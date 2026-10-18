"""scripts/ready_gate.py (ADR-2247, T-0097): the verdict logic, the bootstrap and the CLI exit codes.

The CLI tests run the script as a subprocess against synthetic corpora (--skip-run: no suites are executed,
so every A/C item that needs one is not_assessed) and assert the exit code and the JSON - the way an
operator or CI reads it.  A good corpus passes section B; each bad one fails exactly the check it should.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import ready_gate as rg  # noqa: E402


def make_report(name, *, scenes=6, degraded=(), kinds=(), dead_s=0.5, longest=2.0, status="complete",
                fact=None, mux="pass", cue=None):
    sc = [{"index": i, "audio_s": 10.0} for i in range(1, scenes + 1)]
    sig = [{"id": "still_time", "verdict": "pass", "value": 0.05, "basis": {"n": scenes, "of": scenes},
            "detail": {"per_scene": [{"scene": i, "dead_s": dead_s, "longest_still_s": longest}
                                     for i in range(1, scenes + 1)]}},
           {"id": "mux_integrity", "verdict": mux, "basis": {"n": scenes, "of": scenes}},
           {"id": "fact_support", "verdict": fact or "skip", "value": None}]
    if cue:
        sig.append({"id": "cue_alignment", "verdict": "pass", "value": cue["median"],
                    "basis": {"n": cue["n"], "of": cue["of"]}, "detail": {"p90_s": cue["p90"]}})
    return {"status": status, "scenes": sc, "signals": sig,
            "degraded_scenes": {"n": len(degraded), "of": scenes, "indexes": list(degraded)},
            "degradations": [{"kind": k, "scene": 1} for k in kinds]}


def write_corpus(root, reports):
    for i, r in enumerate(reports):
        d = root / f"job_{i}"
        d.mkdir(parents=True)
        (d / "report.json").write_text(json.dumps(r))
    return root


def good_corpus(root, n=9, **kw):
    return write_corpus(root, [make_report(f"v{i}", **kw) for i in range(n)])


def gate(corpus, *extra):
    p = subprocess.run([sys.executable, str(SCRIPTS / "ready_gate.py"), "--corpus-dir", str(corpus),
                        "--skip-run", *extra], capture_output=True, text=True)
    return p.returncode, json.loads(p.stdout)


def b_status(verdict, name):
    return next(x["status"] for x in verdict["B"] if x["check"] == name)


# ── bootstrap ────────────────────────────────────────────────────────────────────────────────

def test_cluster_bootstrap_of_a_constant_has_a_zero_width_interval():
    ci = rg.cluster_bootstrap([[0.0] * 6 for _ in range(9)], lambda xs: sum(xs) / len(xs), seed=1)
    assert (ci["point"], ci["lo"], ci["hi"]) == (0.0, 0.0, 0.0)
    assert ci["videos"] == 9 and ci["scenes"] == 54


def test_resampling_videos_first_gives_a_wider_interval_than_resampling_scenes_alone():
    # two kinds of video, all scenes in one video alike: the between-video spread is the real uncertainty
    videos = [[1.0] * 8 for _ in range(4)] + [[0.0] * 8 for _ in range(4)]
    clustered = rg.cluster_bootstrap(videos, lambda xs: sum(xs) / len(xs), seed=3)
    flat = rg.cluster_bootstrap([[s for v in videos for s in v]] * 2, lambda xs: sum(xs) / len(xs), seed=3)
    assert (clustered["hi"] - clustered["lo"]) > 3 * (flat["hi"] - flat["lo"])


def test_one_video_cannot_have_an_interval():
    ci = rg.cluster_bootstrap([[0.0, 1.0]], lambda xs: sum(xs) / len(xs))
    assert ci["lo"] is None and rg.decide(ci, at_most=0.5) == "not_demonstrated"


def test_decide_reads_the_bound_not_the_point():
    ci = {"point": 0.195, "lo": 0.10, "hi": 0.25}
    assert rg.decide(ci, at_most=0.20) == "not_demonstrated"          # point passes, bound does not
    assert rg.decide({"point": 0.30, "lo": 0.2, "hi": 0.4}, at_most=0.20) == "fail"
    assert rg.decide({"point": 0.1, "lo": 0.05, "hi": 0.2}, at_most=0.20) == "pass"   # bound == threshold
    assert rg.decide({"point": 0.9, "lo": 0.8, "hi": 0.95}, at_least=0.7) == "pass"


# ── B through the CLI ─────────────────────────────────────────────────────────────────────────────

def test_a_clean_corpus_passes_section_b_but_the_verdict_is_still_a_miss_without_the_other_sections(tmp_path):
    rc, v = gate(good_corpus(tmp_path / "c"))
    for name in ("corpus_complete", "run_validity", "degradation_rate", "board_fallback", "layout_clean", "still_time",
                 "mux_integrity"):
        assert b_status(v, name) == "pass", name
    assert b_status(v, "cue_alignment") == "not_assessed"          # opt-in, never silently passed
    assert rc == 1 and v["ready"] is False and v["may_say_production_ready"] is False
    assert any(m.startswith("A:") for m in v["misses"])             # --skip-run: suites not assessed = miss


def test_a_short_corpus_fails_completeness(tmp_path):
    _, v = gate(good_corpus(tmp_path / "c", n=7))
    assert b_status(v, "corpus_complete") == "fail"


def test_tts_fallback_makes_the_run_invalid_not_failed(tmp_path):
    reps = [make_report(f"v{i}") for i in range(8)] + [make_report("x", kinds=["tts_tier_below"], degraded=[2])]
    _, v = gate(write_corpus(tmp_path / "c", reps))
    assert b_status(v, "run_validity") == "invalid" and v["invalid_run"] is True
    assert not any(x["check"] == "degradation_rate" for x in v["B"])   # nothing else is read from an invalid run


def test_a_pillow_fallback_fails_degradation_and_invalidates_the_signals_it_would_flatter(tmp_path):
    reps = [make_report(f"v{i}") for i in range(8)] + [make_report("x", kinds=["web_to_pillow"], degraded=[3])]
    _, v = gate(write_corpus(tmp_path / "c", reps))
    assert b_status(v, "degradation_rate") == "fail"
    for name in ("layout_clean", "still_time", "mux_integrity"):
        assert b_status(v, name) == "invalid", name


def test_a_board_shown_as_a_still_fails_the_board_fallback_row_apart_from_pillow(tmp_path):
    reps = [make_report(f"v{i}") for i in range(8)] + [make_report("x", kinds=["board_to_still"], degraded=[2])]
    _, v = gate(write_corpus(tmp_path / "c", reps))
    assert b_status(v, "board_fallback") == "fail"
    deg = next(x for x in v["B"] if x["check"] == "degradation_rate")
    assert deg["hard_zero_counts"]["web_to_pillow"] == 0 and deg["board_to_still"] == 1


def test_a_kept_collision_fails_layout_clean(tmp_path):
    reps = [make_report(f"v{i}") for i in range(8)] + [make_report("x", kinds=["collision_kept"])]
    _, v = gate(write_corpus(tmp_path / "c", reps))
    assert b_status(v, "layout_clean") == "fail"


def test_a_still_slide_fails_the_still_time_gate(tmp_path):
    _, v = gate(good_corpus(tmp_path / "c", dead_s=6.0, longest=9.0))
    assert b_status(v, "still_time") == "fail"


def test_a_missing_still_time_signal_is_not_assessed_never_a_pass(tmp_path):
    reps = [make_report(f"v{i}") for i in range(9)]
    for r in reps:
        r["signals"] = [s for s in r["signals"] if s["id"] != "still_time"]
    _, v = gate(write_corpus(tmp_path / "c", reps))
    assert b_status(v, "still_time") == "not_assessed"


def test_a_grounded_task_that_lost_its_claim_check_fails(tmp_path):
    reps = [make_report(f"v{i}") for i in range(8)] + [make_report("g", fact="fail")]
    _, v = gate(write_corpus(tmp_path / "c", reps))
    assert b_status(v, "fact_support") == "fail"


def test_a_truncated_mux_fails(tmp_path):
    reps = [make_report(f"v{i}") for i in range(8)] + [make_report("m", mux="fail")]
    _, v = gate(write_corpus(tmp_path / "c", reps))
    assert b_status(v, "mux_integrity") == "fail"


def test_alignment_worse_than_the_baseline_ratchet_fails_and_better_passes(tmp_path):
    base = (3.37 + 6.3) / 2
    worse = [make_report(f"v{i}", cue={"median": 2.0, "p90": base + 3, "n": 9, "of": 10}) for i in range(9)]
    _, v = gate(write_corpus(tmp_path / "w", worse), "--with-alignment")
    assert b_status(v, "cue_alignment") == "fail"
    better = [make_report(f"v{i}", cue={"median": 0.8, "p90": 1.2, "n": 10, "of": 10}) for i in range(9)]
    _, v = gate(write_corpus(tmp_path / "b", better), "--with-alignment")
    assert b_status(v, "cue_alignment") == "pass"


def test_no_corpus_is_a_miss(tmp_path):
    p = subprocess.run([sys.executable, str(SCRIPTS / "ready_gate.py"), "--skip-run"], capture_output=True, text=True)
    v = json.loads(p.stdout)
    assert p.returncode == 1 and b_status(v, "corpus_complete") == "not_assessed"


# ── A and C ────────────────────────────────────────────────────────────────────────────────────

def test_a_check_whose_test_file_is_gone_fails_it_never_skips(tmp_path):
    (tmp_path / "core" / "console" / "tests").mkdir(parents=True)
    out = rg.section_a(tmp_path, sys.executable, skip_run=True)
    gone = [x for x in out if x.get("reason") == "test file missing"]
    assert gone and all(x["status"] == "fail" for x in gone)


def test_every_a_check_names_a_test_file_that_exists_in_the_real_repos():
    corvinos = Path("/home/shumway/projects/CorvinOS")
    if not corvinos.is_dir():
        pytest.skip("CorvinOS checkout not present")
    for name, repo, files in rg.A_CHECKS:
        root = rg.PLUGIN if repo == "plugin" else corvinos
        assert all((root / f).is_file() for f in files), name


def test_bare_fastapi_app_lint_finds_a_test_that_builds_its_own_app(tmp_path):
    (tmp_path / "test_x.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    pass\n")
    assert rg.bare_app_lint(tmp_path) == ["test_x.py"]


def test_fresh_install_needs_exactly_31_of_31(tmp_path):
    f = tmp_path / "r.json"
    f.write_text(json.dumps({"passed": 30, "total": 31}))
    out = rg.section_c(sys.executable, True, f)
    assert next(x for x in out if x["check"] == "fresh_install_spec")["status"] == "fail"
    f.write_text(json.dumps({"passed": 31, "total": 31}))
    out = rg.section_c(sys.executable, True, f)
    assert next(x for x in out if x["check"] == "fresh_install_spec")["status"] == "pass"


def test_the_words_production_ready_need_alignment_and_a_full_pass():
    ok = [rg.item("x", "pass")]
    assert rg.verdict(ok, ok, ok, invalid=False, with_alignment=False, commit="c")["may_say_production_ready"] is False
    assert rg.verdict(ok, ok, ok, invalid=False, with_alignment=True, commit="c")["may_say_production_ready"] is True
    bad = [rg.item("y", "not_demonstrated")]
    v = rg.verdict(ok, bad, ok, invalid=False, with_alignment=True, commit="c")
    assert v["ready"] is False and v["misses"] == ["B:y=not_demonstrated"]


def test_a_row_where_every_test_skipped_is_not_demonstrated():
    assert rg.a_status("x", 0, "40 passed in 210.00s") == "pass"
    assert rg.a_status("x", 0, "1 skipped in 0.01s") == "not_demonstrated"
    assert rg.a_status("x", 0, "35 passed, 5 skipped in 9s") == "pass"
    assert rg.a_status("capture_policy_hostile_corpus_reaches_nothing", 0, "35 passed, 5 skipped in 9s") == "not_demonstrated"
    assert rg.a_status("x", 1, "1 failed, 3 passed") == "fail"

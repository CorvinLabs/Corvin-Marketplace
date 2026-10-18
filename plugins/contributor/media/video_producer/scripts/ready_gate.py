#!/usr/bin/env python3
"""Production-ready gate of the Video Producer plugin (ADR-2247 "Production-ready gate", T-0097).

"Production ready" is the exit code of this script on a given commit, not a sentence. It prints one JSON
verdict and exits 1 on any miss (0 only when every check passed, 2 when the gate itself could not run).

  A  operations  each item is a pytest run in a sandbox (CORVIN_HOME / XDG / anchor key are temp paths, so
                 nothing reaches the live audit chain); a missing test file is a miss, never a skip.
  B  quality     the signals of the reports of a produced corpus (``--corpus-dir``: one job directory per
                 video, each with ``report.json``), pooled over scenes with a 90 % CLUSTER bootstrap
                 (videos resampled first, then scenes within them). "At most T" passes only when the
                 interval's UPPER bound is <= T; if the interval is wider than the decision, the verdict is
                 ``not_demonstrated``. A run where a scene's TTS fell below the configured tier is INVALID.
                 ``cue_alignment`` spends money and needs ``--with-alignment``; without it the verdict can
                 never carry the words "production ready".
  C  hygiene     plugin suite green, release lint clean, no test that builds its own ``FastAPI()`` app,
                 fresh-install result (``--fresh-install-result``) all green, tree clean.

Statuses: pass | fail | not_demonstrated | not_assessed | invalid. Everything but ``pass`` is a miss.
Usage: ready_gate.py --corpus-dir DIR [--with-alignment] [--fresh-install-result FILE]
                     [--corvinos-dir DIR] [--python PY] [--skip-run] [--seed N] [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

PLUGIN = Path(__file__).resolve().parents[1]
BASELINE = PLUGIN / "tests" / "corpus" / "baseline.json"
BOOTSTRAP_N = 2000
CI_LEVEL = 0.90
DEGRADED_MAX = 0.10
DEAD_SHARE_MAX = 0.20
LONGEST_STILL_P90_MAX_S = 8.0
EXPECTED_VIDEOS = 9          # the seven 2026-10-09 baseline tasks plus the LDD explainer in two languages
FRESH_INSTALL_TOTAL = 31      # the size of web-next/tests/e2e-fresh/video-producer-lifecycle.spec.ts; 29 before the Quality-tab, cancel and delete cases (T-0097)

# A — each item: (name, repo, [test files relative to that repo]).  "plugin" = this directory.
A_CHECKS: List[Tuple[str, str, List[str]]] = [
    ("deadline_primitive_hang_tests_incl_chromium_and_no_bare_subprocess", "plugin", ["tests/test_deadline.py"]),
    ("cancel_leaves_no_process", "corvinos", ["core/console/tests/test_video_producer_cancel_e2e.py"]),
    ("every_job_started_has_one_terminal_event_and_reports_stay_independent", "corvinos",
     ["core/console/tests/test_video_producer_lifecycle_audit_e2e.py"]),
    ("report_holds_no_task_or_narration_text", "plugin", ["tests/test_report_e2e.py"]),
    ("delete_erasure_and_quota", "corvinos", ["core/console/tests/test_video_producer_data_lifecycle_e2e.py"]),
    ("screenshot_job_cannot_read_another_tenants_console_F1", "corvinos",
     ["core/console/tests/test_video_producer_tenant_isolation_e2e.py"]),
    ("plugin_loads_only_for_an_enabling_tenant_F3", "corvinos",
     ["core/console/tests/test_video_producer_plugin_import_e2e.py"]),
    # ADR-2249 D5 signal capture_policy: the hostile corpus (>= 80 entries, the browser pages, WebRTC,
    # Chrome's own background traffic) reaches ZERO destinations and refusals are byte- and time-identical
    ("capture_policy_hostile_corpus_reaches_nothing", "plugin", ["tests/test_capture_policy.py"]),
    # ... and the console answers every target-dependent failure alike (incl. a hang), audits host + hash only
    ("capture_policy_route_uniform_failures_and_audit", "corvinos",
     ["core/console/tests/test_video_producer_capture_e2e.py"]),
    # ADR-2260: a board renders identically in two browsers, its stored model is validated on every load, the worst
    # allowed design stays within twice the median frame time, and a failing board becomes a still of the same image
    ("board_determinism_bounds_and_fallback", "plugin", ["tests/test_board.py"]),
    ("bento_layout_table_and_matrix", "plugin", ["tests/test_bento.py"]),
    ("board_routes_steps_erasure_and_video", "corvinos", ["core/console/tests/test_video_producer_board_e2e.py"]),
]


# ── statistics ────────────────────────────────────────────────────────────────────────────────

def quantile(sorted_vals: Sequence[float], q: float) -> float:
    return sorted_vals[min(len(sorted_vals) - 1, max(0, int(q * len(sorted_vals))))]


def p90(values: Sequence[float]) -> Optional[float]:
    v = sorted(values)
    return v[min(len(v) - 1, int(len(v) * 0.9))] if v else None


def cluster_bootstrap(videos: Sequence[Sequence[Any]], stat: Callable[[List[Any]], Optional[float]], *,
                      n: int = BOOTSTRAP_N, seed: int = 0, level: float = CI_LEVEL) -> Dict[str, Any]:
    """Point estimate and a ``level`` interval. Videos are resampled first, then the scenes of each
    drawn video (the scenes of one video are not independent). ``videos`` is a list of scene lists."""
    videos = [list(v) for v in videos if v]
    pooled = [s for v in videos for s in v]
    point = stat(pooled) if pooled else None
    if point is None or len(videos) < 2:
        return {"point": point, "lo": None, "hi": None, "videos": len(videos), "scenes": len(pooled)}
    rng = random.Random(seed)
    draws: List[float] = []
    for _ in range(n):
        sample: List[Any] = []
        for _v in range(len(videos)):
            v = videos[rng.randrange(len(videos))]
            sample.extend(v[rng.randrange(len(v))] for _ in range(len(v)))
        x = stat(sample)
        if x is not None:
            draws.append(x)
    draws.sort()
    a = (1 - level) / 2
    return {"point": point, "lo": quantile(draws, a), "hi": quantile(draws, 1 - a),
            "videos": len(videos), "scenes": len(pooled)}


def decide(ci: Dict[str, Any], *, at_most: Optional[float] = None, at_least: Optional[float] = None) -> str:
    """The gate reads the interval bound, never the point. No tolerance band. An interval that straddles the
    threshold is ``not_demonstrated`` when the point would pass (the corpus is too small to decide) and
    ``fail`` when the point itself misses."""
    if ci["point"] is None or ci["hi"] is None:
        return "not_demonstrated"
    if at_most is not None:
        if ci["hi"] <= at_most:
            return "pass"
        return "fail" if ci["point"] > at_most else "not_demonstrated"
    if at_least is not None:
        if ci["lo"] >= at_least:
            return "pass"
        return "fail" if ci["point"] < at_least else "not_demonstrated"
    raise ValueError("decide() needs at_most or at_least")


def item(name: str, status: str, **fields: Any) -> Dict[str, Any]:
    return {"check": name, "status": status, **fields}


# ── B — quality from reports ─────────────────────────────────────────────────────────────────────

def load_reports(corpus_dir: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    reports, problems = [], []
    for d in sorted(p for p in corpus_dir.iterdir() if p.is_dir()):
        f = d / "report.json"
        if not f.is_file():
            problems.append(f"{d.name}: no report.json")
            continue
        try:
            rep = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            problems.append(f"{d.name}: report.json unreadable")
            continue
        rep["_dir"] = d.name
        reports.append(rep)
    return reports, problems


def _signal(rep: Dict[str, Any], sid: str) -> Optional[Dict[str, Any]]:
    for r in rep.get("signals") or []:
        if isinstance(r, dict) and r.get("id") == sid:
            return r
    return None


def _degraded_indexes(rep: Dict[str, Any]) -> set:
    return set(((rep.get("degraded_scenes") or {}).get("indexes")) or [])


def section_b(reports: List[Dict[str, Any]], problems: List[str], *, with_alignment: bool, seed: int,
              baseline: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], bool]:
    out: List[Dict[str, Any]] = []
    out.append(item("corpus_complete", "pass" if len(reports) == EXPECTED_VIDEOS and not problems else "fail",
                    n=len(reports), of=EXPECTED_VIDEOS, problems=problems[:10]))
    if not reports:
        return out, False
    kinds = [d.get("kind") for r in reports for d in (r.get("degradations") or [])]
    invalid = "tts_tier_below" in kinds or any(r.get("status") != "complete" for r in reports)
    if invalid:
        out.append(item("run_validity", "invalid",
                        reason="a scene was spoken below the configured TTS tier, or a job did not complete; "
                               "the run proves nothing and may be repeated once (print both runs)"))
        return out, True
    out.append(item("run_validity", "pass"))

    # degradation_rate gates the other signals (a degraded scene would flatter three of them)
    scene_flags = [[1.0 if (s.get("index", i + 1) in _degraded_indexes(r)) else 0.0
                    for i, s in enumerate(r.get("scenes") or [])] for r in reports]
    ci = cluster_bootstrap(scene_flags, lambda xs: sum(xs) / len(xs), seed=seed)
    hard = {k: kinds.count(k) for k in ("web_to_pillow", "no_template", "storyboard_backend_fallback",
                                        "grounding_lost")}
    rate = decide(ci, at_most=DEGRADED_MAX)
    deg = "pass" if rate == "pass" and not any(hard.values()) else ("fail" if rate == "fail" or any(hard.values())
                                                                    else rate)
    # board_to_still (ADR-2260 decision 9) counts toward the scene share, apart from the hard web_to_pillow failure:
    # the picture of the board is shown, not the classic slide
    out.append(item("degradation_rate", deg, ci=ci, threshold_at_most=DEGRADED_MAX, hard_zero_counts=hard,
                    board_to_still=kinds.count("board_to_still")))
    gate_ok = deg == "pass"
    # board_fallback (ADR-2260 decision 9): on the release corpus no board scene may have fallen back to its picture
    n_board = kinds.count("board_to_still")
    out.append(item("board_fallback", "pass" if n_board == 0 else "fail", board_to_still=n_board, threshold=0))

    def gated(name: str, status: str, **f: Any) -> None:
        out.append(item(name, status if gate_ok else "invalid",
                        **({"invalidated_by": "degradation_rate"} if not gate_ok else {}), **f))

    # layout_clean: collisions that stayed in the final video
    kept = kinds.count("collision_kept")
    gated("layout_clean", "pass" if kept == 0 else "fail", collisions_kept=kept)

    # still_time: dead share (duration weight = audio_s) and p90 of the longest still stretch
    rows_per_video: List[List[Tuple[float, float, float]]] = []
    missing: List[str] = []
    for r in reports:
        sig = _signal(r, "still_time")
        per = ((sig or {}).get("detail") or {}).get("per_scene")
        if not sig or sig.get("verdict") == "skip" or not per:
            missing.append(r["_dir"])
            continue
        aud = {s.get("index"): float(s.get("audio_s") or 0) for s in (r.get("scenes") or [])}
        rows_per_video.append([(float(p["dead_s"]), float(p["longest_still_s"]), aud.get(p["scene"], 0.0))
                               for p in per])
    if missing:
        gated("still_time", "not_assessed", reason="signal missing or skipped (numpy?)", videos=missing)
    else:
        dead = cluster_bootstrap(rows_per_video, lambda xs: (sum(x[0] for x in xs) / sum(x[2] for x in xs))
                                 if sum(x[2] for x in xs) > 0 else None, seed=seed)
        lng = cluster_bootstrap(rows_per_video, lambda xs: p90([x[1] for x in xs]), seed=seed)
        d1, d2 = decide(dead, at_most=DEAD_SHARE_MAX), decide(lng, at_most=LONGEST_STILL_P90_MAX_S)
        st = "pass" if d1 == d2 == "pass" else ("fail" if "fail" in (d1, d2) else "not_demonstrated")
        gated("still_time", st, dead_share=dead, longest_still_p90_s=lng, weight_basis="audio_s (approximation)",
              thresholds={"dead_share_at_most": DEAD_SHARE_MAX, "longest_still_p90_at_most_s": LONGEST_STILL_P90_MAX_S})

    # fact_support: a grounded task without a claim check is a fail; videos that are not grounded are n/a
    fs = [(_signal(r, "fact_support") or {}) for r in reports]
    graded = [s for s in fs if s.get("verdict") not in (None, "skip")]
    if not graded:
        gated("fact_support", "not_assessed", reason="no grounded task in the corpus ran the claim check")
    else:
        bad = [s for s in graded if s.get("verdict") in ("fail", "warn")]
        gated("fact_support", "pass" if not bad else "fail", n=len(graded), unsupported=len(bad))

    mux = [(_signal(r, "mux_integrity") or {}).get("verdict") for r in reports]
    gated("mux_integrity", "pass" if all(v == "pass" for v in mux) else
          ("not_assessed" if any(v is None for v in mux) else "fail"), n=sum(v == "pass" for v in mux), of=len(mux))

    # cue_alignment (opt-in): ratchet against the baseline, coverage may not fall
    if not with_alignment:
        out.append(item("cue_alignment", "not_assessed", reason="opt-in; run with --with-alignment"))
    else:
        recs = [_signal(r, "cue_alignment") for r in reports]
        have = [x for x in recs if x and x.get("value") is not None]
        if len(have) < len(reports):
            out.append(item("cue_alignment", "not_assessed", reason="alignment missing for some videos",
                            videos_with=len(have), of=len(reports)))
        else:
            per_video_p90 = [[float((x.get("detail") or {}).get("p90_s") or 0.0)] for x in have]
            ci_a = cluster_bootstrap(per_video_p90, lambda xs: sum(v for v in xs) / len(xs), seed=seed)
            base = [e["measured"]["cue_alignment_p90_s"] for e in baseline.get("entries", [])
                    if e.get("measured", {}).get("cue_alignment_p90_s") is not None]
            ratchet = (sum(base) / len(base)) if base else None
            cov = sum(x["basis"]["n"] for x in have) / max(1, sum(x["basis"]["of"] for x in have))
            base_cov = baseline.get("cue_alignment_coverage")
            st = "not_assessed" if ratchet is None else decide(ci_a, at_most=ratchet)
            if base_cov is not None and cov < base_cov:
                st = "fail"
            out.append(item("cue_alignment", st, p90_mean_of_videos=ci_a, ratchet_baseline_p90_mean=ratchet,
                            coverage=round(cov, 3), baseline_coverage=base_cov,
                            note="baseline coverage is unknown; this run sets it" if base_cov is None else None,
                            goal={"median_s": 1.0, "p90_s": 1.5}))
    return out, False


# ── A / C — subprocess checks ──────────────────────────────────────────────────────────────────────

def sandbox_env(tmp: Path) -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "FORGE_ROOT"}
    env.update(CORVIN_HOME=str(tmp / "home"), XDG_CONFIG_HOME=str(tmp / "xdg"),
               CORVIN_AUDIT_ANCHOR_KEY=str(tmp / "anchor.key"))
    (tmp / "home").mkdir(exist_ok=True)
    (tmp / "xdg").mkdir(exist_ok=True)
    return env


def run_pytest(py: str, cwd: Path, files: Sequence[str], env: Dict[str, str], timeout: int = 1500) -> Tuple[int, str]:
    try:
        p = subprocess.run([py, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *files], cwd=str(cwd),
                           env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    lines = (p.stdout + p.stderr).strip().splitlines()
    return p.returncode, lines[-1] if lines else ""


def section_a(corvinos: Optional[Path], py: str, skip_run: bool) -> List[Dict[str, Any]]:
    out = []
    with tempfile.TemporaryDirectory(prefix="ready_gate_") as t:
        env = sandbox_env(Path(t))
        for name, repo, files in A_CHECKS:
            root = PLUGIN if repo == "plugin" else corvinos
            if root is None:
                out.append(item(name, "not_assessed", reason="--corvinos-dir not given"))
                continue
            missing = [f for f in files if not (root / f).is_file()]
            if missing:
                out.append(item(name, "fail", reason="test file missing", files=missing))
                continue
            if skip_run:
                out.append(item(name, "not_assessed", reason="--skip-run", files=files))
                continue
            rc, tail = run_pytest(py if repo == "plugin" or corvinos is None else str(_venv_py(corvinos, py)),
                                  root, files, env)
            out.append(item(name, a_status(name, rc, tail), files=files, exit_code=rc, tail=tail))
    return out


# rows whose evidence is void if ANY of their tests was skipped (no Chrome, no /proc, no curl): a skipped
# hostile-corpus case proves nothing about the capture (review 2, 2026-10-13)
NO_SKIP_ROWS = frozenset({"capture_policy_hostile_corpus_reaches_nothing",
                          "capture_policy_route_uniform_failures_and_audit"})


def a_status(name: str, rc: int, tail: str) -> str:
    """pass only when pytest passed AND at least one test ran (pytest exits 0 when everything is skipped)."""
    if rc != 0:
        return "fail"
    if not re.search(r"\b[1-9]\d* passed\b", tail):
        return "not_demonstrated"
    if name in NO_SKIP_ROWS and re.search(r"\b[1-9]\d* skipped\b", tail):
        return "not_demonstrated"
    return "pass"


def _venv_py(corvinos: Path, fallback: str) -> str:
    p = corvinos / ".venv" / "bin" / "python"
    return str(p) if p.is_file() else fallback


def bare_app_lint(tests_dir: Path) -> List[str]:
    pat = re.compile(r"^\s*\w+\s*=\s*FastAPI\(", re.M)
    return sorted(str(f.relative_to(tests_dir)) for f in tests_dir.rglob("test_*.py")
                  if pat.search(f.read_text(encoding="utf-8", errors="replace")))


def git(args: Sequence[str], cwd: Path) -> str:
    try:
        return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def section_c(py: str, skip_run: bool, fresh: Optional[Path]) -> List[Dict[str, Any]]:
    out = []
    if skip_run:
        out.append(item("plugin_suite_green", "not_assessed", reason="--skip-run"))
    else:
        with tempfile.TemporaryDirectory(prefix="ready_gate_") as t:
            rc, tail = run_pytest(py, PLUGIN, ["tests"], sandbox_env(Path(t)), timeout=3000)
        out.append(item("plugin_suite_green", "pass" if rc == 0 else "fail", exit_code=rc, tail=tail))
    rl = subprocess.run([py, str(PLUGIN / "scripts" / "release_lint.py"), "--json"], capture_output=True, text=True)
    out.append(item("release_lint_clean", "pass" if rl.returncode == 0 else "fail", exit_code=rl.returncode,
                    findings=(rl.stdout.strip().splitlines() or [])[:10]))
    own_apps = bare_app_lint(PLUGIN / "tests")
    out.append(item("no_test_builds_its_own_fastapi_app", "pass" if not own_apps else "fail", files=own_apps))
    if fresh is None:
        out.append(item("fresh_install_spec", "not_assessed", reason="--fresh-install-result not given"))
    else:
        try:
            r = json.loads(fresh.read_text(encoding="utf-8"))
            ok = r.get("passed") == r.get("total") == FRESH_INSTALL_TOTAL
            out.append(item("fresh_install_spec", "pass" if ok else "fail", passed=r.get("passed"),
                            total=r.get("total"), expected_total=FRESH_INSTALL_TOTAL, source=r.get("source")))
        except (OSError, ValueError):
            out.append(item("fresh_install_spec", "fail", reason="result file unreadable"))
    dirty = git(["status", "--porcelain", "--", "."], PLUGIN)
    out.append(item("tree_clean", "pass" if not dirty else "fail", dirty_files=dirty.splitlines()[:10]))
    return out


# ── verdict ────────────────────────────────────────────────────────────────────────────────────────

def verdict(a: List[Dict[str, Any]], b: List[Dict[str, Any]], c: List[Dict[str, Any]], *, invalid: bool,
            with_alignment: bool, commit: str) -> Dict[str, Any]:
    misses = [f"{sec}:{x['check']}={x['status']}" for sec, items in (("A", a), ("B", b), ("C", c))
              for x in items if x["status"] != "pass"]
    ready = not misses
    return {"ready": ready, "invalid_run": invalid, "with_alignment": with_alignment,
            "may_say_production_ready": bool(ready and with_alignment), "commit": commit,
            "misses": misses, "A": a, "B": b, "C": c}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus-dir", type=Path)
    ap.add_argument("--with-alignment", action="store_true")
    ap.add_argument("--fresh-install-result", type=Path)
    ap.add_argument("--corvinos-dir", type=Path)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--skip-run", action="store_true", help="do not execute suites; those items are not_assessed")
    ap.add_argument("--seed", type=int, default=20261012)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    try:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"ready_gate: cannot read {BASELINE}: {e}", file=sys.stderr)
        return 2
    if a.corpus_dir is None or not a.corpus_dir.is_dir():
        b, invalid = [item("corpus_complete", "not_assessed", reason="--corpus-dir missing or not a directory")], False
    else:
        reports, problems = load_reports(a.corpus_dir)
        b, invalid = section_b(reports, problems, with_alignment=a.with_alignment, seed=a.seed, baseline=baseline)
    commit = git(["rev-parse", "HEAD"], PLUGIN)
    v = verdict(section_a(a.corvinos_dir, a.python, a.skip_run), b, section_c(a.python, a.skip_run, a.fresh_install_result),
                invalid=invalid, with_alignment=a.with_alignment, commit=commit)
    text = json.dumps(v, indent=2, ensure_ascii=False)
    if a.out:
        a.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if v["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())

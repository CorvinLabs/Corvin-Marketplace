"""R5 signals (ADR-2247, PLAN-0946 R5, T-0094): still_time, cue_alignment, language_parity,
revision_locality, and the storage step that gates on language_parity.

Every gating signal has a positive control: a static clip makes ``still_time`` warn; the real German /
English LDD pair of 2026-10-09 makes ``language_parity`` fail (and the storage step refuses to store it);
a scene that never got a cue lowers ``cue_alignment``'s coverage. ``cue_alignment`` runs on RECORDED
whisper-1 responses (tests/fixtures/whisper/, provenance inside) - the network is cut in every test here.
Media fixtures are real ffmpeg output."""
import builtins
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from src import report as rp
from src import signals as sg

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
WHISPER = json.loads((FIX / "whisper" / "ldd_de_scenes_3_4.json").read_text(encoding="utf-8"))
needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg/ffprobe not installed")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No test in this file may reach a provider: the recorded fixture is the only whisper there is."""
    import requests

    def refuse(*a, **k):
        raise AssertionError("network call attempted in a test")
    monkeypatch.setattr(requests, "post", refuse)
    monkeypatch.setattr(requests, "get", refuse)


def _clip(path: Path, source: str, seconds: float):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"{source}{':' if '=' in source else '='}size=640x360:rate=30:duration={seconds}",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)], check=True, timeout=60)


def _job(tmp_path, clips):
    job = tmp_path / "job_x"
    for i, (src, sec) in enumerate(clips, start=1):
        _clip(job / "scenes" / f"scene_{i:03d}.mp4", src, sec)
    report = {"scenes": [{"index": i} for i in range(1, len(clips) + 1)]}
    return job, report


# ── still_time ────────────────────────────────────────────────────────────────────────────────

@needs_ffmpeg
def test_still_time_positive_control_a_static_video_warns(tmp_path):
    job, report = _job(tmp_path, [("color=c=navy", 8), ("color=c=black", 7)])
    r = sg.run(sg.SignalContext(job_dir=job, report=report), only=["still_time"])[0]
    assert r["verdict"] == "warn" and r["value"] == 1.0, r
    assert r["basis"] == {"n": 0, "of": 2} and r["detail"]["scenes_still_ge_5s"] == 2
    assert "dead share above 20 %" in r["reason"]


@needs_ffmpeg
def test_still_time_moving_content_passes(tmp_path):
    job, report = _job(tmp_path, [("testsrc2", 6), ("testsrc2", 4)])
    r = sg.run(sg.SignalContext(job_dir=job, report=report), only=["still_time"])[0]
    assert r["verdict"] == "pass" and r["value"] == 0.0, r
    assert r["threshold"] == {"dead_share_max": 0.2, "longest_still_p90_max_s": 8.0}


@needs_ffmpeg
def test_still_time_is_a_skip_without_numpy(tmp_path, monkeypatch):
    job, report = _job(tmp_path, [("color=c=navy", 2)])
    real = builtins.__import__

    def no_numpy(name, *a, **k):
        if name == "numpy" or name.startswith("numpy."):
            raise ImportError("No module named 'numpy'")
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_numpy)
    r = sg.run(sg.SignalContext(job_dir=job, report=report), only=["still_time"])[0]
    assert (r["verdict"], r["value"], r["reason"]) == ("skip", None, "numpy missing")


@needs_ffmpeg
def test_the_script_and_the_signal_are_one_definition(tmp_path):
    """measure_engagement.py calls the signal's code: the same clips give the same dead share."""
    spec = importlib.util.spec_from_file_location("me", ROOT / "scripts" / "measure_engagement.py")
    me = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(me)
    assert me.sg is sg and me.NumpyMissing is sg.NumpyMissing
    videos = tmp_path / "videos"
    job, report = _job(videos, [("color=c=navy", 6), ("testsrc2", 3)])
    (job / "metadata.json").write_text(json.dumps({"metadata": {}}))
    script = me.measure_job(videos, "job_x", None)
    sig = sg.run(sg.SignalContext(job_dir=job, report=report), only=["still_time"])[0]
    assert script["dead_share"] == sig["value"]
    assert script["longest_still"] == sig["detail"]["longest_still_max_s"]


def test_still_time_agreement_on_the_corpus_was_measured_and_holds():
    """The DoD numbers come from scripts/still_time_agreement.py run on the nine corpus videos
    (tests/corpus/still_time_agreement.json); this asserts what was MEASURED, not a claim."""
    data = json.loads((ROOT / "tests" / "corpus" / "still_time_agreement.json").read_text())
    s = data["summary"]
    assert (s["jobs"], s["of"]) == (9, 9)
    assert s["max_diff_points_vs_recorded"] <= 1.0 and s["max_diff_points_vs_reference"] <= 1.0
    assert s["max_s_per_min"] <= 15.0 and s["verdict"] == "pass"
    assert all(j["s_per_min"] <= 15.0 for j in data["jobs"])


@pytest.mark.skipif(not os.environ.get("VP_CORPUS_VIDEOS"),
                    reason="re-measurement needs the corpus videos: set VP_CORPUS_VIDEOS=<tenant>/video_producer/videos")
def test_still_time_agreement_re_measured_live():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "still_time_agreement.py"), os.environ["VP_CORPUS_VIDEOS"]],
                       capture_output=True, text=True, timeout=1800)
    assert r.returncode == 0, r.stdout + r.stderr


# ── cue_alignment on the recorded whisper fixture ────────────────────────────────────────────────

def replay(fixture=WHISPER):
    calls = []

    def transcribe(mp3: Path):
        calls.append(mp3.name)
        return fixture["responses"][str(int(mp3.stem.split("_")[1]))]["response"]["words"]
    transcribe.calls = calls
    return transcribe


def _aligned_job(tmp_path, extra_scenes=()):
    job = tmp_path / "job_ldd"
    (job / "scenes").mkdir(parents=True)
    scenes = list(WHISPER["storyboard"]["scenes"]) + list(extra_scenes)
    for i in range(1, len(WHISPER["storyboard"]["scenes"]) + 1):
        (job / "scenes" / f"scene_{i:03d}.mp3").write_bytes(b"recorded elsewhere")  # the replay never reads it
    rep = rp.ProductionReport("job_ldd")
    for i in range(1, len(scenes) + 1):
        rep.scene(i, renderer="web" if i <= 2 else "pillow")
    rep.finish("complete")
    rep.write(job)
    return job, {"scenes": scenes}, {"cues": WHISPER["cues"]}


def test_cue_alignment_from_recorded_whisper_is_stored_in_the_report(tmp_path):
    job, storyboard, meta = _aligned_job(tmp_path)
    t = replay()
    out = sg.measure_posthoc(job, storyboard, meta, transcribe=t)
    assert out["stored"] is True and t.calls == ["scene_001.mp3", "scene_002.mp3"]
    rec = out["signals"][0]
    # 9 cued items, every one heard: errors 0.48 0.54 0.73 0.83 1.04 1.05 1.3 1.55 5.32 s
    assert (rec["id"], rec["kind"], rec["basis"]) == ("cue_alignment", "posthoc", {"n": 9, "of": 9})
    assert rec["value"] == 1.04 and rec["detail"]["p90_s"] == 5.32 and rec["detail"]["coverage"] == 1.0
    assert rec["verdict"] == "warn" and rec["reason"] == "above the goal"
    stored = rp.read(job)
    assert [s["id"] for s in stored["signals"]].count("cue_alignment") == 1 and "posthoc_at" in stored
    # the report never carries narration text (validated on write)
    flat = json.dumps(stored, ensure_ascii=False)
    for sc in storyboard["scenes"]:
        assert sc["narration_text"][:30] not in flat
    # a second run replaces, never duplicates
    sg.measure_posthoc(job, storyboard, meta, transcribe=replay())
    assert [s["id"] for s in rp.read(job)["signals"]].count("cue_alignment") == 1


def test_cue_alignment_coverage_counts_a_classic_slide_as_unmatched(tmp_path):
    pillow = {"template": "diagram", "narration_text": "Drei Knoten.", "beats": None,
              "data": {"title": "Drei", "nodes": [{"label": "Eins"}, {"label": "Zwei"}, {"label": "Drei"}]}}
    job, storyboard, meta = _aligned_job(tmp_path, extra_scenes=[pillow])
    rec = sg.measure_posthoc(job, storyboard, meta, transcribe=replay())["signals"][0]
    assert rec["basis"] == {"n": 9, "of": 12} and rec["detail"]["coverage"] == 0.75
    assert {"scene": 3, "items": 3, "matched": 0, "why": "no cue (classic slide)"} in rec["detail"]["per_scene"]


def test_cue_alignment_is_a_skip_unless_run(tmp_path):
    job, storyboard, meta = _aligned_job(tmp_path)
    out = sg.measure_posthoc(job, storyboard, meta, transcribe=None)
    assert out["signals"][0]["verdict"] == "skip" and "opt-in" in out["signals"][0]["reason"]
    # and a job's own end never runs it
    assert "cue_alignment" not in {r["id"] for r in sg.run(sg.SignalContext(job_dir=job, report={"scenes": []}))}


def test_a_refused_measurement_is_stored_as_a_skip_with_the_reason(tmp_path):
    job, storyboard, meta = _aligned_job(tmp_path)
    t = replay()
    out = sg.measure_posthoc(job, storyboard, meta, transcribe=t, refused="refused by the pre-spawn gates")
    assert t.calls == [] and out["stored"] is True
    rec = {s["id"]: s for s in rp.read(job)["signals"]}["cue_alignment"]
    assert (rec["verdict"], rec["value"], rec["reason"]) == ("skip", None, "refused by the pre-spawn gates")


def test_alignment_searches_from_the_sentence_that_names_the_item_not_the_first_mention():
    """Synthetic words (not a recording): the intro names all three items; the beats place each on its
    own later sentence. The first-mention rule measures 'Kennzahl' at 1.2 s; the right one at 6.0 s."""
    narration = "Es gibt Test, Kennzahl und Review. Zuerst der Test. Dann die Kennzahl. Zuletzt das Review."
    words = [{"word": w, "start": s} for w, s in [
        ("Es", 0.0), ("gibt", 0.2), ("Test", 0.6), ("Kennzahl", 1.2), ("und", 1.8), ("Review", 2.0),
        ("Zuerst", 3.0), ("der", 3.3), ("Test", 3.5), ("Dann", 5.4), ("die", 5.7), ("Kennzahl", 6.0),
        ("Zuletzt", 7.5), ("das", 7.9), ("Review", 8.1)]]
    items = [{"label": "Test", "at": 3.0}, {"label": "Kennzahl", "at": 5.4}, {"label": "Review", "at": 7.6}]
    rows = sg.align_scene(narration, [None, 0, 1, 2], items, words)
    assert [r["error_s"] for r in rows] == [0.25, 0.35, 0.25]
    assert abs(5.4 + 0.25 - sg.spoken_time("Kennzahl", words)) == pytest.approx(4.45)  # the old, wrong match


# ── language_parity + the storage step ─────────────────────────────────────────────────────────

def _scenes(name):
    return json.loads((FIX / "parity" / name).read_text(encoding="utf-8"))["scenes"]


def test_language_parity_positive_control_the_real_ldd_pair_fails():
    p = sg.language_parity(_scenes("ldd_de.json"), _scenes("ldd_en.json"))
    assert p["verdict"] == "fail"
    assert p["templates"]["identical_positions"] == 4 and p["templates"]["of"] == 10
    assert p["numeric_facts"]["only_de"] == ["1.5", "2", "4.5"] and p["numeric_facts"]["only_en"] == ["4"]
    assert set(p["reasons"]) == {"template sequence below 80 % identical", "numeric facts differ"}


def test_language_parity_reads_locale_formatting_as_the_same_fact():
    de = [{"template": "hero", "narration_text": "Leerlauf sank von 57 % auf 19 Prozent, bei 1.234,5 Sekunden."},
          {"template": "chart", "narration_text": "Dreizehn Schwachstellen, p90 4,5 s."}]
    en = [{"template": "hero", "narration_text": "Dead share fell from 57% to 19 percent, over 1,234.5 seconds."},
          {"template": "chart", "narration_text": "13 weaknesses, p90 4.5 s."}]
    assert sg.language_parity(de, en)["verdict"] == "pass"
    en[1]["narration_text"] = "13 weaknesses."  # the 4.5 s fact dropped in one version
    p = sg.language_parity(de, en)
    assert p["verdict"] == "fail" and p["numeric_facts"]["only_de"] == ["4.5"]


def _store(videos, job_id, scenes):
    (videos / job_id).mkdir(parents=True)
    (videos / job_id / "output.mp4").write_bytes(job_id.encode())
    (videos.parent / "jobs").mkdir(exist_ok=True)
    (videos.parent / "jobs" / f"{job_id}.json").write_text(json.dumps({"id": job_id, "storyboard": json.dumps({"scenes": scenes})}))


def test_the_storage_step_refuses_a_failing_pair_and_writes_why_into_sources_md(tmp_path):
    videos = tmp_path / "video_producer" / "videos"
    _store(videos, "job_00000de1", _scenes("ldd_de.json"))
    _store(videos, "job_00000e21", _scenes("ldd_en.json"))
    dest = tmp_path / "Corvin-Videos" / "ldd"
    dest.mkdir(parents=True)
    (dest / "sources.md").write_text("# LDD\n\nHand-written text stays.\n")
    cli = [sys.executable, str(ROOT / "scripts" / "store_video_pair.py"), str(videos), "--de", "job_00000de1",
           "--en", "job_00000e21", "--dest", str(dest)]
    r = subprocess.run(cli, capture_output=True, text=True, timeout=60)
    assert r.returncode == 1 and "not stored" in r.stderr
    assert not list(dest.glob("*.mp4"))
    text = (dest / "sources.md").read_text()
    assert text.startswith("# LDD\n\nHand-written text stays.\n") and "## Language parity" in text
    assert "**fail" in text and "Only in de: `1.5`, `2`, `4.5`; only in en: `4`" in text

    # the same pair after a fix: the EN version carries the facts and the templates -> stored, block replaced
    fixed = [dict(s) for s in _scenes("ldd_de.json")]
    shutil.rmtree(videos / "job_00000e21")
    (videos.parent / "jobs" / "job_00000e21.json").unlink()
    _store(videos, "job_00000e21", fixed)
    r = subprocess.run(cli, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert (dest / "ldd.de.mp4").read_bytes() == b"job_00000de1" and (dest / "ldd.en.mp4").read_bytes() == b"job_00000e21"
    text = (dest / "sources.md").read_text()
    assert text.count("## Language parity") == 1 and "**pass**" in text and "Hand-written text stays." in text


# ── revision_locality ─────────────────────────────────────────────────────────────────────────

def test_revision_locality_counts_word_identical_scenes_of_the_base():
    base = ["Erste Szene.", "Zweite  Szene.", "Dritte Szene."]
    assert sg.revision_locality(base, ["Erste Szene.", "Zweite Szene.", "Neue dritte Szene."]) == \
        {"kept": 2, "of": 3, "share": 0.667}
    assert sg.revision_locality(base, ["Alles neu."])["share"] == 0.0


def test_revision_locality_is_information_and_skips_a_first_version(tmp_path):
    ctx = sg.SignalContext(job_dir=tmp_path, report={"scenes": []}, narrations=["A.", "B."], base_narrations=["A.", "C."])
    r = sg.run(ctx, only=["revision_locality"])[0]
    assert (r["verdict"], r["value"], r["basis"]) == ("info", 0.5, {"n": 1, "of": 2})
    r = sg.run(sg.SignalContext(job_dir=tmp_path, report={"scenes": []}, narrations=["A."]), only=["revision_locality"])[0]
    assert (r["verdict"], r["reason"]) == ("skip", "not a revision")

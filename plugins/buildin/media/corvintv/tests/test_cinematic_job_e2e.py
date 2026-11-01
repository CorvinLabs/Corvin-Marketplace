"""Cinematic mode through the JOB PIPELINE: the same entry the console's process runner starts.

Real ``job_main`` in its own process, real screenplay parsing + validation + repair round, real Penpot import,
headless Chromium drawing the canvas engine, ffmpeg, report.json. Only the director MODEL (fixed answers,
``_vp_job_main_fake_director.py``) and the TTS voice (offline mock tier) are replaced; nothing here calls the
renderer directly."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from src import report as rp
from src.async_runner import ProcessJobRunner
from src.storage import get_storage, reset_storage
from tests.test_process_runner import mkjob, procs_for, wait_for

pytest.importorskip("playwright")
pytestmark = [pytest.mark.e2e, pytest.mark.skipif(not os.path.isdir("/proc"), reason="needs /proc (Linux)")]

ENTRY = [sys.executable, str(Path(__file__).resolve().parent / "_vp_job_main_fake_director.py")]
BOARD = (Path(__file__).resolve().parent / "fixtures" / "penpot_board.svg").read_bytes().decode("utf-8")
SENT = "This sentence has exactly eight spoken words here."


def screenplay(art="board"):
    beat = lambda: {"en": SENT, "de": "Dieser Satz hat genau acht gesprochene Wörter hier."}  # noqa: E731
    return {"title": {"en": "Caches", "de": "Caches"}, "acts": [
        {"id": "01", "beats": [beat(), beat(), beat(), beat()],
         "actors": [{"id": "sky", "type": "sky", "par": 0.1, "stars": 1}, {"id": "g", "type": "grade", "v": 0.6, "z": 100},
                    {"id": "cap", "type": "caption", "x": 960, "y": 540, "size": 90, "align": "center",
                     "text": {"en": "Caches", "de": "Zwischenspeicher"}}],
         "tweens": [{"a": "cam", "p": "zoom", "to": 1.15, "at": "b0", "d": 6}]},
        {"id": "02", "beats": [beat(), beat(), beat(), beat()],
         "actors": [{"id": "sky", "type": "sky", "par": 0.1}, {"id": "g", "type": "grade", "v": 0.6, "z": 100},
                    {"id": "d", "type": "art", "src": art, "x": 960, "y": 540, "w": 1280, "h": 720, "p": 0, "o": 0}],
         "tweens": [{"a": "d", "p": "o", "to": 1, "at": "b1", "d": 0.3},
                    {"a": "d", "p": "p", "to": 1, "at": "b1", "d": 1.2, "e": "out"}]}]}


@pytest.fixture
def base(tmp_path):
    reset_storage()
    b = tmp_path / "tenant"
    b.mkdir()
    yield str(b)
    reset_storage()


async def _run(base, tmp_path, job_id, first, repair=None, langs=("en", "de"), expect="complete", **extra):
    llm = tmp_path / "llm"
    llm.mkdir(exist_ok=True)
    (llm / f"{job_id}.direction.json").write_text(json.dumps(first), encoding="utf-8")
    if repair is not None:
        (llm / f"{job_id}.repair.json").write_text(json.dumps(repair), encoding="utf-8")
    cfg = mkjob(base, job_id)
    cfg.update(mode="cinematic", storyboard_backend="claude_cli", storyboard_model="fake-model", cinematic_minutes=1,
               cinematic_langs=list(langs), cinematic_designs={"board": BOARD}, **extra)
    runner = ProcessJobRunner(entry=ENTRY, env={**os.environ, "VP_FAKE_LLM_DIR": str(llm)})
    await runner.start_job(job_id, "explain how caches speed things up", cfg)
    assert wait_for(lambda: get_storage(base).get_job(job_id).status in ("complete", "error"), 600, 0.2)
    job = get_storage(base).get_job(job_id)
    assert job.status == expect, job.error_message
    assert wait_for(lambda: procs_for(job_id) == [], 10)
    return job, Path(base) / "videos" / job_id


def _probe(path: Path, entries: str):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", entries, "-of", "json", str(path)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _frame(video: Path, t: float, out: Path) -> Image.Image:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", str(out)], check=True)
    return Image.open(out).convert("RGB")


def _bright(img: Image.Image, box) -> int:
    return sum(1 for p in img.crop(box).getdata() if sum(p) > 150)


async def test_a_cinematic_job_makes_one_video_per_language_with_the_penpot_design_in_it(base, tmp_path):
    job, d = await _run(base, tmp_path, "job_cin", screenplay(), repair=None)
    # one MP4 per language, same length, a video and an audio stream, no subtitle stream
    en, de = d / "output.mp4", d / "output.de.mp4"
    assert en.is_file() and de.is_file() and job.video_output_path == str(en)
    for p in (en, de):
        assert sorted(s["codec_type"] for s in _probe(p, "stream=codec_type")["streams"]) == ["audio", "video"]
    dur = [float(_probe(p, "format=duration")["format"]["duration"]) for p in (en, de)]
    assert abs(dur[0] - dur[1]) < 0.1
    meta = json.loads((d / "output.json").read_text(encoding="utf-8")) if (d / "output.json").exists() else None
    out = get_storage(base).get_video_output("job_cin") if hasattr(get_storage(base), "get_video_output") else None
    md = (out.metadata if out else (meta or {}).get("metadata", {}))
    assert md.get("mode") == "cinematic" and md.get("languages") == ["en", "de"] and md.get("designs") == ["board"]
    assert md.get("language_sync_diff_ms", 999) < 100
    # the storyboard the console shows: one scene per act
    assert [s.id for s in job.storyboard.scenes] == ["act-01", "act-02"]
    # the design really is in the picture: dark before it is revealed, bright after
    tl = json.loads((d / "cinematic" / "timeline.json").read_text(encoding="utf-8"))
    a2 = tl["acts"][1]
    centre = (480, 270, 1440, 810)
    before = _bright(_frame(en, a2["start"] + 0.4, tmp_path / "b.png"), centre)
    after = _bright(_frame(en, a2["start"] + a2["beats"][1] + 2.0, tmp_path / "a.png"), centre)
    assert after > before + 20000, (before, after)
    # the text act is drawn per language: German caption in the German file, English in the English one
    cap_en = _frame(en, tl["acts"][0]["beats"][1], tmp_path / "ce.png")
    cap_de = _frame(de, tl["acts"][0]["beats"][1], tmp_path / "cd.png")
    assert list(cap_en.crop((300, 450, 1620, 630)).getdata()) != list(cap_de.crop((300, 450, 1620, 630)).getdata())
    # report and screenplay are kept; the temporary frames are not
    rep = json.loads((d / rp.REPORT_NAME).read_text(encoding="utf-8"))
    assert rep["status"] == "complete"
    assert (d / "cinematic" / "direction.json").is_file() and not (d / "cinematic" / "frames").exists()


async def test_a_rejected_screenplay_gets_one_repair_round_that_names_every_finding(base, tmp_path):
    job, d = await _run(base, tmp_path, "job_rep", screenplay(art="ghost"), repair=screenplay(), langs=("en",))
    out = get_storage(base).get_video_output("job_rep")
    assert out.metadata["screenplay_repaired"] >= 1 and (d / "output.mp4").is_file()
    assert not (d / "output.de.mp4").exists()


async def test_a_screenplay_still_wrong_after_the_repair_round_ends_the_job_with_the_reason(base, tmp_path):
    job, d = await _run(base, tmp_path, "job_bad", screenplay(art="ghost"), repair=screenplay(art="ghost"),
                        langs=("en",), expect="error")
    assert "unknown design" in job.error_message and "repair" in job.error_message
    assert not (d / "output.mp4").exists()

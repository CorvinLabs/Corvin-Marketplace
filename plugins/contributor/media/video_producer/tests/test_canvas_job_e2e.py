"""Canvas through the JOB PIPELINE (ADR-2249 D1/D5, PLAN-0947 P2, T-0110).

Same entry the console's process runner starts: the real ``job_main`` in its own process, real
storyboard parsing + validation + repair round, ``continue_from`` resolution, headless Chromium with
the canvas probe, ffmpeg, report.json and its signals. Only the storyboard MODEL (fixed answers,
``_vp_job_main_fake_llm.py``) and the TTS voice (offline mock tier) are replaced. Nothing here calls
the renderer directly."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PIL import Image

from src import report as rp
from src.async_runner import ProcessJobRunner
from src.storage import get_storage, reset_storage
from tests.canvas_cases import CLEAN
from tests.test_process_runner import mkjob, procs_for, wait_for

pytest.importorskip("playwright")
pytestmark = [pytest.mark.e2e, pytest.mark.skipif(not os.path.isdir("/proc"), reason="needs /proc (Linux)")]

ENTRY = [sys.executable, str(Path(__file__).resolve().parent / "_vp_job_main_fake_llm.py")]
# where the "Database" cylinder of CLEAN is drawn (grid col 9..12, row 2..4 of the canvas)
DB_BOX = (1360, 505, 1745, 705)

HERO = {"id": "s1", "kind": "title", "duration_ms": 8000, "narration_text": "Why caches are fast.",
        "visual_description": "title", "template": "hero", "data": {"title": "Why caches are fast"}}
CACHE = {"id": "s2", "kind": "solution", "duration_ms": 12000,
         "narration_text": ("A user sends a request. The app server receives it. It looks in the cache first. "
                            "On a miss it asks the database. A hit skips the database."),
         "visual_description": "sketch", "template": "canvas", "data": CLEAN, "beats": [0, 1, 2, 3, 4]}
CONTINUED = {"id": "s3", "kind": "example", "duration_ms": 8000,
             "narration_text": "The second request is much faster. It is answered by the cache.",
             "visual_description": "same sketch", "template": "canvas", "beats": [0, 1],
             "data": {"title": "The second request is served from the cache", "continue_from": "s2", "elements": [
                 {"type": "label", "id": "fast", "text": "Second request: 2 ms", "at": {"col": 0, "row": 0, "w": 5, "h": 1},
                  "font": "s", "step": 1},
                 {"type": "circle-highlight", "target": "cache", "text": "hit", "side": "e", "step": 2}]}}
SMALL = {"title": "Two kinds of memory", "elements": [
    {"type": "box", "id": "ram", "text": "Cache in RAM", "at": {"col": 1, "row": 1, "w": 4, "h": 2}, "step": 1},
    {"type": "cylinder", "id": "disk", "text": "Database on disk", "at": {"col": 7, "row": 1, "w": 4, "h": 2}, "step": 2},
    {"type": "arrow", "from": "ram", "to": "disk", "text": "slower", "step": 2}]}
BROKEN = {**SMALL, "elements": SMALL["elements"][:2] + [{"type": "arrow", "from": "ram", "to": "ghost", "step": 2}]}
SUMMARY = {"id": "s4", "kind": "summary", "duration_ms": 8000,
           "narration_text": "Memory is fast. The disk is slower.", "visual_description": "sketch",
           "template": "canvas", "data": BROKEN, "beats": [0, 1]}


@pytest.fixture
def base(tmp_path):
    reset_storage()
    b = tmp_path / "tenant"
    b.mkdir()
    yield str(b)
    reset_storage()


async def _run_job(base, tmp_path, job_id, storyboard, repair=None):
    llm = tmp_path / "llm"
    llm.mkdir(exist_ok=True)
    (llm / f"{job_id}.storyboard.json").write_text(json.dumps(storyboard), encoding="utf-8")
    if repair is not None:
        (llm / f"{job_id}.repair.json").write_text(json.dumps(repair), encoding="utf-8")
    cfg = mkjob(base, job_id)
    cfg.update(storyboard_backend="claude_cli", storyboard_model="fake-model")
    runner = ProcessJobRunner(entry=ENTRY, env={**os.environ, "VP_FAKE_LLM_DIR": str(llm)})
    await runner.start_job(job_id, "explain caching", cfg)
    assert wait_for(lambda: get_storage(base).get_job(job_id).status in ("complete", "error"), 600, 0.2)
    job = get_storage(base).get_job(job_id)
    assert job.status == "complete", job.error_message
    assert wait_for(lambda: procs_for(job_id) == [], 10)
    job_dir = Path(base) / "videos" / job_id
    return job_dir, json.loads((job_dir / rp.REPORT_NAME).read_text(encoding="utf-8"))


def _streams(video: Path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(video)],
                         capture_output=True, text=True, check=True)
    return sorted(s["codec_type"] for s in json.loads(out.stdout)["streams"])


def _duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def _frame(video: Path, t: float, out: Path) -> Image.Image:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", str(out)],
                   check=True)
    return Image.open(out).convert("RGB")


def _ink(img: Image.Image, box, thr=40) -> int:
    im = img.crop(box)
    bg = im.getpixel((0, 0))
    return sum(1 for p in im.getdata() if max(abs(p[i] - bg[i]) for i in range(3)) > thr)


async def test_a_canvas_job_draws_with_the_pen_continues_a_board_and_reports_its_signals(base, tmp_path):
    t0 = time.monotonic()
    storyboard = {"id": "sb_cv", "didactic_strategy": "rich_visual", "scenes": [HERO, CACHE, CONTINUED, SUMMARY]}
    repair = {"scenes": [{"id": "s4", "template": "canvas", "data": SMALL}]}
    job_dir, rep = await _run_job(base, tmp_path, "job_cv", storyboard, repair)

    video = job_dir / "output.mp4"
    assert video.is_file() and video.stat().st_size > 10_000
    assert _streams(video) == ["audio", "video"]

    scenes = {s["index"]: s for s in rep["scenes"]}
    for i in (2, 3, 4):
        assert scenes[i]["renderer"] == "web" and scenes[i]["template"] == "canvas", scenes[i]
    sig = {s["id"]: s for s in rep["signals"]}
    # every canvas passed the render gate on its first render: nothing laddered, nothing degraded
    assert sig["canvas_clean"]["verdict"] == "pass" and sig["canvas_clean"]["basis"] == {"n": 3, "of": 3}, sig["canvas_clean"]
    assert not [d for d in rep["degradations"] if d["kind"] in ("collision_replaced", "collision_kept", "web_to_pillow")], \
        rep["degradations"]
    # the model wrote three canvases, two validated at once, the repair round fixed the third
    ca = sig["canvas_authoring"]
    assert ca["verdict"] == "info" and ca["basis"] == {"n": 2, "of": 3} and ca["detail"]["after_repair"] == 3, ca

    # frames of the real MP4, scene starts from the scene clips it was concatenated from
    clips = [job_dir / "scenes" / f"scene_{i:03d}.mp4" for i in range(1, 5)]
    starts = [0.0]
    for c in clips[:-1]:
        starts.append(starts[-1] + _duration(c))
    s2, s3 = starts[1], starts[2]
    d2 = _duration(clips[1])
    # scene 2 draws the board stroke by stroke: no database at its start, part of it while the pen
    # is on it, the whole cylinder at its end
    seq = [_ink(_frame(video, s2 + t, tmp_path / f"f2_{k}.png"), DB_BOX)
           for k, t in enumerate([0.1] + [d2 * f for f in (0.55, 0.62, 0.69, 0.76, 0.83, 0.9)] + [d2 - 0.15])]
    assert seq[0] == 0, seq
    assert seq[-1] > 3000, seq
    assert any(0 < c < seq[-1] * 0.8 for c in seq[1:-1]), f"no frame shows the cylinder being drawn: {seq}"
    # scene 3 continues the board: the database is there from its first frame, nothing redrawn
    first3 = _ink(_frame(video, s3 + 0.1, tmp_path / "f3.png"), DB_BOX)
    assert first3 > 3000, first3
    print(f"\nMEASURE canvas job e2e: {time.monotonic() - t0:.1f}s, ink scene2={seq}, scene3 first={first3}")

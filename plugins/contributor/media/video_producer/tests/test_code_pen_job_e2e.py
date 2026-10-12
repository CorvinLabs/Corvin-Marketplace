"""Pen-drawn code annotations through the JOB PIPELINE (ADR-2249 D1 annotation layer, T-0110).

The real ``job_main`` in its own process (storyboard model and TTS voice faked, nothing else): a code
scene whose annotation carries ``mark: circle`` is rendered next to an identical one without it, and
the frames of the real MP4 must differ exactly where the pen draws, only after the annotation's beat."""
import copy
import os

import pytest
from PIL import Image, ImageChops

from tests.test_canvas_job_e2e import HERO, _duration, _frame, _run_job, base  # noqa: F401  (base = fixture)
from tests.test_code_v2 import V2

pytest.importorskip("playwright")
pytestmark = [pytest.mark.e2e, pytest.mark.skipif(not os.path.isdir("/proc"), reason="needs /proc (Linux)")]

NARRATION = ("We read a config file. First the import. Then the loader opens the file safely. "
             "That call closes the file for us. Finally the result is printed.")
# where the pen circles `open(path)` on line 4 of the 1920x1080 frame
PEN_BOX = (385, 505, 605, 575)


def _code_scene(sid, mark):
    data = copy.deepcopy(V2)
    if mark:
        data["annotations"][0]["mark"] = mark
    return {"id": sid, "kind": "example", "duration_ms": 12000, "narration_text": NARRATION,
            "visual_description": "code", "template": "code", "data": data, "beats": [None, 0, 1, 3, 4]}


def _changed(a: Image.Image, b: Image.Image) -> int:
    diff = ImageChops.difference(a.crop(PEN_BOX), b.crop(PEN_BOX)).convert("L")
    return sum(1 for p in diff.getdata() if p > 60)


async def test_a_code_job_draws_the_pen_mark_at_the_annotation_beat(base, tmp_path):  # noqa: F811
    storyboard = {"id": "sb_pen", "didactic_strategy": "rich_visual",
                  "scenes": [HERO, _code_scene("s2", "circle"), _code_scene("s3", None)]}
    job_dir, rep = await _run_job(base, tmp_path, "job_pen", storyboard)

    scenes = {s["index"]: s for s in rep["scenes"]}
    for i in (2, 3):
        assert scenes[i]["renderer"] == "web" and scenes[i]["template"] == "code", scenes[i]
    assert not [d for d in rep["degradations"] if d["kind"] in ("collision_replaced", "collision_kept", "web_to_pillow")], \
        rep["degradations"]

    video = job_dir / "output.mp4"
    clips = [job_dir / "scenes" / f"scene_{i:03d}.mp4" for i in range(1, 4)]
    s2 = _duration(clips[0])
    s3 = s2 + _duration(clips[1])
    d2, d3 = _duration(clips[1]), _duration(clips[2])
    early_a = _frame(video, s2 + 0.1, tmp_path / "a0.png")
    early_b = _frame(video, s3 + 0.1, tmp_path / "b0.png")
    late_a = _frame(video, s2 + d2 * 0.8, tmp_path / "a1.png")
    late_b = _frame(video, s3 + d3 * 0.8, tmp_path / "b1.png")
    assert late_a.size == (1920, 1080)

    assert _changed(early_a, early_b) < 40, "the pen must not be on the page before its beat"
    drawn = _changed(late_a, late_b)
    assert drawn > 250, f"no pen stroke around `open(path)` at 80 % of the scene (changed pixels: {drawn})"
    print(f"\nMEASURE pen job e2e: changed pixels early={_changed(early_a, early_b)} late={drawn}")

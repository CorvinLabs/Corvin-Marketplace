"""Pen-drawn annotations over a STILL scene through the JOB PIPELINE (ADR-2249 D1 annotation layer, T-0110).

The real ``job_main`` in its own process (storyboard model and TTS voice faked, nothing else): a
``console_still`` scene whose callout carries ``mark: circle`` is rendered next to an identical one
without it. The frames of the real MP4 must be identical before the callout's beat and differ after
it in ONE compact region around the asset hotspot - the pen stroke, anchored to the named spot,
not to model-written coordinates."""
import os

import pytest
from PIL import Image, ImageChops

from tests.test_canvas_job_e2e import HERO, _duration, _frame, _run_job, base  # noqa: F401  (base = fixture)

pytest.importorskip("playwright")
pytestmark = [pytest.mark.e2e, pytest.mark.skipif(not os.path.isdir("/proc"), reason="needs /proc (Linux)")]

NARRATION = ("This is the audit page of the console. Every record is chained to the one before it. "
             "The hash chain card shows that the chain is present and how long it is.")


def _still_scene(sid, mark):
    callout = {"spot": "hash_chain_card", "label": "the chain"}
    if mark:
        callout["mark"] = mark
    return {"id": sid, "kind": "example", "duration_ms": 10000, "narration_text": NARRATION,
            "visual_description": "console screenshot", "template": "console_still",
            "data": {"title": "The audit chain in the console", "asset": "audit_compliance", "callouts": [callout]}}


# the two scenes differ by design in the footer's scene counter ("02 / 03" vs "03 / 03"):
# compare the page above the footer only
PAGE = (0, 0, 1920, 940)


def _diff_region(a: Image.Image, b: Image.Image, thr: int = 60):
    """(changed pixel count, bounding box of the changed pixels or None) above the footer."""
    mask = ImageChops.difference(a.crop(PAGE), b.crop(PAGE)).convert("L").point(lambda p: 255 if p > thr else 0)
    return sum(1 for p in mask.getdata() if p), mask.getbbox()


async def test_a_still_job_draws_the_pen_mark_on_the_hotspot_at_the_callout_beat(base, tmp_path):  # noqa: F811
    storyboard = {"id": "sb_still_pen", "didactic_strategy": "rich_visual",
                  "scenes": [HERO, _still_scene("s2", "circle"), _still_scene("s3", None)]}
    job_dir, rep = await _run_job(base, tmp_path, "job_still_pen", storyboard)

    scenes = {s["index"]: s for s in rep["scenes"]}
    for i in (2, 3):
        assert scenes[i]["renderer"] == "web" and scenes[i]["template"] == "console_still", scenes[i]
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

    early, _ = _diff_region(early_a, early_b)
    assert early < 40, f"the pen must not be on the page before the callout's beat (changed pixels: {early})"
    drawn, box = _diff_region(late_a, late_b)
    assert drawn > 300, f"no pen stroke on the hotspot at 80 % of the scene (changed pixels: {drawn})"
    # one compact region (the stroke around one spot, and its label stepping aside for it), not a
    # shifted or re-laid-out page
    w, h = box[2] - box[0], box[3] - box[1]
    assert w < 520 and h < 260, f"the change is not local to the hotspot: bbox {box}"
    # the hotspot hash_chain_card sits at x=0.40, y=0.47 of the screenshot, which is centred
    # horizontally: the stroke is left of the frame's centre, in the middle band
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    assert 600 < cx < 960 and 350 < cy < 800, f"the stroke is not around the hotspot: centre {(cx, cy)}"
    print(f"\nMEASURE still pen job e2e: changed pixels early={early} late={drawn} bbox={box}")

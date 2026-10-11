"""Canvas through the real render path (ADR-2249 D1, PLAN-0947 P2, T-0110): build_document +
WebSlideRenderer (headless Chromium, the same capture the jobs use), real frames, real pixels.
validate()-only tests are in test_canvas.py and do not count here."""

import copy
from pathlib import Path

import pytest
from PIL import Image, ImageChops

pytest.importorskip("playwright")

from src import web_templates as wt
from src.web_renderer import WebRenderError, WebSlideRenderer
from src.web_timeline import AudioPauses, build_timeline
from tests.canvas_cases import CLEAN, THROUGH_A_BOX

# where the "Database" cylinder is drawn in the settled frame (grid col 9..12, row 2..4 of the 1580x620 canvas)
DB_BOX = (1360, 505, 1745, 705)


@pytest.fixture
async def renderer():
    try:
        async with WebSlideRenderer() as r:
            yield r
    except WebRenderError as e:
        pytest.skip(f"chromium unavailable: {e}")


async def capture(renderer, tmp_path: Path, name: str, data, duration=8.0, timeline=None):
    out = tmp_path / name
    out.mkdir()
    doc = wt.build_document("canvas", data, duration_s=duration, timeline=timeline)
    return await renderer._capture(doc, duration, out, timeline)


def ink(path, box, thr=40):
    """Number of pixels in box that differ clearly from the page background colour at its corner."""
    im = Image.open(path).convert("RGB").crop(box)
    bg = im.getpixel((0, 0))
    return sum(1 for p in im.getdata() if max(abs(p[i] - bg[i]) for i in range(3)) > thr)


async def test_a_clean_canvas_renders_drawn_on_and_passes_the_gate(renderer, tmp_path):
    frames = await capture(renderer, tmp_path, "f", CLEAN)
    assert len(frames) > 60
    assert frames.layout_issues == [], frames.layout_issues
    first, last = frames[0], frames[-1]
    assert ink(first, DB_BOX) == 0, "the database must not exist before its step"
    assert ink(last, DB_BOX) > 3000, "the database cylinder must be drawn in the settled frame"
    # it is drawn on over time: ink is monotone-ish and mid-draw is between none and all
    counts = [ink(frames[i], DB_BOX) for i in range(0, len(frames), 8)]
    assert counts[0] == 0 and counts[-1] > 3000 and any(0 < c < counts[-1] for c in counts)


async def test_the_pen_sprite_is_visible_in_the_real_capture_path(renderer, tmp_path):
    with_pen = await capture(renderer, tmp_path, "pen", CLEAN)
    no_pen = await capture(renderer, tmp_path, "nopen", {**copy.deepcopy(CLEAN), "pen": False})
    assert len(with_pen) == len(no_pen)
    boxes, sizes = [], []
    for a, b in zip(with_pen, no_pen):
        diff = ImageChops.difference(Image.open(a).convert("RGB"), Image.open(b).convert("RGB"))
        boxes.append(diff.getbbox())
        sizes.append(sum(1 for p in diff.convert("L").getdata() if p > 8))
    differing = [i for i, bb in enumerate(boxes) if bb]
    assert len(differing) > 20, "the pen sprite (fill: none) vanished from the frames: the page was rewound"
    # a sprite is a dot with a glow (a few pixels across); a few can run at once, but nothing like a re-layout
    assert max(sizes) < 8000, max(sizes)
    assert boxes[0] is None
    # once every stroke is drawn the pen is gone: the settled frames are the same picture (anti-aliasing of
    # a stroke tip may differ by a few levels in a few pixels because the layer tree differs; a sprite is
    # a 14 px dot at full brightness)
    settled = ImageChops.difference(Image.open(with_pen[-1]).convert("RGB"), Image.open(no_pen[-1]).convert("RGB")).convert("L")
    assert max(settled.getdata()) < 40 and sum(1 for p in settled.getdata() if p > 8) < 100


async def test_a_narration_timeline_cues_the_canvas_steps(renderer, tmp_path):
    d = wt.validate_scene_data("canvas", CLEAN)
    narration = ("A user asks the app server. The app looks in the cache first. On a miss it asks the database. "
                 "A hit skips the database.")
    pauses = AudioPauses(duration=14.0, pause_ends=[2.5, 5.5, 9.0], speech_start=0.0, speech_end=14.0, silent_ratio=0.1)
    tl = build_timeline("canvas", wt.scene_items("canvas", d), narration, pauses, subs=wt.scene_item_subs("canvas", d))
    assert tl.step_times[3] < tl.step_times[5]
    doc = wt.build_document("canvas", CLEAN, duration_s=14.0, timeline=tl)
    assert f"--at:{tl.time_of(5):.3f}s" in doc
    frames = await capture(renderer, tmp_path, "tl", CLEAN, duration=14.0, timeline=tl)
    n = len(frames.schedule)
    at = lambda t: frames[frames.schedule[min(int(t * 30), n - 1)]]  # noqa: E731
    # before the database's cue nothing of it is on screen; after the cue and its draw time it is
    assert ink(at(tl.time_of(5) - 0.1), DB_BOX) == 0
    assert ink(frames[-1], DB_BOX) > 3000
    assert frames.layout_issues == []


async def test_a_canvas_with_an_arrow_through_a_box_fails_the_render_gate(renderer, tmp_path):
    # the validator accepts it (distinct cells, text fits): only the measured page can know
    assert wt.validate_scene_data("canvas", THROUGH_A_BOX)
    frames = await capture(renderer, tmp_path, "bad", THROUGH_A_BOX)
    kinds = {i["type"] for i in frames.layout_issues}
    assert "cv-stroke-shape" in kinds, frames.layout_issues
    stroke = next(i for i in frames.layout_issues if i["type"] == "cv-stroke-shape")
    assert stroke["b"] == "b"


async def test_the_generic_probe_alone_misses_what_the_canvas_probe_finds(renderer, tmp_path):
    frames = await capture(renderer, tmp_path, "bad2", THROUGH_A_BOX)
    generic = [i for i in frames.layout_issues if not i["type"].startswith("cv-")]
    canvas_only = [i for i in frames.layout_issues if i["type"].startswith("cv-")]
    assert canvas_only and len(canvas_only) > len(generic)


async def test_other_templates_are_not_probed_by_the_canvas_gate(renderer, tmp_path):
    out = tmp_path / "c"
    out.mkdir()
    doc = wt.build_document("content", {"title": "Plain", "bullets": ["one", "two"]}, duration_s=4.0)
    frames = await renderer._capture(doc, 4.0, out)
    assert frames.layout_issues == []

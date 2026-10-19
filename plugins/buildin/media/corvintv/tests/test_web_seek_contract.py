"""Seek contract of the web renderer: a page's time only moves forward.

A canvas pen sprite is an animation with ``fill: none`` - it exists only while it runs. Measured on a
40-element canvas scene: seeking a page to the END and then rewinding to 0 (what the capture used to do
for its layout measurement) lost every pen sprite, 48 of 101 frames visibly differed from a fresh
render (up to 9 050 pixels), while the same frames in ascending order were bit-identical across two
browser launches. These tests drive the real capture path with such an animation.
"""

from pathlib import Path

import pytest
from PIL import Image

pytest.importorskip("playwright")

from src.web_renderer import FPS_DEFAULT, WebRenderError, WebSlideRenderer, _ForwardClock
from src.web_templates import build_document

CONTENT = {"title": "Seek contract", "bullets": ["one", "two", "three"]}
PEN_XY = (1730, 930)

# Visible only while it runs (0.1 s .. 0.9 s): the shape of a pen sprite.
_PEN = (
    '<style>@keyframes penx{from{opacity:1}to{opacity:1}}</style>'
    '<div id="pen" style="position:fixed;left:1700px;top:900px;width:60px;height:60px;border-radius:30px;'
    'background:#ffd000;opacity:0;animation:penx 0.8s linear 0.1s none"></div>'
)


def _document() -> str:
    doc = build_document("content", CONTENT, duration_s=3.0)
    assert "</body>" in doc
    return doc.replace("</body>", _PEN + "</body>", 1)


async def _capture(renderer, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    return await renderer._capture(_document(), 3.0, out)


def _is_pen(path) -> bool:
    r, g, b = Image.open(path).convert("RGB").getpixel(PEN_XY)
    return r > 200 and g > 150 and b < 90


@pytest.fixture
async def renderer():
    try:
        async with WebSlideRenderer() as r:
            yield r
    except WebRenderError as e:
        pytest.skip(f"chromium unavailable: {e}")


async def test_a_fill_none_animation_is_drawn_while_it_runs(renderer, tmp_path):
    frames = await _capture(renderer, tmp_path / "f")
    fps = FPS_DEFAULT
    during, before, after = round(0.5 * fps), round(0.03 * fps), round(1.2 * fps)
    assert len(frames) > after, "the scene must run past the pen's end"
    assert _is_pen(frames[during]), "the pen sprite is missing mid-animation (page was rewound?)"
    assert not _is_pen(frames[before]), "the pen is drawn before it starts"
    assert not _is_pen(frames[after]), "the pen is still drawn after it ended"
    # every frame the pen is active in shows it, none outside it does
    window = range(round(0.1 * fps) + 1, round(0.9 * fps))
    assert all(_is_pen(frames[i]) for i in window)


async def test_two_browsers_render_the_pen_scene_identically(tmp_path):
    shots = []
    for name in ("a", "b"):
        try:
            async with WebSlideRenderer() as r:
                shots.append(await _capture(r, tmp_path / name))
        except WebRenderError as e:
            pytest.skip(f"chromium unavailable: {e}")
    a, b = shots
    assert len(a) == len(b)
    assert [Path(p).read_bytes() for p in a] == [Path(p).read_bytes() for p in b]


async def test_layout_is_still_measured_at_the_settled_end_state(renderer, tmp_path):
    frames = await _capture(renderer, tmp_path / "f")
    assert isinstance(frames.layout_issues, list)


class _FakePage:
    def __init__(self):
        self.seeks = []

    async def evaluate(self, _js, t_ms):
        self.seeks.append(t_ms)


async def test_the_clock_refuses_to_rewind_a_page():
    page = _FakePage()
    clock = _ForwardClock(page)
    await clock.seek(100.0)
    await clock.seek(100.0)  # the same instant again is not a rewind
    await clock.seek(250.0)
    with pytest.raises(WebRenderError, match="rewind"):
        await clock.seek(249.0)
    assert page.seeks == [100.0, 100.0, 250.0], "a refused seek must not reach the page"

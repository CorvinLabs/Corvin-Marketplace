"""Renderer behaviour through the real browser (ADR-2238, PLAN-0940 P3)."""

import hashlib
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat

pytest.importorskip("playwright")

from src.web_renderer import WebRenderError, WebSlideRenderer
from src.web_templates import WebSceneError

DIAGRAM = {"title": "Pipeline", "nodes": [{"label": "A"}, {"label": "B"}, {"label": "C"}], "highlight": 1}


def _sha(paths):
    return [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths]


@pytest.fixture
async def renderer():
    try:
        async with WebSlideRenderer() as r:
            yield r
    except WebRenderError as e:
        pytest.skip(f"chromium unavailable: {e}")


async def test_two_renders_are_bit_identical_and_animated(renderer, tmp_path):
    a = await renderer.render("diagram", DIAGRAM, 6.0, tmp_path / "a")
    b = await renderer.render("diagram", DIAGRAM, 6.0, tmp_path / "b")
    assert len(a) == len(b) > 30, "an animated slide must yield many frames"
    assert _sha(a) == _sha(b)
    assert len(set(_sha(a))) > 20, "frames must actually change over time"
    first, last = Image.open(a[0]).convert("RGB"), Image.open(a[-1]).convert("RGB")
    assert first.size == (1920, 1080)
    assert ImageChops.difference(first, last).getbbox() is not None
    assert ImageStat.Stat(last.convert("L")).stddev[0] > 8


async def test_frame_count_stops_at_the_last_animation(renderer, tmp_path):
    short = await renderer.render("quote", {"quote": "q"}, 1.0, tmp_path / "s")
    long = await renderer.render("quote", {"quote": "q"}, 30.0, tmp_path / "l")
    assert len(short) <= 31  # capped by the 1 s narration
    assert len(long) < 30 * 30, "frames end with the entrance animations, not the narration"


async def test_a_font_that_fails_to_load_stops_the_render(renderer, tmp_path, monkeypatch):
    """Chromium falls back to a system font silently; the renderer must not."""
    import re
    from src import web_templates as wt
    good = wt._font_faces()
    broken = re.sub(r"(font-family:'Instrument Sans';[^}]*?base64,)[A-Za-z0-9+/=]+", r"\1AAAA", good, count=1)
    assert broken != good
    monkeypatch.setattr(wt, "_font_faces", lambda: broken)
    with pytest.raises(WebRenderError, match="Instrument Sans"):
        await renderer.render("hero", {"title": "Agentic"}, 2.0, tmp_path / "h")


async def test_light_theme_changes_the_background(renderer, tmp_path):
    dark = await renderer.render("quote", {"quote": "q"}, 2.0, tmp_path / "d", theme="dark")
    light = await renderer.render("quote", {"quote": "q"}, 2.0, tmp_path / "l", theme="light")
    assert sum(Image.open(dark[-1]).convert("RGB").getpixel((10, 10))) < 120
    assert sum(Image.open(light[-1]).convert("RGB").getpixel((10, 10))) > 600


async def test_invalid_input_is_rejected_before_rendering(renderer, tmp_path):
    with pytest.raises(WebSceneError):
        await renderer.render("nope", {}, 2.0, tmp_path / "x")
    with pytest.raises(WebSceneError):
        await renderer.render("hero", {"title": "t"}, 61.0, tmp_path / "x")
    with pytest.raises(WebSceneError):
        await renderer.render("hero", {"title": "t"}, float("nan"), tmp_path / "x")
    assert not list((tmp_path / "x").glob("*.png")) if (tmp_path / "x").exists() else True


async def test_refuses_a_non_empty_frame_directory(renderer, tmp_path):
    d = tmp_path / "used"
    d.mkdir()
    (d / "00000.png").write_bytes(b"x")
    with pytest.raises(WebRenderError, match="not empty"):
        await renderer.render("hero", {"title": "t"}, 2.0, d)


async def test_no_network_and_no_javascript_in_the_render_context(renderer, tmp_path):
    """A document with an external image and a script: the request is aborted, the script never runs."""
    from src import web_renderer as wr

    seen = []
    doc = ('<!doctype html><html><body style="background:#000">'
           '<img src="https://example.com/beacon.png"><script>document.body.style.background="#fff"</script>'
           '</body></html>')
    context = await renderer._browser.new_context(viewport=wr.VIEWPORT, java_script_enabled=False)
    try:
        async def handler(route):
            seen.append(route.request.url)
            await route.abort()
        await context.route("**/*", handler)
        page = await context.new_page()
        await page.set_content(doc, wait_until="load")
        assert await page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(0, 0, 0)"
        assert seen == ["https://example.com/beacon.png"]
    finally:
        await context.close()
    # and the production capture path uses exactly these settings
    import inspect
    src = inspect.getsource(wr.WebSlideRenderer._capture)
    assert "java_script_enabled=False" in src and 'route("**/*"' in src and "route.abort()" in src


async def test_closed_renderer_refuses_work(tmp_path):
    r = WebSlideRenderer()
    with pytest.raises(WebRenderError, match="not open"):
        await r.render("hero", {"title": "t"}, 2.0, tmp_path / "x")

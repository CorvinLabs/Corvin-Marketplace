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


async def test_renders_in_separate_browsers_are_bit_identical_and_animated(tmp_path):
    """Two independent browser instances, as two jobs or two hosts would use.
    Before the compositor flags this differed in up to 54 of 149 frames."""
    paths = []
    for name in ("a", "b"):
        try:
            async with WebSlideRenderer() as r:
                paths.append(await r.render("diagram", DIAGRAM, 6.0, tmp_path / name))
        except WebRenderError as e:
            pytest.skip(f"chromium unavailable: {e}")
    a, b = paths
    assert len(a) == len(b) > 30, "an animated slide must yield many frames"
    assert _sha(a) == _sha(b)
    assert len(set(_sha(a))) > 20, "frames must actually change over time"
    first, last = Image.open(a[0]).convert("RGB"), Image.open(a[-1]).convert("RGB")
    assert first.size == (1920, 1080)
    assert ImageChops.difference(first, last).getbbox() is not None
    assert ImageStat.Stat(last.convert("L")).stddev[0] > 8


async def test_short_narration_still_gets_the_complete_animation(renderer, tmp_path):
    """A 1 s narration must not freeze the odometer mid-roll (review finding 3)."""
    data = {"value": 98765, "label": "frozen?", "caption": "c"}
    short = await renderer.render("stat", data, 1.0, tmp_path / "s")
    long = await renderer.render("stat", data, 30.0, tmp_path / "l")
    assert len(short) > 30, "frames must cover the whole entrance animation"
    assert len(long) < 30 * 30, "frames end with the animation, not the narration"
    assert _sha([short[-1]]) == _sha([long[-1]]), "the final state must be the same, whatever the narration length"


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


async def test_production_capture_blocks_network_and_scripts(renderer, tmp_path, monkeypatch):
    """Feeds a hostile document through WebSlideRenderer.render itself (review finding 6):
    the external request must never arrive and the script must never run."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from src import web_renderer as wr
    from src import web_templates as wt

    hits = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    doc = (f'<!doctype html><html><head><style>{wt._font_faces()}'
           f'body{{margin:0;background:#000;font-family:"Instrument Sans"}}'
           f'@keyframes f{{from{{opacity:0}}}}p{{animation:f 300ms both}}</style>'
           f'<link rel="stylesheet" href="{url}/style.css"></head><body>'
           f'<img src="{url}/beacon.png"><p>x</p>'
           f'<script>document.body.style.background="#fff";fetch("{url}/fetch")</script></body></html>')
    monkeypatch.setattr(wr, "build_document", lambda *a, **k: doc)
    try:
        frames = await renderer.render("hero", {"title": "t"}, 1.0, tmp_path / "hostile")
    finally:
        srv.shutdown()
    assert hits == [], f"the render page reached the network: {hits}"
    # (the aborted <img> leaves a broken-image icon top-left; sample the open background)
    last = Image.open(frames[-1]).convert("RGB")
    assert sum(last.getpixel((960, 900))) < 30 and sum(last.getpixel((1900, 1060))) < 30, "the page script ran"


async def test_closed_renderer_refuses_work(tmp_path):
    r = WebSlideRenderer()
    with pytest.raises(WebRenderError, match="not open"):
        await r.render("hero", {"title": "t"}, 2.0, tmp_path / "x")

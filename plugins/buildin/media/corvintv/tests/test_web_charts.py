"""Data-visual templates (line, donut, flow, timeline, cycle, layers) and their
geometry and ambient-loop contract (ADR-2238 amendment 2026-10-09)."""

import asyncio
import hashlib
import math

import pytest

from src import web_templates as wt
from src.web_geometry import layer_dag, monotone_path, nice_ticks, order_layers
from src.web_templates import WebSceneError, build_document, validate_scene_data


# ── geometry ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lo,hi,expected", [
    (0, 820, [0, 200, 400, 600, 800, 1000]),
    (0, 1, [0, 0.2, 0.4, 0.6, 0.8, 1.0]),
    (-35, 80, [-40, -20, 0, 20, 40, 60, 80]),
    (5, 5, [5, 6, 7, 8, 9, 10]),
])
def test_nice_ticks_cover_the_range_with_round_steps(lo, hi, expected):
    assert nice_ticks(lo, hi, 5) == pytest.approx(expected)


def test_monotone_curve_never_overshoots_between_points():
    pts = [(0, 100), (100, 100), (200, 0), (300, 0), (400, 50)]
    path = monotone_path(pts)
    # sample every cubic segment: y must stay within the segment's endpoint range
    segs = path[1:].split("C")
    x0, y0 = map(float, segs[0].split(","))
    for seg in segs[1:]:
        (c1x, c1y), (c2x, c2y), (x1, y1) = [tuple(map(float, p.split(","))) for p in seg.split()]
        lo, hi = min(y0, y1), max(y0, y1)
        for k in range(1, 20):
            t = k / 20
            y = (1 - t) ** 3 * y0 + 3 * (1 - t) ** 2 * t * c1y + 3 * (1 - t) * t ** 2 * c2y + t ** 3 * y1
            assert lo - 1e-6 <= y <= hi + 1e-6
        x0, y0 = x1, y1


def test_dag_layering_and_cycle_refusal():
    layer = layer_dag(["a", "b", "c", "d"], [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])
    assert layer == {"a": 0, "b": 1, "c": 1, "d": 2}
    assert [g for g in order_layers(["a", "b", "c", "d"], [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")], layer)] \
        == [["a"], ["b", "c"], ["d"]]
    with pytest.raises(ValueError, match="cycle"):
        layer_dag(["a", "b"], [("a", "b"), ("b", "a")])


# ── validation ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,data,msg", [
    ("line", {"title": "t", "labels": ["a", "b"], "series": [{"values": [1, 2]}]}, "3-12"),
    ("line", {"title": "t", "labels": ["a", "b", "c"], "series": [{"values": [1, 2]}]}, "3-3"),
    ("line", {"title": "t", "labels": ["a", "b", "c"], "series": [{"values": [1, 2, 3]}, {"values": [1, 2, 3]}]}, "name"),
    ("donut", {"title": "t", "segments": [{"label": "a", "value": 0}, {"label": "b", "value": 0}]}, "> 0"),
    ("donut", {"title": "t", "segments": [{"label": "a", "value": -1}, {"label": "b", "value": 2}]}, ">= 0"),
    ("flow", {"title": "t", "nodes": [{"id": "A!", "label": "a"}, {"id": "b", "label": "b"}],
              "edges": [{"from": "A!", "to": "b"}]}, "id must match"),
    ("flow", {"title": "t", "nodes": [{"id": "a", "label": "a"}, {"id": "b", "label": "b"}],
              "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}]}, "cycle"),
    ("flow", {"title": "t", "nodes": [{"id": "a", "label": "a"}, {"id": "b", "label": "b"}],
              "edges": [{"from": "a", "to": "zz"}]}, "node ids"),
    ("flow", {"title": "t", "nodes": [{"id": "a", "label": "a"}, {"id": "a", "label": "b"}],
              "edges": [{"from": "a", "to": "a"}]}, "duplicate"),
    ("flow", {"title": "t", "nodes": [{"id": f"n{i}", "label": "x"} for i in range(7)],
              "edges": [{"from": f"n{i}", "to": f"n{i + 1}"} for i in range(6)]}, "5 columns"),
    ("cycle", {"title": "t", "steps": [{"label": "a"}, {"label": "b"}]}, "3-6"),
    ("timeline", {"title": "t", "events": [{"when": "1", "label": "a"}], "current": 0}, "2-6"),
    ("layers", {"title": "t", "layers": [{"label": "a", "html": "<b>"}, {"label": "b"}]}, "unknown field"),
])
def test_invalid_data_is_refused(name, data, msg):
    with pytest.raises(WebSceneError, match=msg):
        validate_scene_data(name, data)


def test_validated_data_round_trips():
    """The strict storyboard path stores validate_scene_data()'s output and the
    renderer validates it again — normalised data must still be valid."""
    for name in ("line", "donut", "flow", "timeline", "cycle", "layers"):
        from tests.test_web_templates import SAMPLES
        once = validate_scene_data(name, SAMPLES[name])
        assert validate_scene_data(name, once) == once


def test_donut_with_percent_unit_shows_one_share_column():
    doc = build_document("donut", {"title": "t", "unit": "%", "segments": [
        {"label": "a", "value": 60}, {"label": "b", "value": 40}]}, duration_s=6)
    assert 'class="lg-v"' not in doc and 'class="lg-p"' in doc


def test_line_ticks_use_locale_and_enough_decimals():
    doc = build_document("line", {"title": "t", "labels": ["a", "b", "c"], "locale": "de",
                                  "series": [{"values": [0.1, 0.5, 0.9]}]}, duration_s=6)
    assert ">0,2<" in doc  # step 0.2 needs one decimal; German comma


# ── ambient loop (real Chromium) ────────────────────────────────────────────

playwright = pytest.importorskip("playwright.async_api")


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("name", ["flow", "cycle", "diagram"])
def test_ambient_loop_is_one_seamless_period(name, tmp_path):
    """frames[loop_start:] is exactly one period: the frame one period after
    loop_start is pixel-identical to frame loop_start, so repeating the period
    has no jump — and the period really moves (it is not a held still)."""
    from src.web_renderer import WebSlideRenderer
    from tests.test_web_templates import SAMPLES

    data = SAMPLES[name]

    async def go():
        async with WebSlideRenderer(fps=12) as r:
            frames = await r.render(name, data, 6.0, tmp_path / "a")
            assert frames.loop_start is not None
            period = len(frames) - frames.loop_start
            assert period in (24, 48)  # the longest ambient duration: 2 s or 4 s at 12 fps
            # render the same document once more, sampled one period later
            doc = wt.build_document(name, data, duration_s=6.0)
            ctx = await r._browser.new_context(viewport={"width": 1920, "height": 1080},
                                               java_script_enabled=False)
            page = await ctx.new_page()
            await page.set_content(doc, wait_until="load")
            await page.evaluate("() => document.fonts.ready")
            shots = []
            for idx in (frames.loop_start, frames.loop_start + period):
                await page.evaluate("t => { for (const a of document.getAnimations()) { a.pause(); a.currentTime = t; } }",
                                    idx * 1000 / 12)
                cdp = await ctx.new_cdp_session(page)
                import base64
                shot = await cdp.send("Page.captureScreenshot", {"format": "png"})
                shots.append(hashlib.sha256(base64.b64decode(shot["data"])).hexdigest())
            await ctx.close()
            return frames, shots

    frames, (h_start, h_wrap) = asyncio.run(go())
    assert h_start == h_wrap
    loop_hashes = {_sha(f) for f in frames[frames.loop_start:]}
    assert len(loop_hashes) > 10  # motion, not a held frame


def test_slide_without_ambient_motion_has_no_loop(tmp_path):
    from src.web_renderer import WebSlideRenderer

    async def go():
        async with WebSlideRenderer(fps=12) as r:
            return await r.render("quote", {"quote": "q"}, 4.0, tmp_path / "q")

    assert asyncio.run(go()).loop_start is None

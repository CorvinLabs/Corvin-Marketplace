"""Penpot SVG import (ADR-2257 strand A, T-0187 / T-0188): parser, safety, style derivation, render."""

import asyncio
import io
import re
from pathlib import Path

import pytest

import penpot_import as pi
from style_pack import StyleError, validate_style

FIXTURE = Path(__file__).parent / "fixtures" / "penpot_board.svg"
NS = 'xmlns="http://www.w3.org/2000/svg"'


@pytest.fixture(scope="module")
def board() -> bytes:
    return FIXTURE.read_bytes()


def svg(body: str, w: int = 400, h: int = 300, extra: str = "") -> bytes:
    return f'<svg {NS} width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none" {extra}>{body}</svg>'.encode()


# ── real export ─────────────────────────────────────────────────────────────

def test_real_penpot_export_is_read_completely(board):
    d = pi.parse_design(board)
    assert (d.width, d.height, d.background) == (1920.0, 1080.0, "#ffffff")
    assert sorted(s.kind for s in d.shapes) == ["ellipse", "rect", "rect", "rect", "rect", "rect", "text", "text"]
    logo = next(s for s in d.shapes if s.kind == "ellipse")
    assert (logo.x, logo.y, logo.w, logo.h, logo.fill) == (200.0, 200.0, 100.0, 100.0, "#0066cc")
    texts = {s.text: s.font_size for s in d.shapes if s.kind == "text"}
    assert texts == {"Beispiel Video-Folie": 48.0, "Design System Template": 32.0}
    assert {s.fill for s in d.shapes} == {"#0066cc", "#ff6600", "#cccccc", "#333333", "#ffffff"}
    assert d.dropped == {}


def test_clean_svg_carries_nothing_from_the_upload(board):
    out = pi.to_svg(pi.parse_design(board))
    assert "localhost" not in out and "http://localhost" not in out and "@font-face" not in out
    assert "<style" not in out and "href" not in out and "<script" not in out
    assert out.count("<rect") == 6 and out.count("<ellipse") == 1 and out.count("<text") == 2


# ── hostile input ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,fragment", [
    (b"", "empty"),
    (b"<html/>", "not an SVG"),
    (b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "b">]><svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"/>', "document type"),
    (b'<!doctype svg><svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"/>', "document type"),
    (b"<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'>\x00</svg>", "encoding"),
    (b"<svg xmlns='http://www.w3.org/2000/svg' width='40'", "malformed"),
])
def test_refused_inputs(raw, fragment):
    with pytest.raises(pi.PenpotImportError) as e:
        pi.parse_design(raw)
    assert fragment in str(e.value)
    assert isinstance(e.value, StyleError)


def test_wrong_namespace_and_size_limits():
    with pytest.raises(pi.PenpotImportError):
        pi.parse_design(b'<svg xmlns="http://example.com/x" width="40" height="40"><rect width="1" height="1"/></svg>')
    with pytest.raises(pi.PenpotImportError, match="no usable size"):
        pi.parse_design(f'<svg {NS}><rect width="1" height="1"/></svg>'.encode())
    for w, h in ((8, 100), (100, 30000)):
        with pytest.raises(pi.PenpotImportError, match="size is outside"):
            pi.parse_design(svg('<rect width="4" height="4" fill="#ff0000"/>', w, h))
    with pytest.raises(pi.PenpotImportError, match="larger than 8 MB"):
        pi.parse_design(b"<svg" + b" " * (pi.MAX_SVG_BYTES + 1))


def test_too_many_shapes_and_deep_nesting():
    many = "".join('<rect width="2" height="2" fill="#ff0000"/>' for _ in range(pi.MAX_SHAPES + 1))
    with pytest.raises(pi.PenpotImportError, match="too many shapes"):
        pi.parse_design(svg(many))
    deep = "<g>" * 70 + '<rect width="2" height="2" fill="#ff0000"/>' + "</g>" * 70
    with pytest.raises(pi.PenpotImportError, match="nested"):
        pi.parse_design(svg(deep))


def test_hostile_content_is_dropped_and_never_reaches_the_output():
    body = (
        '<style>@import url(http://evil.example/x.css); rect{fill:red}</style>'
        '<image href="http://evil.example/p.png" width="50" height="50"/>'
        '<foreignObject width="50" height="50"><div onclick="x()">hi</div></foreignObject>'
        '<use href="#a"/><script>alert(1)</script>'
        '<rect width="50" height="50" fill="url(#grad)" onload="x()"/>'
        '<rect width="60" height="60" fill="#12ab34" style="fill: #12ab34"/>'
        '<path d="M0 0 L10 10 &lt;/path&gt;&lt;script&gt;" fill="#ff0000"/>'
        '<path d="M0 0 L10 10 Z" fill="#00ff00"/>'
        '<text x="10" y="20" style="font-family: x;} body{background:url(http://evil.example)">'
        '&lt;/text&gt;&lt;script&gt;alert(1)&lt;/script&gt;</text>'
    )
    d = pi.parse_design(svg(body, extra='onload="x()"'))
    out = pi.to_svg(d)
    for bad in ("evil", "<script", "onload", "onclick", "href", "<image", "foreignObject", "<use", "@import", "url("):
        assert bad not in out
    assert out.count("<script") == 0
    assert d.dropped["image"] == 1 and d.dropped["foreignObject"] == 1 and d.dropped["use"] == 1
    assert d.dropped["paint"] == 1 and d.dropped["malformed"] == 1
    assert re.fullmatch(r'<svg xmlns="http://www.w3.org/2000/svg"[^<]*>(<[^<>]*>[^<>]*)*</svg>', out)
    assert "&lt;/text&gt;&lt;script&gt;" in out  # text stays text: escaped, never markup


def test_bad_numbers_and_controls_are_refused_per_shape():
    body = ('<rect x="NaN" y="0" width="5" height="5" fill="#ff0000"/>'
            '<rect x="0" y="0" width="1e999" height="5" fill="#ff0000"/>'
            '<rect x="0" y="0" width="30" height="30" fill="#00aa00"/>'
            '<text x="5" y="50" style="font-size: 20px; fill: #000">a‮b\u200fc</text>')
    d = pi.parse_design(svg(body))
    assert d.dropped["malformed"] == 2
    assert [s.kind for s in d.shapes] == ["rect", "text"]
    assert d.shapes[1].text == "abc"


def test_text_is_capped():
    d = pi.parse_design(svg(f'<text x="5" y="50" style="fill:#000">{"x" * (pi.MAX_TEXT + 50)}</text>'))
    assert len(d.shapes[0].text) == pi.MAX_TEXT and d.dropped["text_truncated"] == 1


def test_transforms_compose_and_inherited_fill():
    body = ('<g transform="matrix(1,0,0,1,10,20)" style="fill: rgb(10, 20, 30)">'
            '<rect x="1" y="2" width="3" height="4" transform="matrix(2,0,0,2,0,0)"/></g>')
    r = pi.parse_design(svg(body)).shapes[0]
    assert r.fill == "#0a141e"
    assert r.matrix == (2.0, 0.0, 0.0, 2.0, 10.0, 20.0)


# ── review findings (fidelity and load) ─────────────────────────────────────

def test_viewbox_origin_and_size_are_the_coordinate_space():
    d = pi.parse_design(svg('<rect x="100" y="200" width="800" height="600" fill="#101020"/>'
                            '<rect x="900" y="900" width="50" height="50" fill="#ff0000"/>', 100, 100,
                            'viewBox="100 200 800 600"').replace(b'width="100" height="100" viewBox="0 0 100 100"', b'width="100" height="100"'))
    assert (d.ox, d.oy, d.width, d.height) == (100.0, 200.0, 800.0, 600.0)
    assert d.background == "#101020"  # the full-viewBox rectangle at the origin is the page
    out = pi.to_svg(d)
    assert 'viewBox="100 200 800 600"' in out and '<rect x="100" y="200" width="800" height="600" fill="#101020"/>' in out


def test_percent_size_with_a_viewbox_is_accepted():
    raw = f'<svg {NS} width="100%" height="100%" viewBox="0 0 640 360"><rect width="10" height="10" fill="#ff0000"/></svg>'.encode()
    assert (pi.parse_design(raw).width, pi.parse_design(raw).height) == (640.0, 360.0)


def test_group_opacity_and_stroke_width_are_inherited():
    body = ('<g opacity="0.5" fill-opacity="0.4" stroke="#000000" stroke-width="7">'
            '<g opacity="0.5"><rect width="9" height="9" fill="#ff0000"/></g></g>')
    sh = pi.parse_design(svg(body)).shapes[0]
    assert (sh.opacity, sh.fill_opacity, sh.stroke_width) == (0.25, 0.4, 7.0)
    assert 'opacity="0.25"' in pi.to_svg(pi.parse_design(svg(body)))


def test_text_anchor_survives():
    d = pi.parse_design(svg('<text x="200" y="50" text-anchor="middle" style="fill:#000">Centre</text>'
                            '<text x="5" y="90" text-anchor="evil" style="fill:#000">x</text>'))
    assert [t.anchor for t in d.shapes] == ["middle", "start"]
    assert 'text-anchor="middle"' in pi.to_svg(d)


def test_rect_with_only_one_radius_uses_it_for_both():
    d = pi.parse_design(svg('<rect width="80" height="60" rx="12" fill="#ff0000"/><rect width="9" height="9" fill="#00ff00"/>'))
    assert (d.shapes[0].rx, d.shapes[0].ry) == (12.0, 12.0)
    assert (d.shapes[1].rx, d.shapes[1].ry) == (0.0, 0.0)


def test_total_path_data_is_budgeted():
    path = f'<path d="M0 0 L{"1 1 " * 4000}Z" fill="#ff0000"/>'  # ~16 000 characters each
    ok = pi.parse_design(svg(path * 20))
    assert ok.path_chars < pi.MAX_PATH_TOTAL
    with pytest.raises(pi.PenpotImportError, match="too much path data"):
        pi.parse_design(svg(path * 40))


def test_extreme_proportions_are_refused_before_rendering():
    for w, h in ((16, 20000), (20000, 16)):
        with pytest.raises(pi.PenpotImportError, match="proportions"):
            pi.parse_design(svg('<rect width="4" height="4" fill="#ff0000"/>', w, h))


def test_style_ranking_ignores_what_is_off_canvas_and_transparent():
    body = ('<rect x="-900000" y="0" width="1000000" height="300" fill="#3366cc"/>'
            '<rect x="10" y="10" width="120" height="80" fill="#cc2200"/>'
            '<rect x="0" y="0" width="400" height="300" fill="#00aa00" opacity="0.01"/>')
    st = pi.import_penpot(svg(body), "x.svg").style
    assert st.tokens["light"]["accent"].lower() != "#3366cc" and st.tokens["dark"]["accent"].lower() != "#3366cc"


def test_a_full_canvas_dark_rectangle_without_a_class_is_the_background():
    body = ('<rect width="400" height="300" fill="#101020"/>'
            '<rect x="20" y="20" width="100" height="60" fill="#ff8800"/>'
            '<text x="20" y="200" style="font-size: 24px; fill: #f5f5f5">Hi</text>')
    st = pi.import_penpot(svg(body), "dark.svg").style
    assert st.default_theme == "dark" and st.tokens["dark"]["bg"] == "#101020"


# ── style derivation ────────────────────────────────────────────────────────

def test_style_from_real_export(board):
    res = pi.import_penpot(board, "Brand Board.svg")
    st = res.style
    assert st.name == "Brand Board" and st.source["kind"] == "penpot" and st.default_theme == "light"
    assert st.tokens["light"]["accent"] == "#0066cc" and st.tokens["light"]["bg"] == "#ffffff"
    assert st.fonts[0]["from"] == "sourcesanspro" and st.fonts[0]["to"] == "Instrument Sans"
    assert pi.NOT_IMPORTED in st.warnings
    assert re.fullmatch(r"[0-9a-f]{64}", st.source["sha256"])
    validate_style(st)


def test_dark_design_gets_dark_default_theme():
    body = ('<rect class="frame-background" x="0" y="0" width="400" height="300" style="fill: rgb(14, 19, 32)"/>'
            '<rect x="20" y="20" width="200" height="120" fill="#ff8800"/>'
            '<text x="20" y="200" style="font-size: 24px; fill: #f5f5f5; font-family: Georgia">Hello</text>')
    st = pi.import_penpot(svg(body), "dark.svg").style
    assert st.default_theme == "dark" and st.tokens["dark"]["bg"] == "#0e1320"
    assert st.fonts[0]["to"] == "Newsreader"


def test_grey_only_design_uses_neutral_accent_and_says_so():
    body = '<rect width="300" height="200" fill="#999999"/><rect x="5" y="5" width="30" height="30" fill="#bbbbbb"/>'
    res = pi.import_penpot(svg(body), "grey.svg")
    assert any("neutral accent" in w for w in res.style.warnings)


def test_dropped_elements_are_named_in_the_warnings():
    res = pi.import_penpot(svg('<image href="x" width="1" height="1"/><rect width="9" height="9" fill="#ff0000"/>'), "a.svg")
    assert any(w.startswith("Not imported: 1 image") for w in res.style.warnings)


def test_no_shapes_is_a_clear_refusal():
    with pytest.raises(pi.PenpotImportError, match="No shapes"):
        pi.import_penpot(svg("<g/>"), "empty.svg")


# ── real browser (T-0188) ───────────────────────────────────────────────────

def test_render_matches_the_penpot_svg_in_chromium(board):
    pytest.importorskip("playwright")
    from PIL import Image, ImageChops
    from web_renderer import WebRenderError, WebSlideRenderer

    design = pi.parse_design(board)
    html_doc, w, h = pi.to_html(design)

    async def both():
        async with WebSlideRenderer() as r:
            mine = await r.render_html_png(html_doc, w, h, timeout_s=30)
            orig = await r.render_html_png(
                '<!doctype html><html><body style="margin:0">' + board.decode() + "</body></html>", 1920, 1080,
                timeout_s=30)
        return mine, orig

    try:
        mine, orig = asyncio.run(both())
    except WebRenderError as e:
        pytest.skip(f"no usable Chromium: {e}")
    a, b = (Image.open(io.BytesIO(x)).convert("RGB") for x in (mine, orig))
    assert a.size == b.size == (1920, 1080)
    diff = ImageChops.difference(a, b).point(lambda v: 255 if v > 24 else 0).convert("L")
    # shapes are identical; text is placed identically (same boxes) but the browser's fallback face for the
    # unavailable Penpot font differs, so the only differing pixels lie inside the two text boxes
    for box in ((0, 0, 1920, 395), (0, 541, 1920, 1080), (0, 0, 460, 1080), (1458, 0, 1920, 1080)):
        assert diff.crop(box).getbbox() is None, box
    assert a.getpixel((200, 200)) == (0, 102, 204)  # the logo ellipse
    assert a.getpixel((160, 960)) == (0, 102, 204)  # first swatch
    assert sum(1 for _ in a.crop((460, 395, 1458, 541)).getdata() if _ != (255, 255, 255)) > 1000  # text drawn

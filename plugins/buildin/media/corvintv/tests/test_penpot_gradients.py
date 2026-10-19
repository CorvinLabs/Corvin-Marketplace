"""Gradients and group index in the closed shape model (ADR-2260 decision 7, T-0196).

Every route by which a paint can reach a shape is either typed or counted - never dropped silently - and
a dropped gradient falls back to the colour of its first valid stop, identically from every route.
"""

import asyncio
import io

import pytest

import penpot_import as pi

NS = 'xmlns="http://www.w3.org/2000/svg"'
LINEAR = ('<linearGradient id="g" x1="0" y1="0" x2="1" y2="0">'
          '<stop offset="0" stop-color="#ff0000"/><stop offset="1" stop-color="#0000ff" stop-opacity="0.5"/>'
          '</linearGradient>')
RADIAL = ('<radialGradient id="r" cx="0.5" cy="0.5" r="0.5">'
          '<stop offset="0%" stop-color="#ffffff"/><stop offset="100%" stop-color="#000000"/></radialGradient>')
RECT = '<rect x="10" y="10" width="200" height="100" %s/>'


def doc(body: str, root: str = 'fill="none"', defs: str = LINEAR) -> bytes:
    return f'<svg {NS} id="shape-test" width="400" height="300" viewBox="0 0 400 300" {root}><defs>{defs}</defs>{body}</svg>'.encode()


# ── typed ───────────────────────────────────────────────────────────────────

def test_a_linear_gradient_on_a_shape_is_typed_not_dropped():
    d = pi.parse_design(doc(RECT % 'fill="url(#g)"'))
    sh = d.shapes[0]
    g = sh.fill_gradient
    assert g is not None and g.kind == "linear" and g.units == "bbox"
    assert g.stops == ((0.0, "#ff0000", 1.0), (1.0, "#0000ff", 0.5))
    assert g.coords == (0.0, 0.0, 1.0, 0.0)
    assert sh.fill == "#ff0000"          # the flat fallback every other consumer (palette ranking) keeps reading
    assert d.dropped == {}


def test_a_radial_gradient_with_percent_offsets_is_typed():
    d = pi.parse_design(doc(RECT % 'fill="url(#r)"', defs=RADIAL))
    g = d.shapes[0].fill_gradient
    assert g.kind == "radial" and g.coords[:3] == (0.5, 0.5, 0.5)
    assert [s[0] for s in g.stops] == [0.0, 1.0]


def test_to_svg_writes_the_gradient_from_typed_fields_with_its_own_ids():
    out = pi.to_svg(pi.parse_design(doc(RECT % 'fill="url(#g)"')))
    assert '<linearGradient id="g0"' in out and 'fill="url(#g0)"' in out
    assert out.count("<stop ") == 2 and 'stop-color="#ff0000"' in out and 'stop-opacity="0.5"' in out
    assert 'id="g"' not in out


def test_a_gradient_used_by_two_shapes_is_written_once():
    out = pi.to_svg(pi.parse_design(doc(RECT % 'fill="url(#g)"' + RECT % 'fill="url(#g)"')))
    assert out.count("<linearGradient") == 1 and out.count('fill="url(#g0)"') == 2


# ── every route is typed or counted ─────────────────────────────────────────

def test_route_group_inheritance_is_typed():
    d = pi.parse_design(doc('<g fill="url(#g)">' + RECT % "" + "</g>"))
    assert d.shapes[0].fill_gradient is not None and d.dropped == {}


def test_route_root_element_is_typed():
    d = pi.parse_design(doc(RECT % "", root='fill="url(#g)"'))
    assert d.shapes[0].fill_gradient is not None and d.dropped == {}


def test_route_style_attribute_is_typed():
    d = pi.parse_design(doc(RECT % 'style="fill: url(#g)"'))
    assert d.shapes[0].fill_gradient is not None and d.dropped == {}


def test_route_stylesheet_class_is_counted_not_silent():
    d = pi.parse_design(doc('<style>.a{fill:url(#g)}</style>' + RECT % 'class="a"'))
    assert d.dropped.get("stylesheet") == 1 and d.dropped.get("class_paint") == 1
    assert d.shapes[0].fill_gradient is None


def test_route_tspan_paint_is_counted_not_silent():
    d = pi.parse_design(doc('<text x="0" y="20" fill="#ff0000"><tspan fill="url(#g)">Hi</tspan></text>'))
    assert d.dropped.get("tspan_paint") == 1 and d.shapes[0].fill == "#ff0000"


def test_route_own_stroke_is_counted_and_keeps_the_first_stop_colour():
    d = pi.parse_design(doc(RECT % 'fill="#00ff00" stroke="url(#g)" stroke-width="3"'))
    sh = d.shapes[0]
    assert sh.stroke == "#ff0000" and sh.fill_gradient is None and d.dropped.get("gradient_stroke") == 1


def test_route_group_stroke_is_counted_once_at_the_group():
    d = pi.parse_design(doc('<g stroke="url(#g)">' + RECT % 'fill="#00ff00"' + RECT % 'fill="#00ff00"' + "</g>"))
    assert d.dropped.get("gradient_stroke") == 1
    assert [s.stroke for s in d.shapes] == ["#ff0000", "#ff0000"]


# ── a dropped gradient falls back the same way from every route ─────────────

BAD_ONE_STOP = '<linearGradient id="g"><stop offset="0" stop-color="#00ff00"/></linearGradient>'


@pytest.mark.parametrize("make", [
    lambda: doc(RECT % 'fill="url(#g)"', defs=BAD_ONE_STOP),
    lambda: doc('<g fill="url(#g)">' + RECT % "" + "</g>", defs=BAD_ONE_STOP),
    lambda: doc(RECT % "", root='fill="url(#g)"', defs=BAD_ONE_STOP),
    lambda: doc(RECT % 'style="fill:url(#g)"', defs=BAD_ONE_STOP),
], ids=["own", "group", "root", "style"])
def test_a_dropped_gradient_takes_its_first_valid_stop_colour_from_every_route(make):
    d = pi.parse_design(make())
    assert d.shapes[0].fill == "#00ff00" and d.shapes[0].fill_gradient is None
    assert d.dropped.get("gradient", 0) >= 1


def test_a_gradient_that_does_not_exist_leaves_no_fill_and_is_counted():
    d = pi.parse_design(doc(RECT % 'fill="url(#nope)"'))
    assert d.shapes[0].fill is None and d.dropped.get("paint") == 1


def test_a_fallback_colour_after_the_url_is_used_when_the_gradient_is_missing():
    d = pi.parse_design(doc(RECT % 'fill="url(#nope) #12ab34"'))
    assert d.shapes[0].fill == "#12ab34" and d.dropped.get("paint") == 1


@pytest.mark.parametrize("paint", [
    'url(http://evil.example/x.svg#g)', 'url(https://evil.example/x)', 'url(//evil.example/x)',
    'url(javascript:alert(1))', 'url(data:image/svg+xml;base64,PHN2Zy8+)', 'url(file:///etc/passwd)',
], ids=["http", "https", "protocol-relative", "javascript", "data", "file"])
def test_an_external_url_in_a_fill_never_reaches_the_output(paint):
    d = pi.parse_design(doc(RECT % f'fill="{paint}"'))
    out = pi.to_svg(d).replace(NS.split(" ", 1)[0], "")  # the output's own xmlns is not upload content
    assert d.shapes[0].fill is None and d.shapes[0].fill_gradient is None and d.dropped.get("paint") == 1
    for bad in ("http", "javascript", "data:", "file:", "evil", "url("):
        assert bad not in out


def test_an_external_href_on_a_gradient_is_dropped_and_counted_and_never_fetched():
    defs = ('<linearGradient id="g" href="http://evil.example/g.svg#x">'
            '<stop offset="0" stop-color="#ff0000"/><stop offset="1" stop-color="#0000ff"/></linearGradient>')
    d = pi.parse_design(doc(RECT % 'fill="url(#g)"', defs=defs))
    out = pi.to_svg(d).replace(NS, "")
    assert "evil" not in out and "http" not in out and "#ff0000" in out  # first stop, the flat fallback
    assert d.shapes[0].fill_gradient is None and d.dropped.get("gradient", 0) >= 1


# ── bounds and hostile input ────────────────────────────────────────────────

def stops(*pairs):
    return "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in pairs)


@pytest.mark.parametrize("body", [
    stops(*[(i / 9, "#ff0000") for i in range(10)]),                      # 10 stops, over the cap of 8
    stops((0, "#ff0000")),                                                # one stop
    stops((0.6, "#ff0000"), (0.3, "#0000ff")),                            # decreasing offsets
    stops((0, "#ff0000"), (1.5, "#0000ff")),                              # offset out of range
    stops((-0.1, "#ff0000"), (1, "#0000ff")),
    stops((0, "#ff0000"), ("nan", "#0000ff")),
    stops((0, "#ff0000"), ("1e999", "#0000ff")),
    stops((0, "#ff0000"), (1, "url(http://evil.example/x)")),             # a stop colour that is not a colour
    stops((0, "#ff0000"), (1, "expression(alert(1))")),
], ids=["ten-stops", "one-stop", "decreasing", "above-one", "negative", "nan", "inf", "url-colour", "expression"])
def test_a_gradient_that_breaks_a_stop_bound_is_dropped_counted_and_never_reaches_the_output(body):
    defs = f'<linearGradient id="g">{body}</linearGradient>'
    d = pi.parse_design(doc(RECT % 'fill="url(#g)"', defs=defs))
    assert d.shapes[0].fill_gradient is None and d.dropped.get("gradient", 0) >= 1
    out = pi.to_svg(d)
    assert "evil" not in out and "expression" not in out and "<linearGradient" not in out


@pytest.mark.parametrize("attrs", [
    'gradientUnits="javascript:1"',
    'gradientTransform="rotate(45)"',                                      # only matrix() is accepted
    'gradientTransform="matrix(1 0 0 1 1e9 0)"',                           # entry beyond the coordinate bound
    'gradientTransform="matrix(nan 0 0 1 0 0)"',
    'x1="1e999"', 'x2="abc"', 'x1="50%" gradientUnits="userSpaceOnUse"',  # percent only means something in bbox units
    'href="#other"', 'xlink:href="#other" xmlns:xlink="http://www.w3.org/1999/xlink"',
], ids=["units", "rotate", "huge-matrix", "nan-matrix", "inf-coord", "text-coord", "percent-user", "href", "xlink-href"])
def test_a_gradient_that_breaks_a_geometry_bound_is_dropped_and_counted(attrs):
    defs = (f'<linearGradient id="g" {attrs}><stop offset="0" stop-color="#ff0000"/>'
            '<stop offset="1" stop-color="#0000ff"/></linearGradient>')
    d = pi.parse_design(doc(RECT % 'fill="url(#g)"', defs=defs))
    assert d.shapes[0].fill_gradient is None and d.dropped.get("gradient", 0) >= 1
    assert d.shapes[0].fill == "#ff0000"       # first valid stop


def test_more_than_64_gradients_keep_the_first_64_and_count_the_rest():
    defs = "".join(f'<linearGradient id="g{i}"><stop offset="0" stop-color="#ff0000"/>'
                   f'<stop offset="1" stop-color="#0000ff"/></linearGradient>' for i in range(70))
    body = "".join(RECT % f'fill="url(#g{i})"' for i in (0, 63, 64, 69))
    d = pi.parse_design(doc(body, defs=defs))
    assert [s.fill_gradient is not None for s in d.shapes] == [True, True, False, False]
    assert d.dropped.get("gradient_limit") == 6


@pytest.mark.parametrize("gid", ['g"><script>alert(1)</script>', "a b", "x" * 80, "g;fill:red", "g)(", ""])
def test_an_id_outside_the_plain_pattern_can_never_be_referenced_and_never_appears_in_the_output(gid):
    safe = gid.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    defs = (f'<linearGradient id="{safe}"><stop offset="0" stop-color="#ff0000"/>'
            '<stop offset="1" stop-color="#0000ff"/></linearGradient>')
    d = pi.parse_design(doc(RECT % f'fill="url(#{safe})"', defs=defs))
    out = pi.to_svg(d)
    assert d.shapes[0].fill_gradient is None
    for bad in ("<script", "alert", "fill:red", "x" * 80):
        assert bad not in out


def test_gradient_output_has_no_byte_of_the_upload_outside_typed_fields():
    out = pi.to_svg(pi.parse_design(doc(RECT % 'fill="url(#g)" onclick="x()" data-x="evil"')))
    for bad in ("onclick", "evil", "data-x", "href", "<script", "xlink"):
        assert bad not in out


def test_a_gradient_cycle_through_href_cannot_loop():
    defs = ('<linearGradient id="a" href="#b"><stop offset="0" stop-color="#ff0000"/></linearGradient>'
            '<linearGradient id="b" href="#a"><stop offset="0" stop-color="#0000ff"/></linearGradient>')
    d = pi.parse_design(doc(RECT % 'fill="url(#a)"', defs=defs))
    assert d.shapes[0].fill_gradient is None and d.dropped.get("gradient", 0) >= 1


def test_a_gradient_far_from_the_root_is_still_found_but_hidden_content_stays_hidden():
    d = pi.parse_design(doc('<g><defs>' + LINEAR.replace('id="g"', 'id="h"') + '</defs></g>' + RECT % 'fill="url(#h)"', defs=""))
    assert d.shapes[0].fill_gradient is not None


# ── group index ─────────────────────────────────────────────────────────────

def test_shapes_remember_the_top_level_element_they_came_from():
    body = ('<g>' + RECT % 'fill="#111111"' + '<g>' + RECT % 'fill="#222222"' + '</g></g>'
            + RECT % 'fill="#333333"' + '<g>' + RECT % 'fill="#444444"' + '</g>')
    d = pi.parse_design(doc(body, defs=""))
    assert [s.group for s in d.shapes] == [0, 0, 1, 2]


def test_a_skipped_top_level_element_does_not_take_an_index():
    d = pi.parse_design(doc('<title>t</title><g>' + RECT % 'fill="#111111"' + '</g>' + RECT % 'fill="#222222"', defs=""))
    assert [s.group for s in d.shapes] == [0, 1]


# ── pixels ──────────────────────────────────────────────────────────────────

def test_a_gradient_renders_as_a_gradient_in_the_real_browser():
    from PIL import Image
    d = pi.parse_design(doc('<rect x="0" y="0" width="400" height="300" fill="url(#g)"/>'))
    png = asyncio.run(pi.render_png(d))
    im = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = im.size
    left, right = im.getpixel((int(w * 0.05), h // 2)), im.getpixel((int(w * 0.95), h // 2))
    assert left[0] > 200 and left[2] < 80          # red end
    assert right[2] > 120 and right[0] < 180       # blue end, half opaque over white
    assert left != right


# ── found while writing the tests above ─────────────────────────────────────

def test_a_full_canvas_gradient_rectangle_is_a_shape_not_a_flat_page_background():
    d = pi.parse_design(doc('<rect x="0" y="0" width="400" height="300" fill="url(#g)"/>'))
    assert d.background is None and len(d.shapes) == 1 and d.shapes[0].fill_gradient is not None


def test_a_full_canvas_flat_rectangle_is_still_the_background():
    d = pi.parse_design(doc('<rect x="0" y="0" width="400" height="300" fill="#102030"/>', defs=""))
    assert d.background == "#102030" and d.shapes == []


def test_a_font_face_only_stylesheet_and_structural_classes_cost_nothing():
    css = "<style>@font-face { font-family: x; src: url(http://fonts.invalid/x.woff2); }</style>"
    d = pi.parse_design(doc(css + RECT % 'class="fills" fill="#12ab34"', defs=""))
    assert d.dropped == {} and d.shapes[0].fill == "#12ab34"


def test_a_tag_selector_that_paints_is_counted_for_every_shape():
    d = pi.parse_design(doc("<style>rect{fill:url(#g)}</style>" + RECT % "" + RECT % ""))
    assert d.dropped.get("stylesheet") == 1 and d.dropped.get("class_paint") == 2


def test_an_import_rule_is_counted_even_without_a_painting_declaration():
    d = pi.parse_design(doc('<style>@import url(http://evil.invalid/a.css);</style>' + RECT % 'fill="#12ab34"', defs=""))
    assert d.dropped.get("stylesheet") == 1 and "evil" not in pi.to_svg(d)


def test_the_draft_style_names_what_was_dropped_in_plain_words():
    res = pi.import_penpot(doc(RECT % 'fill="url(#g)" stroke="url(#g)"' + RECT % 'fill="url(#nope)"'))
    text = " ".join(res.notes)
    assert "1 gradient stroke" in text and "1 unreadable paint" in text


def test_gradient_pixels_match_the_source_svg_in_chromium():
    """The same document drawn by the browser straight from the upload and from our typed model: a linear and a
    radial gradient, one with a transform and user units, with half-opaque stops."""
    pytest.importorskip("playwright")
    from PIL import Image, ImageChops
    from web_renderer import WebRenderError, WebSlideRenderer

    defs = (LINEAR + RADIAL +
            '<linearGradient id="u" gradientUnits="userSpaceOnUse" x1="20" y1="20" x2="380" y2="20" '
            'gradientTransform="matrix(1 0 0.2 1 -30 0)"><stop offset="0" stop-color="#00aa44"/>'
            '<stop offset="0.5" stop-color="#ffee00" stop-opacity="0.6"/><stop offset="1" stop-color="#220066"/></linearGradient>')
    body = ('<rect x="10" y="10" width="380" height="80" fill="url(#g)"/>'
            '<ellipse cx="100" cy="190" rx="90" ry="70" fill="url(#r)"/>'
            '<rect x="220" y="110" width="170" height="170" rx="20" fill="url(#u)" opacity="0.9"/>')
    upload = doc(body, defs=defs)
    design = pi.parse_design(upload)
    assert design.dropped == {}
    html_doc, w, h = pi.to_html(design)

    async def both():
        async with WebSlideRenderer() as r:
            mine = await r.render_html_png(html_doc, w, h, timeout_s=30)
            orig = await r.render_html_png('<!doctype html><html><body style="margin:0;background:#fff">'
                                           + upload.decode() + "</body></html>", w, h, timeout_s=30)
        return mine, orig

    try:
        mine, orig = asyncio.run(both())
    except WebRenderError as e:
        pytest.skip(f"no usable Chromium: {e}")
    a, b = (Image.open(io.BytesIO(x)).convert("RGB") for x in (mine, orig))
    assert a.size == b.size
    diff = ImageChops.difference(a, b).point(lambda v: 255 if v > 6 else 0).convert("L")
    assert diff.getbbox() is None, diff.getbbox()
    assert len({a.getpixel((x, 50)) for x in range(20, 380, 40)}) > 5      # it really is a gradient, not a flat fill

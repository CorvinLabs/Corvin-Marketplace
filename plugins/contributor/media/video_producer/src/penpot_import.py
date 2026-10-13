"""Penpot SVG export -> closed shape model -> draft Style and clean SVG (ADR-2257, strand A).

Pure functions over bytes: no filesystem, no network, no subprocess. The upload is untrusted.
The XML goes through the same hardened parser as the PowerPoint import (no DTD or entities, no
NUL, node and depth caps) and is then reduced to a CLOSED model: rectangles, ellipses, paths and
text with validated numbers and ``#rrggbb`` colours. Everything the model cannot express (images,
gradients, filters, scripts, ``use``, external ``@font-face`` URLs) is counted and dropped, never
passed on: ``to_svg`` writes the output from the typed fields only, so no byte of the upload
reaches the browser that renders it.

What an SVG export cannot carry - components, constraints, auto-layout, animations - is not
imported; ``design_to_style`` says so in the draft's warnings.
"""

from __future__ import annotations

import copy
import hashlib
import html
import math
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    from .style_import_pptx import (NEUTRAL_ACCENT, ImportResult, PptxImportError, _is_chromatic, _label_from_filename,
                                    _aspect, _other_bg, _palette, map_font, parse_xml, _clean_font)
    from .style_pack import Style, StyleError, contrast, luminance, mix, sanitize_source, validate_style
    from .web_templates import load_tokens
except ImportError:  # standalone script use
    from style_import_pptx import (NEUTRAL_ACCENT, ImportResult, PptxImportError, _is_chromatic, _label_from_filename,
                                   _aspect, _other_bg, _palette, map_font, parse_xml, _clean_font)
    from style_pack import Style, StyleError, contrast, luminance, mix, sanitize_source, validate_style
    from web_templates import load_tokens

SVG_NS = "http://www.w3.org/2000/svg"
MAX_SVG_BYTES = 8 * 1024 * 1024
MAX_SHAPES = 2000
MAX_TEXT = 600
MAX_TEXT_TOTAL = 30_000
MAX_PATH = 20_000
MAX_PATH_TOTAL = 400_000  # rendering cost grows with path length; 400 x 20 000 took 26 s in Chromium
MAX_ASPECT = 32.0
MIN_DIM, MAX_DIM = 16.0, 20_000.0
MAX_COORD = 1e6
MAX_SECONDS = 5.0
RENDER_BOX = (1920.0, 1080.0)

_SKIP = frozenset({"defs", "pattern", "clipPath", "mask", "filter", "style", "linearGradient", "radialGradient",
                   "symbol", "metadata", "title", "desc", "marker"})
_UNSUPPORTED = frozenset({"image", "foreignObject", "use", "script", "switch", "line", "polyline", "polygon"})
_PATH_OK = re.compile(r"[MmLlHhVvCcSsQqTtAaZz0-9eE+\-., \t\r\n]*")
_HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")
_RGB = re.compile(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*([\d.]+)\s*)?\)")
_MATRIX = re.compile(r"matrix\(\s*([^)]*)\)")
_CTRL = re.compile("[\x00-\x08\x0b-\x1f\x7f‪-‮⁦-⁩‎‏]")
_BASELINES = frozenset({"alphabetic", "ideographic", "hanging", "middle", "central", "text-before-edge",
                        "text-after-edge", "auto"})
_IDENT = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
_ANCHORS = frozenset({"start", "middle", "end"})
NOT_IMPORTED = ("An SVG export does not carry components, constraints, auto-layout or animations; "
                "they were not imported. Gradients, images, shadows and blurs are dropped.")


class PenpotImportError(StyleError):
    """The file cannot be imported; the message is safe to show the user."""


@dataclass(frozen=True)
class Shape:
    kind: str  # rect | ellipse | path | text
    x: float = 0.0  # rect/text: origin; ellipse: centre
    y: float = 0.0
    w: float = 0.0  # rect: size; ellipse: radii
    h: float = 0.0
    rx: float = 0.0
    ry: float = 0.0
    d: str = ""
    text: str = ""
    fill: Optional[str] = None
    fill_opacity: float = 1.0
    stroke: Optional[str] = None
    stroke_width: float = 0.0
    opacity: float = 1.0
    font_family: str = ""
    font_size: float = 0.0
    font_weight: int = 400
    text_length: float = 0.0
    baseline: str = "alphabetic"
    anchor: str = "start"
    matrix: Tuple[float, float, float, float, float, float] = _IDENT


@dataclass
class Design:
    width: float
    height: float
    background: Optional[str]
    shapes: List[Shape] = field(default_factory=list)
    dropped: Dict[str, int] = field(default_factory=dict)
    ox: float = 0.0  # viewBox origin: shapes are drawn in the viewBox's own coordinates
    oy: float = 0.0
    path_chars: int = 0


def _local(tag: Any) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _num(v: Any, default: Optional[float] = None, lo: float = -MAX_COORD, hi: float = MAX_COORD) -> float:
    if v is None or v == "":
        if default is None:
            raise ValueError("missing number")
        return default
    s = str(v).strip()
    if s.endswith("px"):
        s = s[:-2]
    f = float(s)
    if not math.isfinite(f) or f < lo or f > hi:
        raise ValueError("number out of range")
    return f


def _style(el: ET.Element) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in (el.get("style") or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def _attr(el: ET.Element, st: Dict[str, str], key: str) -> Optional[str]:
    return st.get(key, el.get(key))


_UNSET = object()


def _color(v: Optional[str]) -> Any:
    """'#rrggbb', None for 'none'/transparent, _UNSET when the value is not a plain colour."""
    if v is None:
        return _UNSET
    s = v.strip().lower()
    if s in ("none", "transparent"):
        return None
    if s == "black":
        return "#000000"
    if s == "white":
        return "#ffffff"
    m = _RGB.fullmatch(s)
    if m:
        r, g, b = (int(m.group(i)) for i in (1, 2, 3))
        if max(r, g, b) > 255:
            return _UNSET
        return "#{:02x}{:02x}{:02x}".format(r, g, b)
    if _HEX.fullmatch(s):
        if len(s) == 4:
            s = "#" + "".join(c * 2 for c in s[1:])
        return s
    return _UNSET


def _unit(v: Optional[str], default: float = 1.0) -> float:
    try:
        return _num(v, default, 0.0, 1.0)
    except ValueError:
        return default


def _matrix(el: ET.Element, tally: Dict[str, int]) -> Tuple[float, ...]:
    raw = el.get("transform")
    if not raw:
        return _IDENT
    m = _MATRIX.fullmatch(raw.strip())
    try:
        if not m:
            raise ValueError("unsupported transform")
        vals = [_num(x, None, -MAX_COORD, MAX_COORD) for x in re.split(r"[\s,]+", m.group(1).strip())]
        if len(vals) != 6:
            raise ValueError("bad matrix")
        return tuple(vals)
    except ValueError:
        tally["bad_transform"] = tally.get("bad_transform", 0) + 1
        return _IDENT


def _mul(p: Tuple[float, ...], c: Tuple[float, ...]) -> Tuple[float, ...]:
    a1, b1, c1, d1, e1, f1 = p
    a2, b2, c2, d2, e2, f2 = c
    out = (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2, a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
           a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)
    return out if all(math.isfinite(x) and abs(x) < MAX_COORD for x in out) else _IDENT


def _bump(tally: Dict[str, int], key: str) -> None:
    tally[key] = tally.get(key, 0) + 1


def _radii(el: ET.Element) -> Tuple[float, float]:
    """SVG rule: a rect given only rx (or only ry) uses it for both radii."""
    rx = _num(el.get("rx"), None, 0.0) if el.get("rx") is not None else None
    ry = _num(el.get("ry"), None, 0.0) if el.get("ry") is not None else None
    if rx is None and ry is None:
        return 0.0, 0.0
    return (ry if rx is None else rx), (rx if ry is None else ry)


def _stroke_width(el: ET.Element, st: Dict[str, str], default: float) -> float:
    try:
        return _num(_attr(el, st, "stroke-width"), default, 0.0, 1000.0)
    except ValueError:
        return default


def _shape(tag: str, el: ET.Element, st: Dict[str, str], m: Tuple[float, ...], inh: Dict[str, Any],
           tally: Dict[str, int]) -> Optional[Shape]:
    fill = _color(_attr(el, st, "fill")) if _attr(el, st, "fill") is not None else inh["fill"]
    stroke = _color(_attr(el, st, "stroke")) if _attr(el, st, "stroke") is not None else inh["stroke"]
    if fill is _UNSET:
        _bump(tally, "paint")
        fill = None
    if stroke is _UNSET:
        _bump(tally, "paint")
        stroke = None
    common = dict(fill=fill, fill_opacity=_unit(_attr(el, st, "fill-opacity"), inh["fill_opacity"]), stroke=stroke,
                  stroke_width=_stroke_width(el, st, inh["stroke_width"]) if stroke else 0.0,
                  opacity=inh["opacity"] * _unit(_attr(el, st, "opacity")), matrix=m)
    if tag == "rect":
        w, h = _num(el.get("width"), None, 0.0), _num(el.get("height"), None, 0.0)
        rx, ry = _radii(el)
        return Shape("rect", x=_num(el.get("x"), 0.0), y=_num(el.get("y"), 0.0), w=w, h=h, rx=rx, ry=ry, **common)
    if tag in ("ellipse", "circle"):
        rx = _num(el.get("rx", el.get("r")), None, 0.0)
        ry = _num(el.get("ry", el.get("r")), None, 0.0)
        return Shape("ellipse", x=_num(el.get("cx"), 0.0), y=_num(el.get("cy"), 0.0), w=rx, h=ry, **common)
    if tag == "path":
        d = (el.get("d") or "").strip()
        if not d or len(d) > MAX_PATH or not _PATH_OK.fullmatch(d):
            raise ValueError("path data refused")
        return Shape("path", d=d, **common)
    text = _CTRL.sub("", "".join(el.itertext()))
    if not text.strip():
        return None
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT]
        _bump(tally, "text_truncated")
    base = (_attr(el, st, "dominant-baseline") or "alphabetic").strip().lower()
    weight = (_attr(el, st, "font-weight") or "400").strip().lower()
    weight_n = 700 if weight == "bold" else 400 if weight == "normal" else int(weight) if weight.isdigit() else 400
    anchor = (_attr(el, st, "text-anchor") or "start").strip().lower()
    return Shape("text", x=_num(el.get("x"), 0.0), y=_num(el.get("y"), 0.0), text=text,
                 anchor=anchor if anchor in _ANCHORS else "start",
                 font_family=_clean_font((_attr(el, st, "font-family") or "").split(",")[0].strip("'\" ")),
                 font_size=_num(_attr(el, st, "font-size"), 16.0, 1.0, 2000.0),
                 font_weight=min(max(weight_n, 100), 900), baseline=base if base in _BASELINES else "alphabetic",
                 text_length=_num(el.get("textLength"), 0.0, 0.0, MAX_COORD), **common)


def _walk(node: ET.Element, m: Tuple[float, ...], inh: Dict[str, Any], design: Design, tally: Dict[str, int],
          state: Dict[str, Any]) -> None:
    for el in node:
        if time.monotonic() > state["deadline"]:
            raise PenpotImportError("The design is too complex to read.")
        tag = _local(el.tag)
        if tag in _SKIP:
            continue
        if tag in _UNSUPPORTED:
            _bump(tally, tag)
            continue
        st = _style(el)
        if st.get("display") == "none" or st.get("visibility") == "hidden":
            continue
        cm = _mul(m, _matrix(el, tally))
        if tag in ("g", "svg"):
            sub = dict(inh)
            sub["opacity"] = inh["opacity"] * _unit(_attr(el, st, "opacity"))
            sub["fill_opacity"] = _unit(_attr(el, st, "fill-opacity"), inh["fill_opacity"])
            sub["stroke_width"] = _stroke_width(el, st, inh["stroke_width"])
            for key in ("fill", "stroke"):
                if _attr(el, st, key) is not None:
                    c = _color(_attr(el, st, key))
                    sub[key] = None if c is _UNSET else c
            _walk(el, cm, sub, design, tally, state)
            continue
        if tag not in ("rect", "ellipse", "circle", "path", "text"):
            _bump(tally, "other")
            continue
        try:
            shape = _shape(tag, el, st, cm, inh, tally)
        except ValueError:
            _bump(tally, "malformed")
            continue
        if shape is None:
            continue
        if (tag == "rect" and not design.shapes and design.background is None and shape.fill and cm == _IDENT
                and shape.fill_opacity == 1.0 and shape.opacity == 1.0 and shape.x <= design.ox + 0.5
                and shape.y <= design.oy + 0.5 and shape.w >= design.width - 1 and shape.h >= design.height - 1):
            design.background = shape.fill  # the first full-canvas solid rectangle is the page, not a shape
            continue
        if shape.kind == "path":
            design.path_chars += len(shape.d)
            if design.path_chars > MAX_PATH_TOTAL:
                raise PenpotImportError("The design has too much path data to render.")
        state["text_total"] += len(shape.text)
        if len(design.shapes) >= MAX_SHAPES or state["text_total"] > MAX_TEXT_TOTAL:
            raise PenpotImportError("The design has too many shapes or too much text to import.")
        design.shapes.append(shape)


def parse_design(data: bytes) -> Design:
    """Penpot SVG bytes -> Design. Raises PenpotImportError (safe message) for anything it refuses."""
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise PenpotImportError("The file is empty.")
    if len(data) > MAX_SVG_BYTES:
        raise PenpotImportError("The SVG is larger than 8 MB.")
    try:
        root = parse_xml(bytes(data))
    except PptxImportError as e:
        raise PenpotImportError(str(e).replace("presentation", "design")) from None
    if _local(root.tag) != "svg" or not root.tag.startswith("{" + SVG_NS + "}"):
        raise PenpotImportError("This is not an SVG file.")
    ox = oy = 0.0
    try:
        vb = [_num(x, None) for x in re.split(r"[\s,]+", root.get("viewBox").strip())] if root.get("viewBox") else []
        if len(vb) == 4:
            ox, oy, width, height = vb  # shapes are drawn in the viewBox's coordinates; width/height only scale
        else:
            width, height = _num(root.get("width"), None), _num(root.get("height"), None)
    except ValueError:
        raise PenpotImportError("The SVG has no usable size.") from None
    if not (MIN_DIM <= width <= MAX_DIM and MIN_DIM <= height <= MAX_DIM):
        raise PenpotImportError("The SVG size is outside 16 to 20000 pixels.")
    if max(width, height) / min(width, height) > MAX_ASPECT:
        raise PenpotImportError("The SVG proportions are too extreme to render.")
    design = Design(width=width, height=height, background=None, ox=ox, oy=oy)
    root_fill = _color(_attr(root, _style(root), "fill"))
    inh = {"fill": "#000000" if root_fill is _UNSET else root_fill, "stroke": None, "opacity": 1.0,
           "fill_opacity": 1.0, "stroke_width": 1.0}
    state = {"deadline": time.monotonic() + MAX_SECONDS, "text_total": 0}
    _walk(root, _IDENT, inh, design, design.dropped, state)
    if not design.shapes and design.background is None:
        raise PenpotImportError("No shapes could be read. Export a board from Penpot as SVG.")
    return design


def _n(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".") or "0"


def to_svg(design: Design, box: Tuple[float, float] = RENDER_BOX) -> str:
    """Clean SVG written only from the model's typed fields, scaled to fit ``box`` (never enlarged)."""
    s = min(1.0, box[0] / design.width, box[1] / design.height)
    w, h = max(1, round(design.width * s)), max(1, round(design.height * s))
    out = [f'<svg xmlns="{SVG_NS}" width="{w}" height="{h}" viewBox="{_n(design.ox)} {_n(design.oy)} {_n(design.width)} {_n(design.height)}">',
           f'<rect x="{_n(design.ox)}" y="{_n(design.oy)}" width="{_n(design.width)}" height="{_n(design.height)}" '
           f'fill="{design.background or "#ffffff"}"/>']
    for sh in design.shapes:
        a = [f'fill="{sh.fill}"' if sh.fill else 'fill="none"']
        if sh.fill and sh.fill_opacity < 1:
            a.append(f'fill-opacity="{_n(sh.fill_opacity)}"')
        if sh.stroke:
            a.append(f'stroke="{sh.stroke}" stroke-width="{_n(sh.stroke_width)}"')
        if sh.opacity < 1:
            a.append(f'opacity="{_n(sh.opacity)}"')
        if sh.matrix != _IDENT:
            a.append('transform="matrix(%s)"' % " ".join(_n(v) for v in sh.matrix))
        attrs = " ".join(a)
        if sh.kind == "rect":
            out.append(f'<rect x="{_n(sh.x)}" y="{_n(sh.y)}" width="{_n(sh.w)}" height="{_n(sh.h)}" '
                       f'rx="{_n(sh.rx)}" ry="{_n(sh.ry)}" {attrs}/>')
        elif sh.kind == "ellipse":
            out.append(f'<ellipse cx="{_n(sh.x)}" cy="{_n(sh.y)}" rx="{_n(sh.w)}" ry="{_n(sh.h)}" {attrs}/>')
        elif sh.kind == "path":
            out.append(f'<path d="{html.escape(sh.d, quote=True)}" {attrs}/>')
        else:
            fam = html.escape(f"'{sh.font_family}', sans-serif" if sh.font_family else "sans-serif", quote=True)
            tl = f' textLength="{_n(sh.text_length)}" lengthAdjust="spacingAndGlyphs"' if sh.text_length else ""
            out.append(f'<text x="{_n(sh.x)}" y="{_n(sh.y)}" dominant-baseline="{sh.baseline}" font-family="{fam}" '
                       f'font-size="{_n(sh.font_size)}" font-weight="{sh.font_weight}" text-anchor="{sh.anchor}" xml:space="preserve"{tl} '
                       f'{attrs}>{html.escape(sh.text, quote=False)}</text>')
    out.append("</svg>")
    return "".join(out)


def to_html(design: Design, box: Tuple[float, float] = RENDER_BOX) -> Tuple[str, int, int]:
    svg = to_svg(design, box)
    m = re.match(r'<svg [^>]*width="(\d+)" height="(\d+)"', svg)
    w, h = int(m.group(1)), int(m.group(2))
    return ('<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;padding:0;background:#fff}'
            'svg{display:block}</style></head><body>' + svg + "</body></html>"), w, h


async def render_png(design: Design, *, timeout_s: float = 15.0) -> bytes:
    """The design as PNG through the producer's hardened headless Chromium (JS off, network aborted)."""
    try:
        from .web_renderer import WebSlideRenderer
    except ImportError:  # standalone script use
        from web_renderer import WebSlideRenderer
    document, w, h = to_html(design)
    async with WebSlideRenderer() as r:
        return await r.render_html_png(document, w, h, timeout_s=timeout_s)


# ── style derivation ────────────────────────────────────────────────────────

def _area(sh: Shape, d: Design) -> float:
    """Visible area for colour ranking: clipped to the canvas, weighted by opacity."""
    a, b, c, e, _, _ = sh.matrix
    scale = abs(a * e - b * c)
    if sh.kind == "rect":
        w, h = sh.w, sh.h
        if sh.matrix == _IDENT:
            w = max(0.0, min(sh.x + sh.w, d.ox + d.width) - max(sh.x, d.ox))
            h = max(0.0, min(sh.y + sh.h, d.oy + d.height) - max(sh.y, d.oy))
        area = w * h * scale
    elif sh.kind == "ellipse":
        area = math.pi * sh.w * sh.h * scale
    else:
        area = 1000.0
    return min(area, d.width * d.height) * sh.opacity


def design_to_style(design: Design, filename: str = "", sha256: Optional[str] = None) -> ImportResult:
    """Draft Style from a design's colours and fonts (same derivation rules as the PowerPoint import)."""
    bg = design.background or "#ffffff"
    area: Dict[str, float] = {}
    chars: Dict[str, int] = {}
    fams: Dict[str, int] = {}
    biggest: Tuple[float, str] = (0.0, "")
    for sh in design.shapes:
        if sh.fill and sh.fill != bg:
            if sh.kind == "text":
                chars[sh.fill] = chars.get(sh.fill, 0) + len(sh.text)
            else:
                area[sh.fill] = area.get(sh.fill, 0.0) + _area(sh, design) * sh.fill_opacity
        if sh.kind == "text" and sh.font_family:
            fams[sh.font_family] = fams.get(sh.font_family, 0) + len(sh.text)
            if sh.font_size > biggest[0]:
                biggest = (sh.font_size, sh.font_family)
    light = luminance(bg) >= 0.179
    text_own = max(chars, key=lambda c: (chars[c], c)) if chars else ("#111111" if light else "#f2f2f2")
    ranked = sorted(((a, c) for c, a in area.items() if _is_chromatic(c[1:])), key=lambda t: (-t[0], t[1]))
    accents = [c for _, c in ranked]
    warnings: List[str] = []
    if not accents:
        accents = [NEUTRAL_ACCENT]
        warnings.append("The design has no distinctive colour, so a neutral accent colour was used. "
                        "Pick your own accent in the preview.")
    major = biggest[1] or (max(fams, key=lambda f: (fams[f], f)) if fams else "")
    minor = max(fams, key=lambda f: (fams[f], f)) if fams else major
    tokens = copy.deepcopy(load_tokens())
    own_theme, other_theme = ("light", "dark") if light else ("dark", "light")
    sha = sha256 or hashlib.sha256(repr((design.width, design.height, design.shapes)).encode()).hexdigest()
    style: Optional[Style] = None
    adjusted = False
    for attempt in range(3):
        bg_own = bg if attempt == 0 else mix(bg, "#ffffff" if light else "#000000", 0.5) if attempt == 1 \
            else ("#ffffff" if light else "#15171c")
        bg_other = _other_bg(not light, {}, True)
        pal_own, adj = _palette(bg_own, text_own, accents, tokens[own_theme]["success"])
        pal_other, _ = _palette(bg_other, "#f2f2f2" if light else "#141414", accents, tokens[other_theme]["success"])
        adjusted = adj
        tokens[own_theme].update(pal_own)
        tokens[other_theme].update(pal_other)
        h_fam, h_why = map_font(major)
        b_fam, b_why = map_font(minor or major)
        tokens["typography"].update(heading_family=h_fam, body_family=b_fam, mono_family="JetBrains Mono")
        tokens["source"] = "Imported style"
        fonts: List[Dict[str, str]] = []
        for src, fam, why in ((major, h_fam, h_why), (minor, b_fam, b_why)):
            entry = {"from": src or "(none)", "to": fam, "reason": why}
            if entry not in fonts:
                fonts.append(entry)
        st = Style(id="sty_00000000", name=_label_from_filename(filename), tokens=copy.deepcopy(tokens),
                   default_theme=own_theme, wordmark="", intro_mark=False, credit=False, decor="minimal",
                   source=sanitize_source({"kind": "penpot", "sha256": sha, "deck_aspect": _aspect(
                       int(design.width), int(design.height))}),
                   fonts=fonts, warnings=list(warnings), mark_png=None)
        try:
            style = validate_style(st)
            if attempt:
                style.warnings.append("The design background was adjusted so text stays readable.")
            break
        except StyleError:
            continue
    if style is None:
        raise PenpotImportError("A readable style could not be built from this design.")
    if adjusted:
        style.warnings.append("The accent colour was adjusted slightly so it stays readable on the background.")
    labels = {"image": "images", "foreignObject": "embedded HTML", "use": "linked shapes", "script": "scripts",
              "paint": "gradients or patterns", "other": "other elements", "malformed": "malformed shapes",
              "line": "lines", "polyline": "lines", "polygon": "polygons", "bad_transform": "unsupported transforms",
              "switch": "switches", "text_truncated": "over-long texts"}
    skipped = [f"{n} {labels.get(k, k)}" for k, n in sorted(design.dropped.items()) if n]
    if skipped:
        style.warnings.append("Not imported: " + ", ".join(skipped) + ".")
    style.warnings.append(NOT_IMPORTED)
    style = validate_style(style)
    return ImportResult(style=style, notes=list(style.warnings))


def import_penpot(data: bytes, filename: str = "") -> ImportResult:
    """Penpot SVG bytes -> draft Style. The upload's sha256 is the provenance."""
    design = parse_design(data)
    return design_to_style(design, filename, hashlib.sha256(bytes(data)).hexdigest())

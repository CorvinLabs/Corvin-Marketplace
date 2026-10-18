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
import dataclasses
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
MAX_GRADIENTS = 64
MIN_STOPS, MAX_STOPS = 2, 8
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
_URL = re.compile(r"url\(\s*#([A-Za-z0-9_.:\-]{1,64})\s*\)(?:\s+(\S.*))?", re.DOTALL)
_GRAD_ID = re.compile(r"[A-Za-z0-9_.:\-]{1,64}")
_GRAD_TAGS = {"linearGradient": "linear", "radialGradient": "radial"}
_ANCHORS = frozenset({"start", "middle", "end"})
NOT_IMPORTED = ("An SVG export has no components, constraints, auto-layout or animations. Fill gradients are kept; "
                "gradient strokes, images, shadows, blurs, filters and style sheets are dropped.")


UNKNOWN_STRUCTURE = ("Unknown Penpot structure: no element with a Penpot shape id (shape-<uuid>). This reader takes "
                     "SVG exports of boards from Penpot 2.18.x (File > Export > SVG); other SVG files are refused.")


class PenpotImportError(StyleError):
    """The file cannot be imported; the message is safe to show the user."""


@dataclass(frozen=True)
class Gradient:
    """A linear or radial fill gradient: typed numbers and ``#rrggbb`` stops only (ADR-2260 decision 7)."""
    kind: str  # linear | radial
    coords: Tuple[float, float, float, float]  # linear: x1 y1 x2 y2; radial: cx cy r 0
    units: str  # bbox | user
    stops: Tuple[Tuple[float, str, float], ...]  # (offset, #rrggbb, opacity)
    matrix: Tuple[float, float, float, float, float, float] = _IDENT


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
    group: int = 0  # ordinal of the top-level element of the root this shape came from
    fill_gradient: Optional[Gradient] = None  # when set, ``fill`` holds its first stop as the flat fallback


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


def _matrix(el: ET.Element, tally: Dict[str, int], attr: str = "transform") -> Tuple[float, ...]:
    raw = el.get(attr)
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


def _gcoord(el: ET.Element, name: str, default: Optional[float], bbox: bool) -> float:
    v = el.get(name)
    if v is None:
        if default is None:
            raise ValueError("missing coordinate")
        return default
    s = v.strip()
    if s.endswith("%"):
        if not bbox:
            raise ValueError("percent in user units")
        f = float(s[:-1]) / 100.0
        if not math.isfinite(f) or abs(f) > MAX_COORD:
            raise ValueError("coordinate out of range")
        return f
    return _num(s, None, -MAX_COORD, MAX_COORD)


def _offset(v: Optional[str]) -> float:
    s = (v or "0").strip()
    f = float(s[:-1]) / 100.0 if s.endswith("%") else float(s)
    if not math.isfinite(f) or f < 0.0 or f > 1.0:
        raise ValueError("offset out of range")
    return f


def _stop_colour(el: ET.Element) -> str:
    st = _style(el)
    raw = st.get("stop-color", el.get("stop-color"))
    c = "#000000" if raw is None else _color(raw)
    if c is _UNSET or c is None:
        raise ValueError("stop colour is not a plain colour")
    return c


def _parse_gradient(el: ET.Element, tally: Dict[str, int]) -> Gradient:
    """One gradient element -> Gradient, or ValueError when any bound or grammar rule is broken."""
    if el.get("href") is not None or any(_local(k) == "href" for k in el.attrib):
        raise ValueError("gradient references another gradient")
    kind = _GRAD_TAGS[_local(el.tag)]
    units_raw = el.get("gradientUnits", "objectBoundingBox")
    if units_raw not in ("objectBoundingBox", "userSpaceOnUse"):
        raise ValueError("unknown gradient units")
    bbox = units_raw == "objectBoundingBox"
    if kind == "linear":
        d = (0.0, 0.0, 1.0, 0.0) if bbox else (None, None, None, None)
        coords = (_gcoord(el, "x1", d[0], bbox), _gcoord(el, "y1", d[1], bbox),
                  _gcoord(el, "x2", d[2], bbox), _gcoord(el, "y2", d[3], bbox))
    else:
        d = (0.5, 0.5, 0.5) if bbox else (None, None, None)
        cx, cy, r = _gcoord(el, "cx", d[0], bbox), _gcoord(el, "cy", d[1], bbox), _gcoord(el, "r", d[2], bbox)
        if r < 0:
            raise ValueError("negative radius")
        coords = (cx, cy, r, 0.0)
        for name, centre in (("fx", cx), ("fy", cy)):
            if el.get(name) is not None and abs(_gcoord(el, name, None, bbox) - centre) > 1e-6:
                _bump(tally, "gradient_focal")
    if el.get("spreadMethod") not in (None, "pad"):
        _bump(tally, "gradient_spread")
    raw_matrix = el.get("gradientTransform")
    matrix = _IDENT
    if raw_matrix:
        mt = _MATRIX.fullmatch(raw_matrix.strip())
        vals = [_num(x, None, -MAX_COORD, MAX_COORD) for x in re.split(r"[\s,]+", mt.group(1).strip())] if mt else []
        if len(vals) != 6:
            raise ValueError("unsupported gradient transform")
        matrix = tuple(vals)
    stops = []
    last = 0.0
    for child in el:
        if _local(child.tag) != "stop":
            continue
        off = _offset(child.get("offset"))
        if off < last:
            raise ValueError("stop offsets decrease")
        last = off
        stops.append((off, _stop_colour(child), _unit(_style(child).get("stop-opacity", child.get("stop-opacity")), 1.0)))
    if not MIN_STOPS <= len(stops) <= MAX_STOPS:
        raise ValueError("a gradient has 2 to 8 stops")
    return Gradient(kind, coords, "bbox" if bbox else "user", tuple(stops), matrix)


def _first_stop_colour(el: ET.Element) -> Optional[str]:
    for child in el:
        if _local(child.tag) == "stop":
            try:
                return _stop_colour(child)
            except ValueError:
                return None
    return None


def _collect_gradients(root: ET.Element, tally: Dict[str, int]) -> Dict[str, Tuple[Optional[Gradient], Optional[str]]]:
    """id -> (Gradient or None when dropped, flat fallback colour). Dropped definitions are counted."""
    out: Dict[str, Tuple[Optional[Gradient], Optional[str]]] = {}
    for el in root.iter():
        if _local(el.tag) not in _GRAD_TAGS:
            continue
        gid = el.get("id") or ""
        if not _GRAD_ID.fullmatch(gid) or gid in out:
            _bump(tally, "gradient")
            continue
        if len(out) >= MAX_GRADIENTS:
            _bump(tally, "gradient_limit")
            out[gid] = (None, _first_stop_colour(el))
            continue
        try:
            out[gid] = (_parse_gradient(el, tally), None)
        except (ValueError, KeyError):
            _bump(tally, "gradient")
            out[gid] = (None, _first_stop_colour(el))
    for gid, (g, fb) in list(out.items()):
        if g is not None:
            out[gid] = (g, g.stops[0][1])
    return out


_CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_CSS_PAINT = re.compile(r"(?:^|;)\s*(?:fill|stroke)\s*:", re.I)


def _stylesheet_paint(root: ET.Element, tally: Dict[str, int]) -> Tuple[frozenset, bool]:
    """Style sheets are not imported. Only a sheet that can PAINT (a fill/stroke rule or an @import) is counted: a real
    Penpot export carries one for @font-face and structural classes, which lose nothing. Returns the class names a
    painting rule selects and whether a painting rule selects by anything else (tag, id, universal)."""
    classes, everything = set(), False
    for el in root.iter():
        if _local(el.tag) != "style":
            continue
        css = re.sub(r"@font-face\s*\{[^{}]*\}", "", "".join(el.itertext()), flags=re.I)
        painting = bool(re.search(r"@import", css, re.I))
        for selector, body in _CSS_RULE.findall(css):
            if _CSS_PAINT.search(body.strip()):
                painting = True
                found = re.findall(r"\.([A-Za-z0-9_\-]+)", selector)
                classes.update(found)
                if not found or re.search(r"(?:^|[\s,>+~])[A-Za-z*#\[]", selector.strip()):
                    everything = True
        if painting:
            _bump(tally, "stylesheet")
    return frozenset(classes), everything


def _paint(value: Optional[str], grads: Dict[str, Tuple[Optional[Gradient], Optional[str]]],
           tally: Dict[str, int], stroke: bool = False) -> Tuple[Optional[str], Optional[Gradient]]:
    """One paint value -> (flat colour or None, typed gradient or None). An unreadable paint is counted."""
    s = (value or "").strip()
    m = _URL.fullmatch(s)
    if m:
        g, fb = grads.get(m.group(1), (None, None))
        if m.group(1) not in grads:
            _bump(tally, "paint")
            alt = _color(m.group(2)) if m.group(2) else None
            return (alt if isinstance(alt, str) else None), None
        if g is None:
            return fb, None
        if stroke:
            _bump(tally, "gradient_stroke")
            return g.stops[0][1], None
        return g.stops[0][1], g
    c = _color(s)
    if c is _UNSET:
        _bump(tally, "paint")
        return None, None
    return c, None


def _stroke_width(el: ET.Element, st: Dict[str, str], default: float) -> float:
    try:
        return _num(_attr(el, st, "stroke-width"), default, 0.0, 1000.0)
    except ValueError:
        return default


def _shape(tag: str, el: ET.Element, st: Dict[str, str], m: Tuple[float, ...], inh: Dict[str, Any],
           tally: Dict[str, int], state: Dict[str, Any]) -> Optional[Shape]:
    grads = state["grads"]
    own_fill, own_stroke = _attr(el, st, "fill"), _attr(el, st, "stroke")
    fill, fill_g = _paint(own_fill, grads, tally) if own_fill is not None else (inh["fill"], inh["fill_g"])
    stroke = _paint(own_stroke, grads, tally, stroke=True)[0] if own_stroke is not None else inh["stroke"]
    common = dict(group=state["group"], fill_gradient=fill_g if fill else None, fill=fill, fill_opacity=_unit(_attr(el, st, "fill-opacity"), inh["fill_opacity"]), stroke=stroke,
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
    for sub in el.iter():
        if sub is not el and _local(sub.tag) == "tspan":
            sst = _style(sub)
            if _attr(sub, sst, "fill") is not None or _attr(sub, sst, "stroke") is not None:
                _bump(tally, "tspan_paint")
                break
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
          state: Dict[str, Any], top: bool = False) -> None:
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
        if top and tag in ("g", "svg", "rect", "ellipse", "circle", "path", "text"):
            state["group"] += 1
        if tag in ("g", "svg"):
            sub = dict(inh)
            sub["opacity"] = inh["opacity"] * _unit(_attr(el, st, "opacity"))
            sub["fill_opacity"] = _unit(_attr(el, st, "fill-opacity"), inh["fill_opacity"])
            sub["stroke_width"] = _stroke_width(el, st, inh["stroke_width"])
            for key in ("fill", "stroke"):
                raw = _attr(el, st, key)
                if raw is not None:
                    sub[key], g = _paint(raw, state["grads"], tally, stroke=key == "stroke")
                    sub[key + "_g"] = g if key == "fill" else None
            _walk(el, cm, sub, design, tally, state)
            continue
        if tag not in ("rect", "ellipse", "circle", "path", "text"):
            _bump(tally, "other")
            continue
        if state["paint_all"] or (state["paint_classes"] and state["paint_classes"] & set((el.get("class") or "").split())):
            _bump(tally, "class_paint")
        try:
            shape = _shape(tag, el, st, cm, inh, tally, state)
        except ValueError:
            _bump(tally, "malformed")
            continue
        if shape is None:
            continue
        if (tag == "rect" and not design.shapes and design.background is None and shape.fill and shape.fill_gradient is None and cm == _IDENT
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
    if not any(str(el.get("id") or "").startswith("shape-") for el in root.iter()):
        raise PenpotImportError(UNKNOWN_STRUCTURE)
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
    grads = _collect_gradients(root, design.dropped)
    paint_classes, paint_all = _stylesheet_paint(root, design.dropped)
    raw_root_fill = _attr(root, _style(root), "fill")
    root_fill, root_g = ("#000000", None) if raw_root_fill is None else _paint(raw_root_fill, grads, design.dropped)
    inh = {"fill": root_fill, "fill_g": root_g, "stroke": None, "stroke_g": None, "opacity": 1.0,
           "fill_opacity": 1.0, "stroke_width": 1.0}
    state = {"deadline": time.monotonic() + MAX_SECONDS, "text_total": 0, "grads": grads, "group": -1,
             "paint_classes": paint_classes, "paint_all": paint_all}
    _walk(root, _IDENT, inh, design, design.dropped, state, top=True)
    if not design.shapes and design.background is None:
        raise PenpotImportError("No shapes could be read. Export a board from Penpot as SVG.")
    return design


def _n(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".") or "0"


def _gradient_svg(g: Gradient, index: int) -> str:
    units = "objectBoundingBox" if g.units == "bbox" else "userSpaceOnUse"
    if g.kind == "linear":
        geo = f'x1="{_n(g.coords[0])}" y1="{_n(g.coords[1])}" x2="{_n(g.coords[2])}" y2="{_n(g.coords[3])}"'
        tag = "linearGradient"
    else:
        geo = f'cx="{_n(g.coords[0])}" cy="{_n(g.coords[1])}" r="{_n(g.coords[2])}"'
        tag = "radialGradient"
    tr = ' gradientTransform="matrix(%s)"' % " ".join(_n(v) for v in g.matrix) if g.matrix != _IDENT else ""
    stops = "".join(f'<stop offset="{_n(o)}" stop-color="{c}" stop-opacity="{_n(a)}"/>' for o, c, a in g.stops)
    return f'<{tag} id="g{index}" gradientUnits="{units}" {geo}{tr}>{stops}</{tag}>'


def _shape_svg(sh: Shape, used: Dict[Gradient, int], extra: str = "") -> str:
    """One shape as an SVG element, from its typed fields only. ``extra`` is markup the CALLER builds (a class or a
    reveal index from the board template), never data."""
    a = [f'fill="url(#g{used[sh.fill_gradient]})"' if sh.fill and sh.fill_gradient is not None
         else f'fill="{sh.fill}"' if sh.fill else 'fill="none"']
    if sh.fill and sh.fill_opacity < 1:
        a.append(f'fill-opacity="{_n(sh.fill_opacity)}"')
    if sh.stroke:
        a.append(f'stroke="{sh.stroke}" stroke-width="{_n(sh.stroke_width)}"')
    if sh.opacity < 1:
        a.append(f'opacity="{_n(sh.opacity)}"')
    if sh.matrix != _IDENT:
        a.append('transform="matrix(%s)"' % " ".join(_n(v) for v in sh.matrix))
    if extra:
        a.append(extra)
    attrs = " ".join(a)
    if sh.kind == "rect":
        return (f'<rect x="{_n(sh.x)}" y="{_n(sh.y)}" width="{_n(sh.w)}" height="{_n(sh.h)}" '
                f'rx="{_n(sh.rx)}" ry="{_n(sh.ry)}" {attrs}/>')
    if sh.kind == "ellipse":
        return f'<ellipse cx="{_n(sh.x)}" cy="{_n(sh.y)}" rx="{_n(sh.w)}" ry="{_n(sh.h)}" {attrs}/>'
    if sh.kind == "path":
        return f'<path d="{html.escape(sh.d, quote=True)}" {attrs}/>'
    fam = html.escape(f"'{sh.font_family}', sans-serif" if sh.font_family else "sans-serif", quote=True)
    tl = f' textLength="{_n(sh.text_length)}" lengthAdjust="spacingAndGlyphs"' if sh.text_length else ""
    return (f'<text x="{_n(sh.x)}" y="{_n(sh.y)}" dominant-baseline="{sh.baseline}" font-family="{fam}" '
            f'font-size="{_n(sh.font_size)}" font-weight="{sh.font_weight}" text-anchor="{sh.anchor}" xml:space="preserve"{tl} '
            f'{attrs}>{html.escape(sh.text, quote=False)}</text>')


def _gradients_used(design: Design) -> Dict[Gradient, int]:
    used: Dict[Gradient, int] = {}
    for sh in design.shapes:
        if sh.fill and sh.fill_gradient is not None and sh.fill_gradient not in used:
            used[sh.fill_gradient] = len(used)
    return used


def to_svg(design: Design, box: Tuple[float, float] = RENDER_BOX) -> str:
    """Clean SVG written only from the model's typed fields, scaled to fit ``box`` (never enlarged).

    It does not rely on every ``Design`` having come from the parser: a field that breaks the validator's patterns
    is refused here too (ADR-2260 decision 2, the second line), so a hand-built or tampered object cannot write markup
    through an attribute that is not escaped."""
    guard_design(design)
    s = min(1.0, box[0] / design.width, box[1] / design.height)
    w, h = max(1, round(design.width * s)), max(1, round(design.height * s))
    used = _gradients_used(design)
    out = [f'<svg xmlns="{SVG_NS}" width="{w}" height="{h}" viewBox="{_n(design.ox)} {_n(design.oy)} {_n(design.width)} {_n(design.height)}">']
    if used:
        out.append("<defs>" + "".join(_gradient_svg(g, i) for g, i in used.items()) + "</defs>")
    out += [f'<rect x="{_n(design.ox)}" y="{_n(design.oy)}" width="{_n(design.width)}" height="{_n(design.height)}" '
           f'fill="{design.background or "#ffffff"}"/>']
    out += [_shape_svg(sh, used) for sh in design.shapes]
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


# ── the stored model (ADR-2260 decision 2) ──────────────────────────────────
# A design is stored beside its picture as ``design.json`` and is untrusted like an upload when it is read back.
# ``validate_design`` is the ONLY way a Shape is built from JSON; ``guard_design`` is the second line in ``to_svg``.

DESIGN_VERSION = 1
_HEX6 = re.compile(r"#[0-9a-f]{6}")
_KINDS = ("rect", "ellipse", "path", "text")
_SHAPE_KEYS = frozenset({"kind", "x", "y", "w", "h", "rx", "ry", "d", "text", "fill", "fill_opacity", "stroke",
                         "stroke_width", "opacity", "font_family", "font_size", "font_weight", "text_length",
                         "baseline", "anchor", "matrix", "group", "fill_gradient"})
_DESIGN_KEYS = frozenset({"v", "width", "height", "ox", "oy", "background", "shapes"})
_GRADIENT_KEYS = frozenset({"kind", "coords", "units", "stops", "matrix"})


class DesignError(PenpotImportError):
    """A stored or hand-built design breaks the model's rules; the message is safe to show."""


def _bad(what: str) -> DesignError:
    return DesignError(f"The stored design is invalid ({what}).")


def _fnum(v: Any, what: str, lo: float = -MAX_COORD, hi: float = MAX_COORD) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise _bad(what)
    f = float(v)
    if not math.isfinite(f) or f < lo or f > hi:
        raise _bad(what)
    return f + 0.0


def _colour_or_none(v: Any, what: str) -> Optional[str]:
    if v is None:
        return None
    if not isinstance(v, str) or not _HEX6.fullmatch(v):
        raise _bad(what)
    return v


def _matrix6(v: Any, what: str) -> Tuple[float, float, float, float, float, float]:
    if not isinstance(v, (list, tuple)) or len(v) != 6:
        raise _bad(what)
    out = tuple(_fnum(x, what) for x in v)
    if any(abs(x) >= MAX_COORD for x in out):
        raise _bad(what)
    return out  # type: ignore[return-value]


def _gradient_from(v: Any) -> Gradient:
    if not isinstance(v, dict) or set(v) != _GRADIENT_KEYS:
        raise _bad("gradient fields")
    if v["kind"] not in ("linear", "radial") or v["units"] not in ("bbox", "user"):
        raise _bad("gradient kind or units")
    c = v["coords"]
    if not isinstance(c, (list, tuple)) or len(c) != 4:
        raise _bad("gradient coordinates")
    coords = tuple(_fnum(x, "gradient coordinates") for x in c)
    if v["kind"] == "radial" and (coords[2] < 0 or coords[3] != 0.0):
        raise _bad("gradient radius")
    stops_in = v["stops"]
    if not isinstance(stops_in, (list, tuple)) or not MIN_STOPS <= len(stops_in) <= MAX_STOPS:
        raise _bad("gradient stops")
    stops, last = [], 0.0
    for st in stops_in:
        if not isinstance(st, (list, tuple)) or len(st) != 3:
            raise _bad("gradient stop")
        off = _fnum(st[0], "gradient offset", 0.0, 1.0)
        if off < last:
            raise _bad("gradient offsets decrease")
        last = off
        col = _colour_or_none(st[1], "gradient colour")
        if col is None:
            raise _bad("gradient colour")
        stops.append((off, col, _fnum(st[2], "gradient opacity", 0.0, 1.0)))
    return Gradient(v["kind"], coords, v["units"], tuple(stops), _matrix6(v["matrix"], "gradient transform"))  # type: ignore[arg-type]


def _shape_from(v: Any) -> Shape:
    if not isinstance(v, dict) or set(v) != _SHAPE_KEYS:
        raise _bad("shape fields")
    kind = v["kind"]
    if kind not in _KINDS:
        raise _bad("shape kind")
    num = {k: _fnum(v[k], k) for k in ("x", "y")}
    for k in ("w", "h", "rx", "ry"):
        num[k] = _fnum(v[k], k, 0.0)
    d, text = v["d"], v["text"]
    if not isinstance(d, str) or not isinstance(text, str):
        raise _bad("path or text")
    if kind == "path":
        if not d or len(d) > MAX_PATH or not _PATH_OK.fullmatch(d):
            raise _bad("path data")
    elif d:
        raise _bad("path data on a non-path")
    if kind == "text":
        if not text.strip() or len(text) > MAX_TEXT or _CTRL.search(text):
            raise _bad("text")
    elif text:
        raise _bad("text on a non-text")
    fam = v["font_family"]
    if not isinstance(fam, str) or _clean_font(fam) != fam:
        raise _bad("font family")
    weight = v["font_weight"]
    if isinstance(weight, bool) or not isinstance(weight, int) or not 100 <= weight <= 900:
        raise _bad("font weight")
    if v["baseline"] not in _BASELINES or v["anchor"] not in _ANCHORS:
        raise _bad("baseline or anchor")
    group = v["group"]
    if isinstance(group, bool) or not isinstance(group, int) or not 0 <= group < MAX_SHAPES:
        raise _bad("group")
    fill = _colour_or_none(v["fill"], "fill")
    grad = None if v["fill_gradient"] is None else _gradient_from(v["fill_gradient"])
    if grad is not None and fill != grad.stops[0][1]:
        raise _bad("gradient fallback colour")
    stroke = _colour_or_none(v["stroke"], "stroke")
    return Shape(kind, x=num["x"], y=num["y"], w=num["w"], h=num["h"], rx=num["rx"], ry=num["ry"], d=d, text=text,
                 fill=fill, fill_opacity=_fnum(v["fill_opacity"], "fill opacity", 0.0, 1.0), stroke=stroke,
                 stroke_width=_fnum(v["stroke_width"], "stroke width", 0.0, 1000.0),
                 opacity=_fnum(v["opacity"], "opacity", 0.0, 1.0), font_family=fam,
                 font_size=_fnum(v["font_size"], "font size", 0.0, 2000.0), font_weight=weight,
                 text_length=_fnum(v["text_length"], "text length", 0.0), baseline=v["baseline"], anchor=v["anchor"],
                 matrix=_matrix6(v["matrix"], "transform"), group=group, fill_gradient=grad)


def validate_design(obj: Any) -> Design:
    """JSON (as loaded) -> Design, field by field, or DesignError. Every number finite and within the parser's own
    ranges, colours by the parser's pattern, enumerations from their sets, path data through the parser's path check,
    the parser's count and size caps. Runs on every load of a stored model."""
    if not isinstance(obj, dict) or set(obj) != _DESIGN_KEYS or obj.get("v") != DESIGN_VERSION:
        raise _bad("fields or version")
    width = _fnum(obj["width"], "width", MIN_DIM, MAX_DIM)
    height = _fnum(obj["height"], "height", MIN_DIM, MAX_DIM)
    if max(width, height) / min(width, height) > MAX_ASPECT:
        raise _bad("proportions")
    shapes_in = obj["shapes"]
    if not isinstance(shapes_in, list) or len(shapes_in) > MAX_SHAPES:
        raise _bad("shape count")
    design = Design(width=width, height=height, background=_colour_or_none(obj["background"], "background"),
                    ox=_fnum(obj["ox"], "origin"), oy=_fnum(obj["oy"], "origin"))
    text_total, grads = 0, set()
    for item in shapes_in:
        sh = _shape_from(item)
        design.path_chars += len(sh.d)
        text_total += len(sh.text)
        if sh.fill_gradient is not None:
            grads.add(sh.fill_gradient)
        design.shapes.append(sh)
    if design.path_chars > MAX_PATH_TOTAL or text_total > MAX_TEXT_TOTAL or len(grads) > MAX_GRADIENTS:
        raise _bad("size")
    if not design.shapes and design.background is None:
        raise _bad("empty")
    return design


def guard_design(design: Design) -> None:
    """The second line (ADR-2260 decision 2): refuse any field of a Design object that ``validate_design`` would
    refuse, whoever built it. Cheap: a round trip through the stored form."""
    if not isinstance(design, Design) or not all(isinstance(sh, Shape) for sh in design.shapes):
        raise _bad("not a design")
    validate_design(design_to_dict(design))


def _gradient_dict(g: Gradient) -> Dict[str, Any]:
    return {"kind": g.kind, "coords": list(g.coords), "units": g.units,
            "stops": [list(st) for st in g.stops], "matrix": list(g.matrix)}


def design_to_dict(design: Design) -> Dict[str, Any]:
    """The whole typed design - size, origin, background, shapes - as JSON-ready data (no steps, no upload bytes)."""
    shapes = []
    for sh in design.shapes:
        shapes.append({"kind": sh.kind, "x": sh.x, "y": sh.y, "w": sh.w, "h": sh.h, "rx": sh.rx, "ry": sh.ry,
                       "d": sh.d, "text": sh.text, "fill": sh.fill, "fill_opacity": sh.fill_opacity,
                       "stroke": sh.stroke, "stroke_width": sh.stroke_width, "opacity": sh.opacity,
                       "font_family": sh.font_family, "font_size": sh.font_size, "font_weight": sh.font_weight,
                       "text_length": sh.text_length, "baseline": sh.baseline, "anchor": sh.anchor,
                       "matrix": list(sh.matrix), "group": sh.group,
                       "fill_gradient": None if sh.fill_gradient is None else _gradient_dict(sh.fill_gradient)})
    return {"v": DESIGN_VERSION, "width": design.width, "height": design.height, "ox": design.ox, "oy": design.oy,
            "background": design.background, "shapes": shapes}


# ── the board bound (ADR-2260 decision 10) ──────────────────────────────────
# Applied when a design is used as a ``board``, never at import: a design over a bound still imports as a picture and
# as a style source. The values are fixed from measurement (``tests/test_board.py`` renders the worst allowed design -
# every bound met at once - and compares its frame time with the existing templates').
# Measured 2026-10-18 at 1920x1080, 30 fps (ratio = worst board ms/frame : median of the other templates): with the
# transform scale at 16 and strokes at 48 the worst board took 5.8x; scale is the driver (scale 1: 1.6x), stroke width
# next. Scale 4 + stroke 24: 1.92x (no margin); scale 2 + stroke 16: 1.48x - these are the values.
BOARD_MAX_SHAPES = 240
BOARD_MAX_PATH_CHARS = 60_000
BOARD_MAX_STROKE = 16.0
BOARD_MAX_MATRIX_SCALE = 2.0       # |a|, |b|, |c|, |d| of a shape's transform
BOARD_MAX_FONT = 320.0
BOARD_MAX_TEXT_CHARS = 4_000
BOARD_MAX_GRADIENTS = 16
BOARD_MAX_TRANSLUCENT = 120        # shapes with opacity or fill opacity below 1
BOARD_MAX_TEXT_LENGTH = 60         # text shapes with a textLength adjustment
MAX_STEPS = 12
MAX_STEP_LABEL = 40


def board_refusal(design: Design) -> Optional[str]:
    """Why this design cannot be a board (a safe sentence with the count), or None when it is within every bound."""
    n = len(design.shapes)
    if n == 0:
        return "The design has no shapes to reveal."
    if n > BOARD_MAX_SHAPES:
        return f"The design has {n} shapes; a board can reveal at most {BOARD_MAX_SHAPES}."
    if design.path_chars > BOARD_MAX_PATH_CHARS:
        return f"The design has {design.path_chars} characters of path data; a board allows {BOARD_MAX_PATH_CHARS}."
    text = sum(len(sh.text) for sh in design.shapes)
    if text > BOARD_MAX_TEXT_CHARS:
        return f"The design has {text} characters of text; a board allows {BOARD_MAX_TEXT_CHARS}."
    if any(sh.stroke and sh.stroke_width > BOARD_MAX_STROKE for sh in design.shapes):
        return f"A stroke is wider than {BOARD_MAX_STROKE:g}; a board cannot draw it."
    if any(max(abs(v) for v in sh.matrix[:4]) > BOARD_MAX_MATRIX_SCALE for sh in design.shapes):
        return f"A shape is scaled by more than {BOARD_MAX_MATRIX_SCALE:g}x; a board cannot draw it."
    if any(sh.kind == "text" and sh.font_size > BOARD_MAX_FONT for sh in design.shapes):
        return f"A text is larger than {BOARD_MAX_FONT:g} pixels; a board cannot draw it."
    grads = {sh.fill_gradient for sh in design.shapes if sh.fill_gradient is not None}
    if len(grads) > BOARD_MAX_GRADIENTS:
        return f"The design has {len(grads)} gradients; a board allows {BOARD_MAX_GRADIENTS}."
    translucent = sum(1 for sh in design.shapes if sh.opacity < 1 or (sh.fill and sh.fill_opacity < 1))
    if translucent > BOARD_MAX_TRANSLUCENT:
        return f"The design has {translucent} see-through shapes; a board allows {BOARD_MAX_TRANSLUCENT}."
    adjusted = sum(1 for sh in design.shapes if sh.kind == "text" and sh.text_length)
    if adjusted > BOARD_MAX_TEXT_LENGTH:
        return f"The design has {adjusted} stretched texts; a board allows {BOARD_MAX_TEXT_LENGTH}."
    return None


class StepsError(ValueError):
    """A step assignment breaks the contract; the message is safe to show."""


def _plain_label(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise StepsError("A step label must be text.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise StepsError("A step label contains an invalid character.") from None
    out = " ".join(_CTRL.sub("", value).split())
    if any(c in out for c in "<>&\"\\`{}"):
        raise StepsError("A step label is plain text: no markup characters.")
    if len(out) > MAX_STEP_LABEL:
        raise StepsError(f"A step label is at most {MAX_STEP_LABEL} characters.")
    return out or None


def validate_steps(steps: Any, n_shapes: Optional[int] = None) -> List[Dict[str, Any]]:
    """An ordered partition of the shapes: 1-12 steps, every shape in exactly one, each step non-empty, an optional
    plain-text label of at most 40 characters. Without ``n_shapes`` the partition is checked against 0..max (the
    record carries no shape count; the caller that holds the design checks the count)."""
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise StepsError(f"A board has 1 to {MAX_STEPS} steps.")
    out, seen = [], set()
    for st in steps:
        if not isinstance(st, dict) or set(st) - {"shapes", "label"} or "shapes" not in st:
            raise StepsError("A step is {shapes, label}.")
        idx = st["shapes"]
        if not isinstance(idx, list) or not idx:
            raise StepsError("Every step needs at least one shape.")
        for i in idx:
            if isinstance(i, bool) or not isinstance(i, int) or i < 0 or i >= MAX_SHAPES:
                raise StepsError("A step names shapes by their index.")
            if i in seen:
                raise StepsError("A shape is in two steps.")
            seen.add(i)
        entry: Dict[str, Any] = {"shapes": list(idx)}
        label = _plain_label(st.get("label"))
        if label is not None:
            entry["label"] = label
        if st.get("label") not in (None, "") and entry.get("label") != st.get("label"):
            raise StepsError("A step label is plain text.")
        out.append(entry)
    total = n_shapes if n_shapes is not None else (max(seen) + 1 if seen else 0)
    if seen != set(range(total)):
        raise StepsError("Every shape must be in exactly one step.")
    return out


def derived_label(design: Design, indices: List[int]) -> Optional[str]:
    """The text of the first text shape of a step (in shape order), cut at 40 characters on a word boundary."""
    for i in sorted(indices):
        sh = design.shapes[i]
        if sh.kind == "text":
            text = " ".join(sh.text.split())
            if not text:
                continue
            if len(text) <= MAX_STEP_LABEL:
                return text
            cut = text[:MAX_STEP_LABEL + 1].rsplit(" ", 1)[0]
            return (cut if 0 < len(cut) <= MAX_STEP_LABEL else text[:MAX_STEP_LABEL]).rstrip()
    return None


def step_labels(design: Design, steps: List[Dict[str, Any]]) -> List[Optional[str]]:
    """What the narration can name per step: the label the user typed, else the derived one, else none."""
    return [st.get("label") or derived_label(design, st["shapes"]) for st in steps]


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


DROPPED_LABELS = {
    "image": "images", "foreignObject": "embedded HTML", "use": "linked shapes", "script": "scripts",
    "paint": "unreadable paints", "other": "other elements", "malformed": "malformed shapes", "line": "lines",
    "polyline": "lines", "polygon": "polygons", "bad_transform": "unsupported transforms", "switch": "switches",
    "text_truncated": "over-long texts", "gradient": "unreadable gradients",
    "gradient_limit": "gradients over the limit of 64", "gradient_stroke": "gradient strokes",
    "gradient_focal": "gradient focal points", "gradient_spread": "gradient spread modes",
    "stylesheet": "style sheets", "class_paint": "styled shapes", "tspan_paint": "styled text spans"}


def describe_dropped(dropped: Dict[str, int]) -> List[str]:
    """'2 images', '1 style sheet': what the import left out, in words (never the internal counter names)."""
    out = []
    for key, n in sorted(dropped.items()):
        if not n:
            continue
        label = DROPPED_LABELS.get(key, key.replace("_", " "))
        if n == 1 and label.endswith("ches"):
            label = label[:-2]
        elif n == 1 and label.endswith("s"):
            label = label[:-1]
        out.append(f"{n} {label}")
    return out


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
    skipped = describe_dropped(design.dropped)
    if skipped:
        style.warnings.append("Not imported: " + ", ".join(skipped) + ".")
    style.warnings.append(NOT_IMPORTED)
    style = validate_style(style)
    return ImportResult(style=style, notes=list(style.warnings))


def svg_to_json(data: bytes) -> Dict[str, Any]:
    """Penpot SVG bytes -> the closed shape model as plain JSON types (the spike converter, hardened).

    Only the typed fields of the model appear here; the upload's own text, markup and URLs never do.
    """
    d = parse_design(data)
    return {
        "canvas": {"width": d.width, "height": d.height, "x": d.ox, "y": d.oy},
        "background": d.background,
        "shapes": [dataclasses.asdict(s) for s in d.shapes],
        "dropped": dict(d.dropped),
        "not_imported": NOT_IMPORTED,
    }


def import_penpot(data: bytes, filename: str = "") -> ImportResult:
    """Penpot SVG bytes -> draft Style. The upload's sha256 is the provenance."""
    design = parse_design(data)
    return design_to_style(design, filename, hashlib.sha256(bytes(data)).hexdigest())

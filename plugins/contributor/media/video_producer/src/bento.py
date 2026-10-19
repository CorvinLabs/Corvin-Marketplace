"""``bento`` template (ADR-2260 decision 5): a grid of two to six tiles with a closed vocabulary.

The layout is chosen from ``LAYOUTS`` by tile count and the featured flag; a combination outside
the table is refused. There are no coordinates in the scene data, and every tile kind is a closed
set. Strings go through the same escaping and control-character rules as every other template.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

try:
    from .web_geometry import monotone_path
except ImportError:
    from web_geometry import monotone_path

# (tiles, featured?) -> layout name. Anything not listed here is refused (ADR-2260 table).
LAYOUTS: Dict[Tuple[int, bool], str] = {
    (2, False): "two",
    (3, False): "three", (3, True): "feature3",
    (4, False): "quad", (4, True): "feature4",
    (5, False): "five", (5, True): "feature5",
    (6, False): "six",
}
KINDS = ("number", "statement", "icon", "spark")
# A closed set of stroke glyphs (24x24 viewBox). Every name the template accepts is listed here.
ICONS: Dict[str, str] = {
    "check": "M5 12.5l4.5 4.5L19 7.5",
    "shield": "M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z",
    "bolt": "M13 2L4 14h7l-1 8 9-12h-7z",
    "chart": "M4 20V10M10 20V4M16 20v-7M2 20h20",
    "lock": "M6 11h12v9H6zM9 11V8a3 3 0 0 1 6 0v3",
    "users": "M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 20c0-3.3 2.7-6 6-6s6 2.7 6 6",
    "cloud": "M7 18a4 4 0 0 1-.5-8A6 6 0 0 1 18 9a4 4 0 0 1 0 9z",
}
MAX_TILE_VALUE = 1e9


def _wt():
    try:
        from . import web_templates as wt
    except ImportError:
        import web_templates as wt
    return wt


def validate(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalised ``bento`` scene data, or WebSceneError. Called by ``validate_scene_data``."""
    wt = _wt()
    wt._unknown(data, ("eyebrow", "title", "tiles", "featured"))
    raw = wt._list(data, "tiles", 2, 6)
    n = len(raw)
    featured = wt._int(data, "featured", 0, n - 1, None)
    key = (n, featured is not None)
    if key not in LAYOUTS:
        raise wt.WebSceneError(
            f"bento with {n} tiles{' and a featured tile' if featured is not None else ''} is not a layout "
            f"(allowed: 2, 3, 4, 5, 6 tiles; a featured tile only with 3, 4 or 5)")
    tiles = [_tile(t) for t in raw]
    return {"eyebrow": wt._text(data, "eyebrow", 40, False), "title": wt._text(data, "title", 80, False),
            "tiles": tiles, "featured": featured}


def layout_of(d: Dict[str, Any]) -> str:
    """The layout of validated data, from the table. It is derived, never stored: the normalised data is stored back
    into the scene and validated again by the job (cues, repair), and a stored ``layout`` would be a model-writable
    field that second pass has to refuse - a bento that failed it silently became a classic slide (Penpot tech demo,
    2026-10-18)."""
    return LAYOUTS[(len(d["tiles"]), d.get("featured") is not None)]


def _tile(t: Any) -> Dict[str, Any]:
    wt = _wt()
    if not isinstance(t, dict):
        raise wt.WebSceneError("bento tiles must be objects")
    kind = t.get("kind")
    if kind not in KINDS:
        raise wt.WebSceneError(f"bento tile kind must be one of {', '.join(KINDS)}")
    if kind == "number":
        wt._unknown(t, ("kind", "value", "decimals", "unit", "label"))
        value = wt._number(t, "value")
        if abs(value) >= MAX_TILE_VALUE:
            raise wt.WebSceneError(f"bento number must be below {MAX_TILE_VALUE:g}")
        return {"kind": kind, "value": value, "decimals": wt._int(t, "decimals", 0, 2, 0),
                "unit": wt._text(t, "unit", 8, False), "label": wt._text(t, "label", 60)}
    if kind == "statement":
        wt._unknown(t, ("kind", "text"))
        return {"kind": kind, "text": wt._text(t, "text", 140)}
    if kind == "icon":
        wt._unknown(t, ("kind", "name", "label"))
        name = t.get("name")
        if name not in ICONS:
            raise wt.WebSceneError(f"bento icon must be one of {', '.join(ICONS)}")
        return {"kind": kind, "name": name, "label": wt._text(t, "label", 60)}
    wt._unknown(t, ("kind", "values", "label"))  # spark
    values = []
    for v in wt._list(t, "values", 3, 12):
        values.append(wt._number({"v": v}, "v"))
    return {"kind": kind, "values": values, "label": wt._text(t, "label", 60)}


def scene_items(d: Dict[str, Any]) -> List[Tuple[str, int]]:
    """(label, reveal step) per tile in data order: one reveal step per tile, so the cue timeline
    shows a tile when the narration names it (ADR-2245). A statement has no label of its own, so
    its text is the thing the narration can name."""
    out = []
    for k, t in enumerate(d["tiles"]):
        label = t["text"] if t["kind"] == "statement" else t["label"]
        out.append((label, 2 + k))
    return out


def _spark(values: List[float]) -> str:
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    step = 200.0 / (len(values) - 1)
    pts = [(i * step, 54.0 - (v - lo) / span * 48.0) for i, v in enumerate(values)]
    return monotone_path(pts)


# The grid is a FIXED box (below an eyebrow and a title) so a tile can never grow into the header; every tile's
# type size is then computed from the cell it really gets, not from one pixel value for all layouts.
GRID_W, GRID_H, GAP = 1580.0, 600.0, 24.0


def cell_box(layout: str, featured: bool, pos: int = 0) -> Tuple[float, float]:
    """(width, height) in px of the cell of ``layout`` the tile at ``pos`` (placement order, featured first) gets - the
    arithmetic of the CSS grid below."""
    g = GAP
    col = lambda n, gaps=None: (GRID_W - g * (n - 1)) / n  # noqa: E731
    half = (GRID_H - g) / 2
    if layout == "two":
        return col(2), GRID_H
    if layout == "three":
        return col(3), GRID_H
    if layout == "quad":
        return col(2), half
    if layout == "six":
        return col(3), half
    if layout == "five":  # two cells of three of six columns, then three of two
        c6 = col(6)
        return (3 * c6 + 2 * g if pos < 2 else 2 * c6 + g), half
    if layout == "feature3":
        unit = (GRID_W - g) / 2.4
        return (1.4 * unit, GRID_H) if featured else (unit, half)
    if layout == "feature4":
        unit = (GRID_W - g) / 2.4
        return (1.4 * unit, GRID_H) if featured else (unit, (GRID_H - 2 * g) / 3)
    if layout == "feature5":
        unit = (GRID_H - g) / 2.1
        return (GRID_W, 1.1 * unit) if featured else (col(4), unit)
    raise ValueError(layout)


def _lines(text: str, px: float, width: float, em: float = 0.56) -> int:
    per = max(int(width / (px * em)), 1)
    return -(-len(text) // per)


def _cell(t: Dict[str, Any], k: int, featured: bool, box: Tuple[float, float]) -> str:
    wt = _wt()
    low = box[1] < 200
    pad_y, pad_x = (16, 24) if low else (28, 32)
    iw, ih = box[0] - 2 * pad_x, box[1] - 2 * pad_y
    lbl_px = 22 if low else 24
    cls = "t r" + (" feat" if featured else "")
    label_h = 0 if t["kind"] == "statement" else _lines(t["label"], lbl_px, iw, 0.6) * lbl_px * 1.3 + 8
    if t["kind"] == "number":
        text = f'{wt._fmt(t["value"], t["decimals"], "en")}{t["unit"] or ""}'
        fs = min(132 if featured else 84, iw / (max(len(text), 1) * 0.6), (ih - label_h - 8) / 1.2)
        body = f'<div class="num" style="font-size:{max(fs, 24):.0f}px">{wt._e(text)}</div>'
    elif t["kind"] == "statement":
        fs = 46 if featured else 32
        while fs > 18 and _lines(t["text"], fs, iw, 0.6) * fs * 1.25 > ih:
            fs -= 2
        body = f'<p class="stmt" style="font-size:{fs}px">{wt._e(t["text"])}</p>'
    elif t["kind"] == "icon":
        size = max(min(72 if featured else 56, ih - label_h - 8), 28)
        body = (f'<svg class="ico" style="width:{size:.0f}px;height:{size:.0f}px" viewBox="0 0 24 24" aria-hidden="true">'
                f'<path d="{ICONS[t["name"]]}"/></svg>')
    else:
        h = max(min(ih - label_h - 8, 220 if featured else 120), 24)
        body = (f'<svg class="spk" style="height:{h:.0f}px" viewBox="0 0 200 60" preserveAspectRatio="none" aria-hidden="true">'
                f'<path vector-effect="non-scaling-stroke" d="{_spark(t["values"])}"/></svg>')
    label = "" if t["kind"] == "statement" else f'<div class="lbl" style="font-size:{lbl_px}px">{wt._e(t["label"])}</div>'
    return f'<div class="{cls}" style="--i:{2 + k};padding:{pad_y}px {pad_x}px">{body}{label}</div>'


def build(d: Dict[str, Any]) -> str:
    """The bento body. The featured tile is placed first so the layout's first cell is always the large one;
    each tile keeps its data index for the reveal (``--i``)."""
    wt = _wt()
    tiles = d["tiles"]
    feat = d.get("featured")
    order = [feat] + [k for k in range(len(tiles)) if k != feat] if feat is not None else list(range(len(tiles)))
    layout = layout_of(d)
    cells = "".join(_cell(tiles[k], k, k == feat, cell_box(layout, k == feat, pos)) for pos, k in enumerate(order))
    return f'<div class="frame">{wt._header(d)}<div class="bento {layout_of(d)}">{cells}</div></div>'


CSS = """
.bento { display: grid; gap: 24px; width: 1580px; height: 600px; flex: none; margin-top: 40px; }
.bento > .t { display: flex; flex-direction: column; justify-content: center; gap: 8px; min-height: 0; min-width: 0;
  border-radius: 18px; background: var(--bg-card); }
.bento.two { grid-template-columns: 1fr 1fr; }
.bento.three { grid-template-columns: 1fr 1fr 1fr; }
.bento.quad { grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; }
.bento.five { grid-template-columns: repeat(6, 1fr); grid-template-rows: 1fr 1fr; }
.bento.five > .t:nth-child(-n+2) { grid-column: span 3; }
.bento.five > .t:nth-child(n+3) { grid-column: span 2; }
.bento.six { grid-template-columns: 1fr 1fr 1fr; grid-template-rows: 1fr 1fr; }
.bento.feature3 { grid-template-columns: 1.4fr 1fr; grid-template-rows: 1fr 1fr; }
.bento.feature3 > .feat { grid-row: 1 / 3; }
.bento.feature4 { grid-template-columns: 1.4fr 1fr; grid-template-rows: 1fr 1fr 1fr; }
.bento.feature4 > .feat { grid-row: 1 / 4; }
.bento.feature5 { grid-template-columns: repeat(4, 1fr); grid-template-rows: 1.1fr 1fr; }
.bento.feature5 > .feat { grid-column: 1 / 5; }
.bento .num { font-family: var(--font-heading); font-size: 84px; line-height: 1.2; color: var(--accent); }
.bento .feat .num { font-size: 132px; }
.bento .stmt { margin: 0; font-size: 32px; line-height: 1.25; }
.bento .feat .stmt { font-size: 46px; }
.bento .ico { width: 56px; height: 56px; fill: none; stroke: var(--accent); stroke-width: 1.6;
  stroke-linecap: round; stroke-linejoin: round; }
.bento .spk { width: 100%; fill: none; stroke: var(--accent); stroke-width: 3; }
.bento .lbl { opacity: .8; line-height: 1.3; }
"""

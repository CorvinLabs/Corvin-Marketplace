"""Board template (ADR-2260 decisions 1-4, 9, 10; T-0197): an imported design revealed by the narration.

A ``board`` scene names an asset id. The asset must be BOARD-READY: its stored typed model (``design.json``,
re-validated on every load) within every board bound, with ``steps`` assigned (an ordered partition of the shapes).
Nothing of the original upload is read: the design is written from the typed fields only (``penpot_import``).

  * every shape belongs to exactly one step; step order is reveal order; each step is one item for the cue
    timeline, labelled by the user's label or by the first text shape inside it (a step with neither is revealed
    by the storyboard's beats, else on the default even spacing - it is then NOT revealed when the narration names
    it);
  * motion is a closed set of four seekable CSS animations: rise (text), fade (rectangles, fill-only paths), scale
    (ellipses) and stroke draw-on for paths that HAVE a stroke (``stroke-dashoffset`` over ``pathLength=1``; a path
    with stroke and fill fades its fill in behind the drawn stroke). No ambient animation;
  * paint order is the design's shape order: each shape keeps its own position in the document and only carries its
    step's reveal index, so a step whose shapes are not contiguous never reorders the drawing;
  * text uses the producer's bundled fonts (``map_font``): the renderer loads no font from outside.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional, Tuple


def _wt():
    try:
        from . import web_templates  # noqa: PLC0415
    except ImportError:
        import web_templates  # noqa: PLC0415
    return web_templates


def _pi():
    try:
        from . import penpot_import  # noqa: PLC0415
    except ImportError:
        import penpot_import  # noqa: PLC0415
    return penpot_import


def _store_mod():
    try:
        from . import asset_store  # noqa: PLC0415
    except ImportError:
        import asset_store  # noqa: PLC0415
    return asset_store


AREA_W = 1580
AREA_H_HEADER = 600    # below eyebrow + title
AREA_H_FULL = 820      # no header: the whole frame


def _board(asset: Any, err=ValueError) -> Dict[str, Any]:
    """The board-ready record of ``asset`` from the bound tenant store, or ``err``. An unknown id, an asset of another
    tenant (not in this store) and an image without a stored model all get the SAME refusal as a missing one."""
    am = _store_mod()
    store = am.current()
    if store is None or not isinstance(asset, str) or not am.ID_RE.fullmatch(asset):
        raise err(f"unknown board asset {asset!r}")
    try:
        if store.design(asset) is None:
            raise err(f"unknown board asset {asset!r}")
        return store.board(asset)
    except am.AssetNotFound:
        raise err(f"unknown board asset {asset!r}") from None
    except am.AssetError as e:
        raise err(f"board {asset!r}: {e}") from None


def validate(data: Dict[str, Any], err=ValueError) -> Dict[str, Any]:
    wt = _wt()
    wt._unknown(data, ("eyebrow", "title", "asset"))
    out = {"eyebrow": wt._text(data, "eyebrow", 40, required=False), "title": wt._text(data, "title", 80, required=False),
           "asset": data.get("asset")}
    _board(out["asset"], err)
    return out


def reveal_steps(d: Dict[str, Any]) -> int:
    return len(_board(d["asset"])["steps"])


def scene_items(d: Dict[str, Any]) -> List[Tuple[str, int]]:
    """One item per step: what the narration can name ("" = nothing to name; beats or even spacing reveal it)."""
    return [(lb or "", 2 + k) for k, lb in enumerate(_board(d["asset"])["labels"])]


def scene_item_subs(d: Dict[str, Any]) -> List[str]:
    return [""] * len(_board(d["asset"])["steps"])


def step_of_shapes(steps: List[Dict[str, Any]], n: int) -> List[int]:
    out = [0] * n
    for k, st in enumerate(steps):
        for i in st["shapes"]:
            out[i] = k
    return out


def motion(shape: Any) -> str:
    """The closed set (ADR-2260 decision 4): which of the four motions a shape uses."""
    if shape.kind == "text":
        return "rise"
    if shape.kind == "ellipse":
        return "scale"
    if shape.kind == "path" and shape.stroke and shape.stroke_width > 0:
        return "draw"
    return "fade"


def board_svg(design: Any, steps: List[Dict[str, Any]], width: float, height: float) -> str:
    """The design as inline SVG for the slide: background static, each shape revealed with its step."""
    pi = _pi()
    from_font = pi.map_font
    pi.guard_design(design)
    used = pi._gradients_used(design)
    step = step_of_shapes(steps, len(design.shapes))
    n = pi._n
    parts = [f'<svg class="board-art" width="{width:.0f}" height="{height:.0f}" '
             f'viewBox="{n(design.ox)} {n(design.oy)} {n(design.width)} {n(design.height)}" preserveAspectRatio="xMidYMid meet">']
    if used:
        parts.append("<defs>" + "".join(pi._gradient_svg(g, i) for g, i in used.items()) + "</defs>")
    parts.append(f'<rect x="{n(design.ox)}" y="{n(design.oy)}" width="{n(design.width)}" height="{n(design.height)}" '
                 f'fill="{design.background or "#ffffff"}"/>')
    for i, sh in enumerate(design.shapes):
        if sh.kind == "text":
            sh = dataclasses.replace(sh, font_family=from_font(sh.font_family)[0])
        cue = f'style="--i:{2 + step[i]};--nofocus:1"'
        m = motion(sh)
        if m == "draw":
            if sh.fill:  # the fill fades in behind the stroke that draws on top of it
                fill_only = dataclasses.replace(sh, stroke=None, stroke_width=0.0)
                parts.append(f'<g class="bd r m-fade" {cue}>{pi._shape_svg(fill_only, used)}</g>')
            stroke_only = dataclasses.replace(sh, fill=None, fill_gradient=None, fill_opacity=1.0)
            parts.append(pi._shape_svg(stroke_only, used, f'class="bdraw" pathLength="1" {cue}'))
        else:
            parts.append(f'<g class="bd r m-{m}" {cue}>{pi._shape_svg(sh, used)}</g>')
    parts.append("</svg>")
    return "".join(parts)


def fit(design: Any, has_header: bool) -> Tuple[float, float]:
    box_h = AREA_H_HEADER if has_header else AREA_H_FULL
    s = min(AREA_W / design.width, box_h / design.height)
    return design.width * s, design.height * s


def body(d: Dict[str, Any]) -> str:
    b = _board(d["asset"])
    has_header = bool(d.get("eyebrow") or d.get("title"))
    w, h = fit(b["design"], has_header)
    art = board_svg(b["design"], b["steps"], w, h)
    cls = "frame board-slide" + ("" if has_header else " center")
    return f'<div class="{cls}">{_wt()._header(d)}<div class="board" style="width:{w:.0f}px;height:{h:.0f}px">{art}</div></div>'


CSS = (
    ".board { margin-top: 36px; border-radius: 18px; overflow: hidden; border: 1px solid var(--border); flex-shrink: 0; }"
    ".board-slide.center { justify-content: center; }"
    ".board-slide.center .board { margin-top: 0; }"
    ".board-art { display: block; }"
    ".board .bd { transform-box: fill-box; transform-origin: center; }"
    ".board .bd.m-fade { animation-name: fade; }"
    ".board .bd.m-scale { animation-name: board-scale; }"
    "@keyframes board-scale { from { opacity: 0; transform: scale(.6); } to { opacity: 1; transform: none; } }"
    ".board .bdraw { stroke-dasharray: 1; stroke-dashoffset: 1; animation: draw 900ms var(--ease) both;"
    " animation-delay: var(--at); }"
)


def css(d: Optional[Dict[str, Any]] = None) -> str:
    return CSS

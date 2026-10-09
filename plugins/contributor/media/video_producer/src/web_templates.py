"""Web-slide templates (ADR-2238): validated scene data -> one self-contained HTML document.

Everything a slide shows passes through ``validate_scene_data`` (closed template
enum, typed fields, length limits) and is HTML-escaped when it is written. The
LLM picks a template and fills data; it never supplies markup. Design tokens
are validated with strict patterns because they are written into CSS.

The document is self-contained: fonts are inlined as data URIs, there is no
<script>, no url() other than those data URIs, and the renderer loads it with
JavaScript and network disabled.
"""

from __future__ import annotations

import base64
import html
import os
import stat as stat_mod
import json
import math
import random
import re
import zlib
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .web_geometry import layer_dag, monotone_path, nice_ticks, order_layers, polar
    from .web_timeline import SPARSE_TEMPLATES, Timeline
except ImportError:  # standalone script use (no package context)
    from web_geometry import layer_dag, monotone_path, nice_ticks, order_layers, polar
    from web_timeline import SPARSE_TEMPLATES, Timeline

WEB_DIR = Path(__file__).parent / "web"
DEFAULT_TOKENS_PATH = WEB_DIR / "design_tokens.json"
BASE_CSS_PATH = WEB_DIR / "css" / "base.css"

TEMPLATES = ("hero", "content", "stat", "diagram", "chart", "compare", "quote", "code",
             "line", "donut", "flow", "timeline", "cycle", "layers", "console_still")
THEMES = ("dark", "light")

# The "you are here" strip (PLAN-0942 D11): Corvin's layers as the website's
# platform-arch diagram draws them, top to bottom.
MAP_LAYERS: Dict[str, str] = {
    "channels": "Channels", "agents": "Agents", "engines": "Engines",
    "compute": "Pipelines · Compute", "data": "Data", "audit": "Audit",
}
CONSOLE_ASSET_DIR = Path(__file__).resolve().parent / "web" / "assets" / "console"
MAX_ASSET_BYTES = 256 * 1024


@lru_cache(maxsize=1)
def _console_catalog() -> Dict[str, Dict[str, Any]]:
    """Bundled console screenshots (scripts/build_console_assets.py). Missing = none."""
    try:
        raw = json.loads((CONSOLE_ASSET_DIR / "catalog.json").read_text())
    except (OSError, ValueError):
        return {}
    out = {}
    for key, entry in raw.items():
        f = CONSOLE_ASSET_DIR / str(entry.get("file", ""))
        if re.fullmatch(r"[a-z0-9_]{2,32}", key) and f.is_file() and f.parent == CONSOLE_ASSET_DIR \
                and f.stat().st_size <= MAX_ASSET_BYTES:
            spots = {}
            for name, spot in (entry.get("spots") or {}).items():
                if re.fullmatch(r"[a-z0-9_]{2,32}", name) and isinstance(spot, dict) \
                        and all(isinstance(spot.get(k), (int, float)) and 0 <= spot[k] <= 1 for k in ("x", "y")):
                    spots[name] = {"x": float(spot["x"]), "y": float(spot["y"]),
                                   "description": str(spot.get("description", ""))[:120]}
            out[key] = {"file": f, "caption": str(entry.get("caption", ""))[:160], "spots": spots,
                        "w": int(entry.get("width", 1600)), "h": int(entry.get("height", 1000))}
    return out


def console_assets() -> Dict[str, str]:
    """asset key -> caption (+ its named hotspots), for the storyboard prompt."""
    out = {}
    for k, v in _console_catalog().items():
        spots = "; ".join(f"{n} = {s['description']}" for n, s in v["spots"].items())
        out[k] = v["caption"] + (f" — spots: {spots}" if spots else " — no spots (no callouts or zoom)")
    return out


def _corvinOS_symbol_svg(size: int = 48) -> str:
    """The real mark from Corvin-Website/logo.svg: prompt chevron, underscore bar, gold dot."""
    return (f'<svg width="{size}" height="{size}" viewBox="12 12 96 96" '
            f'class="corvinOS-symbol" style="color:var(--text)">'
            f'<path fill="none" stroke="currentColor" stroke-width="8" stroke-linecap="round" '
            f'stroke-linejoin="round" d="M28 40 L56 60 L28 80"/>'
            f'<rect fill="currentColor" x="66" y="72" width="30" height="9" rx="2"/>'
            f'<circle cx="80" cy="50" r="10" fill="#C9A227"/>'
            f'<circle cx="80" cy="50" r="10" fill="none" stroke="currentColor" stroke-width="2"/></svg>')


LANGS = ("de", "en")

# family name -> (file, style) ; only bundled families may appear in tokens
BUNDLED_FONTS: Dict[str, List[Tuple[str, str]]] = {
    "Newsreader": [("Newsreader.woff2", "normal"), ("Newsreader-Italic.woff2", "italic")],
    "Instrument Sans": [("InstrumentSans.woff2", "normal")],
    "JetBrains Mono": [("JetBrainsMono.woff2", "normal")],
}

THEME_KEYS = ("bg", "bg_card", "border", "text", "text_muted", "text_faint", "accent", "accent_hi", "glow", "success")
_HEX = re.compile(r"#[0-9a-fA-F]{6}")
_RGBA = re.compile(r"rgba\((\d{1,3}), ?(\d{1,3}), ?(\d{1,3}), ?(0|1|0?\.\d{1,3}|1\.0)\)")
_EASING = re.compile(r"cubic-bezier\((-?\d(?:\.\d{1,3})?), ?(-?\d(?:\.\d{1,3})?), ?(-?\d(?:\.\d{1,3})?), ?(-?\d(?:\.\d{1,3})?)\)")
MAX_TOKENS_BYTES = 64 * 1024


class WebSceneError(ValueError):
    """Scene data or design tokens do not satisfy the template contract."""


# ── design tokens ───────────────────────────────────────────────────────────

def _valid_color(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if _HEX.fullmatch(value):
        return True
    m = _RGBA.fullmatch(value)
    return bool(m) and all(int(m.group(i)) <= 255 for i in (1, 2, 3))


def validate_tokens(tokens: Any) -> Dict[str, Any]:
    """Raise WebSceneError unless ``tokens`` is a complete, CSS-safe token set."""
    if not isinstance(tokens, dict):
        raise WebSceneError("design tokens must be a JSON object")
    for theme in THEMES:
        block = tokens.get(theme)
        if not isinstance(block, dict):
            raise WebSceneError(f"design tokens: missing theme {theme!r}")
        for key in THEME_KEYS:
            if not _valid_color(block.get(key)):
                raise WebSceneError(f"design tokens: {theme}.{key} must be #rrggbb or rgba(r, g, b, a), got {block.get(key)!r}")
    typo = tokens.get("typography")
    if not isinstance(typo, dict):
        raise WebSceneError("design tokens: missing typography")
    for key in ("heading_family", "body_family", "mono_family"):
        if typo.get(key) not in BUNDLED_FONTS:
            raise WebSceneError(
                f"design tokens: typography.{key}={typo.get(key)!r} is not a bundled font "
                f"({', '.join(BUNDLED_FONTS)}); an unbundled family would silently fall back"
            )
    anim = tokens.get("animation")
    if not isinstance(anim, dict):
        raise WebSceneError("design tokens: missing animation")
    rise = anim.get("rise_ms")
    if not isinstance(rise, int) or isinstance(rise, bool) or not 200 <= rise <= 3000:
        raise WebSceneError("design tokens: animation.rise_ms must be an integer in [200, 3000]")
    if not isinstance(anim.get("easing"), str) or not _EASING.fullmatch(anim["easing"]):
        raise WebSceneError("design tokens: animation.easing must be cubic-bezier(a, b, c, d)")
    return tokens


def load_tokens(path: Optional[Path] = None) -> Dict[str, Any]:
    """Read a token file: a regular file of at most 64 KB (no FIFO/device that could
    block or exhaust the host process), then strict validation."""
    p = Path(path) if path else DEFAULT_TOKENS_PATH
    try:
        st = os.stat(p)
        if not stat_mod.S_ISREG(st.st_mode) or st.st_size > MAX_TOKENS_BYTES:
            raise OSError
        with open(p, "rb") as f:
            tokens = json.loads(f.read(MAX_TOKENS_BYTES + 1).decode("utf-8"))
    except (OSError, ValueError):
        raise WebSceneError("design tokens file is not a readable JSON regular file under 64 KB") from None
    return validate_tokens(tokens)


@lru_cache(maxsize=1)
def _font_faces() -> str:
    rules = []
    for family, files in BUNDLED_FONTS.items():
        for filename, style in files:
            data = base64.b64encode((WEB_DIR / "fonts" / filename).read_bytes()).decode("ascii")
            rules.append(
                f"@font-face{{font-family:'{family}';font-style:{style};font-weight:100 900;"
                f"src:url(data:font/woff2;base64,{data}) format('woff2');}}"
            )
    return "".join(rules)


@lru_cache(maxsize=1)
def _base_css() -> str:
    return BASE_CSS_PATH.read_text(encoding="utf-8")


# ── scene data validation ───────────────────────────────────────────────────

_WS = re.compile(r"\s+")
# control characters, plus bidi overrides/isolates and zero-width characters, which
# would let generated text display differently from what it contains
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]")


def _encodable(value: str, key: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise WebSceneError(f"field {key!r} contains an invalid character (lone surrogate)") from None
    return value


def _text(data: dict, key: str, limit: int, required: bool = True) -> Optional[str]:
    value = data.get(key)
    if value is None or value == "":
        if required:
            raise WebSceneError(f"missing required field {key!r}")
        return None
    if not isinstance(value, str):
        raise WebSceneError(f"field {key!r} must be a string")
    value = _WS.sub(" ", _CTRL.sub("", _encodable(value, key))).strip()
    if not value and required:
        raise WebSceneError(f"missing required field {key!r}")
    if len(value) > limit:
        raise WebSceneError(f"field {key!r} is {len(value)} chars, limit {limit}")
    return value or None


def _code_line(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        raise WebSceneError("code lines must be strings")
    value = _CTRL.sub("", _encodable(value, "lines").replace("\t", "    ")).rstrip()
    if "\n" in value or "\r" in value:
        raise WebSceneError("a code line must not contain a line break")
    if len(value) > limit:
        raise WebSceneError(f"code line is {len(value)} chars, limit {limit}")
    return value


def _number(data: dict, key: str, required: bool = True) -> Optional[float]:
    value = data.get(key)
    if value is None:
        if required:
            raise WebSceneError(f"missing required field {key!r}")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WebSceneError(f"field {key!r} must be a finite number")
    try:
        value = float(value)
    except OverflowError:
        raise WebSceneError(f"field {key!r} is out of range") from None
    if not math.isfinite(value):
        raise WebSceneError(f"field {key!r} must be a finite number")
    if abs(value) > 1e12:
        raise WebSceneError(f"field {key!r} is out of range")
    return value + 0.0  # -0.0 -> 0.0


def _int(data: dict, key: str, lo: int, hi: int, default: Optional[int]) -> Optional[int]:
    value = data.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise WebSceneError(f"field {key!r} must be an integer in [{lo}, {hi}]")
    return value


def _list(data: dict, key: str, lo: int, hi: int) -> list:
    value = data.get(key)
    if not isinstance(value, list) or not lo <= len(value) <= hi:
        raise WebSceneError(f"field {key!r} must be a list of {lo}-{hi} items")
    return value


def _unknown(data: dict, allowed: Tuple[str, ...]) -> None:
    extra = sorted(set(data) - set(allowed))
    if extra:
        raise WebSceneError(f"unknown field(s) {extra}")


def validate_scene_data(template: Any, data: Any) -> Dict[str, Any]:
    """Return a normalised copy of ``data`` or raise WebSceneError."""
    if template not in TEMPLATES:
        raise WebSceneError(f"unknown template {template!r} (allowed: {', '.join(TEMPLATES)})")
    if not isinstance(data, dict):
        raise WebSceneError("template data must be a JSON object")
    out: Dict[str, Any] = {"eyebrow": _text(data, "eyebrow", 40, required=False)}

    if template == "hero":
        _unknown(data, ("eyebrow", "badge", "title", "accent", "subtitle"))
        out.update(badge=_text(data, "badge", 60, False), title=_text(data, "title", 70),
                   accent=_text(data, "accent", 60, False), subtitle=_text(data, "subtitle", 220, False))
    elif template == "content":
        _unknown(data, ("eyebrow", "title", "bullets"))
        out.update(title=_text(data, "title", 80),
                   bullets=[_text({"b": b}, "b", 110) for b in _list(data, "bullets", 1, 5)])
    elif template == "stat":
        _unknown(data, ("eyebrow", "value", "decimals", "prefix", "suffix", "label", "caption", "locale"))
        locale = data.get("locale", "en")
        if locale not in LANGS:
            raise WebSceneError(f"field 'locale' must be one of {LANGS}")
        value = _number(data, "value")
        if abs(value) >= 1e9:
            raise WebSceneError("stat value must be below 1e9")
        out.update(value=value, decimals=_int(data, "decimals", 0, 2, 0), locale=locale,
                   prefix=_text(data, "prefix", 4, False), suffix=_text(data, "suffix", 8, False),
                   label=_text(data, "label", 80), caption=_text(data, "caption", 200, False))
    elif template == "diagram":
        _unknown(data, ("eyebrow", "title", "nodes", "highlight"))
        nodes = []
        for n in _list(data, "nodes", 2, 6):
            if not isinstance(n, dict):
                raise WebSceneError("diagram nodes must be objects")
            _unknown(n, ("label", "sub"))
            nodes.append({"label": _text(n, "label", 28), "sub": _text(n, "sub", 48, False)})
        out.update(title=_text(data, "title", 80), nodes=nodes,
                   highlight=_int(data, "highlight", 0, len(nodes) - 1, None))
    elif template == "chart":
        _unknown(data, ("eyebrow", "title", "bars", "unit", "decimals", "highlight", "locale"))
        locale = data.get("locale", "en")
        if locale not in LANGS:
            raise WebSceneError(f"field 'locale' must be one of {LANGS}")
        bars = []
        for b in _list(data, "bars", 2, 8):
            if not isinstance(b, dict):
                raise WebSceneError("chart bars must be objects")
            _unknown(b, ("label", "value"))
            v = _number(b, "value")
            if v < 0:
                raise WebSceneError("chart values must be >= 0")
            bars.append({"label": _text(b, "label", 24), "value": v})
        if max(b["value"] for b in bars) <= 0:
            raise WebSceneError("chart needs at least one value > 0")
        out.update(title=_text(data, "title", 80), bars=bars, unit=_text(data, "unit", 8, False),
                   decimals=_int(data, "decimals", 0, 2, 0), locale=locale,
                   highlight=_int(data, "highlight", 0, len(bars) - 1, None))
    elif template == "compare":
        _unknown(data, ("eyebrow", "title", "left", "right"))
        sides = {}
        for side in ("left", "right"):
            s = data.get(side)
            if not isinstance(s, dict):
                raise WebSceneError(f"field {side!r} must be an object")
            _unknown(s, ("title", "points"))
            sides[side] = {"title": _text(s, "title", 40),
                           "points": [_text({"p": p}, "p", 90) for p in _list(s, "points", 1, 4)]}
        out.update(title=_text(data, "title", 80), **sides)
    elif template == "quote":
        _unknown(data, ("eyebrow", "quote", "attribution", "locale"))
        locale = data.get("locale", "en")
        if locale not in LANGS:
            raise WebSceneError(f"field 'locale' must be one of {LANGS}")
        out.update(quote=_text(data, "quote", 220), attribution=_text(data, "attribution", 80, False), locale=locale)
    elif template == "code":
        _unknown(data, ("eyebrow", "title", "language", "lines"))
        out.update(title=_text(data, "title", 80), language=_text(data, "language", 24, False),
                   lines=[_code_line(l, 90) for l in _list(data, "lines", 1, 12)])
    elif template == "line":
        _unknown(data, ("eyebrow", "title", "labels", "series", "unit", "decimals", "highlight", "locale"))
        labels = [_text({"x": x}, "x", 12) for x in _list(data, "labels", 3, 12)]
        series = []
        for sr in _list(data, "series", 1, 3):
            if not isinstance(sr, dict):
                raise WebSceneError("line series must be objects")
            _unknown(sr, ("name", "values"))
            values = [_number({"v": v}, "v") for v in _list(sr, "values", len(labels), len(labels))]
            series.append({"name": _text(sr, "name", 24, required=len(_list(data, "series", 1, 3)) > 1),
                           "values": values})
        out.update(title=_text(data, "title", 80), labels=labels, series=series,
                   unit=_text(data, "unit", 8, False), decimals=_int(data, "decimals", 0, 2, 0),
                   locale=_locale(data), highlight=_int(data, "highlight", 0, len(labels) - 1, None))
    elif template == "donut":
        _unknown(data, ("eyebrow", "title", "segments", "center_value", "center_label", "unit",
                        "decimals", "highlight", "locale"))
        segs = []
        for sg in _list(data, "segments", 2, 6):
            if not isinstance(sg, dict):
                raise WebSceneError("donut segments must be objects")
            _unknown(sg, ("label", "value"))
            v = _number(sg, "value")
            if v < 0:
                raise WebSceneError("donut values must be >= 0")
            segs.append({"label": _text(sg, "label", 28), "value": v})
        if sum(sg["value"] for sg in segs) <= 0:
            raise WebSceneError("donut needs at least one value > 0")
        out.update(title=_text(data, "title", 80), segments=segs,
                   center_value=_text(data, "center_value", 10, False),
                   center_label=_text(data, "center_label", 28, False),
                   unit=_text(data, "unit", 8, False), decimals=_int(data, "decimals", 0, 2, 0),
                   locale=_locale(data), highlight=_int(data, "highlight", 0, len(segs) - 1, None))
    elif template == "flow":
        _unknown(data, ("eyebrow", "title", "nodes", "edges", "highlight"))
        nodes, ids = [], []
        for nd in _list(data, "nodes", 2, 8):
            if not isinstance(nd, dict):
                raise WebSceneError("flow nodes must be objects")
            _unknown(nd, ("id", "label", "sub"))
            nid = nd.get("id")
            if not isinstance(nid, str) or not _ID.fullmatch(nid):
                raise WebSceneError("flow node id must match [a-z0-9_]{1,16}")
            if nid in ids:
                raise WebSceneError(f"duplicate flow node id {nid!r}")
            ids.append(nid)
            nodes.append({"id": nid, "label": _text(nd, "label", 24), "sub": _text(nd, "sub", 36, False)})
        edges, seen = [], set()
        for ed in _list(data, "edges", 1, 12):
            if not isinstance(ed, dict):
                raise WebSceneError("flow edges must be objects")
            _unknown(ed, ("from", "to", "label"))
            a, b = ed.get("from"), ed.get("to")
            if a not in ids or b not in ids:
                raise WebSceneError("flow edge endpoints must be node ids")
            if a == b or (a, b) in seen:
                raise WebSceneError("flow edges must not be self-loops or duplicates")
            seen.add((a, b))
            edges.append({"from": a, "to": b, "label": _text(ed, "label", 18, False)})
        try:
            layer = layer_dag(ids, [(e["from"], e["to"]) for e in edges])
        except ValueError as e:
            raise WebSceneError(str(e)) from None
        groups = order_layers(ids, [(e["from"], e["to"]) for e in edges], layer)
        if len(groups) > 5 or max(len(g) for g in groups) > 4:
            raise WebSceneError("flow layout allows at most 5 columns and 4 nodes per column")
        hl = data.get("highlight")
        if hl is not None and hl not in ids:
            raise WebSceneError("flow highlight must be a node id")
        out.update(title=_text(data, "title", 80), nodes=nodes, edges=edges, highlight=hl)
    elif template == "timeline":
        _unknown(data, ("eyebrow", "title", "events", "current"))
        events = []
        for ev in _list(data, "events", 2, 6):
            if not isinstance(ev, dict):
                raise WebSceneError("timeline events must be objects")
            _unknown(ev, ("when", "label", "sub"))
            events.append({"when": _text(ev, "when", 16), "label": _text(ev, "label", 28),
                           "sub": _text(ev, "sub", 60, False)})
        out.update(title=_text(data, "title", 80), events=events,
                   current=_int(data, "current", 0, len(events) - 1, None))
    elif template == "cycle":
        _unknown(data, ("eyebrow", "title", "caption", "center", "steps", "highlight"))
        steps = []
        for st in _list(data, "steps", 3, 6):
            if not isinstance(st, dict):
                raise WebSceneError("cycle steps must be objects")
            _unknown(st, ("label", "sub"))
            steps.append({"label": _text(st, "label", 22), "sub": _text(st, "sub", 40, False)})
        out.update(title=_text(data, "title", 60), caption=_text(data, "caption", 180, False),
                   center=_text(data, "center", 24, False), steps=steps,
                   highlight=_int(data, "highlight", 0, len(steps) - 1, None))
    elif template == "layers":
        _unknown(data, ("eyebrow", "title", "layers", "highlight"))
        layers = []
        for ly in _list(data, "layers", 2, 6):
            if not isinstance(ly, dict):
                raise WebSceneError("layers entries must be objects")
            _unknown(ly, ("label", "sub", "tag"))
            layers.append({"label": _text(ly, "label", 32), "sub": _text(ly, "sub", 64, False),
                           "tag": _text(ly, "tag", 12, False)})
        out.update(title=_text(data, "title", 80), layers=layers,
                   highlight=_int(data, "highlight", 0, len(layers) - 1, None))
    elif template == "console_still":
        _unknown(data, ("eyebrow", "title", "asset", "caption", "callouts", "zoom"))
        asset = data.get("asset")
        if asset not in _console_catalog():
            raise WebSceneError(f"unknown console asset {asset!r} (allowed: {', '.join(_console_catalog())})")
        spots = _console_catalog()[asset]["spots"]

        def spot(obj: dict) -> Dict[str, str]:
            name = obj.get("spot")
            if name not in spots:
                raise WebSceneError(f"unknown spot {name!r} for asset {asset!r} (allowed: {', '.join(spots) or 'none'})")
            return {"spot": name}  # coordinates are resolved at build time: validation stays idempotent

        callouts = []
        for c in (_list(data, "callouts", 0, 3) if "callouts" in data else []):
            if not isinstance(c, dict):
                raise WebSceneError("callouts entries must be objects")
            _unknown(c, ("spot", "label"))
            callouts.append({**spot(c), "label": _text(c, "label", 32)})
        zoom = None
        if data.get("zoom") is not None:
            z = data["zoom"]
            if not isinstance(z, dict):
                raise WebSceneError("zoom must be an object")
            _unknown(z, ("spot", "scale"))
            scale = _number(z, "scale")
            if not 1.0 <= scale <= 1.6:
                raise WebSceneError("zoom.scale must be between 1 and 1.6")
            zoom = {**spot(z), "scale": scale}
        out.update(title=_text(data, "title", 80), asset=asset, caption=_text(data, "caption", 120, False),
                   callouts=callouts, zoom=zoom)
    return out


_ID = re.compile(r"[a-z0-9_]{1,16}")


def _flow_layout(d: Dict[str, Any]) -> Tuple[Dict[str, int], List[List[str]]]:
    ids = [n["id"] for n in d["nodes"]]
    pairs = [(e["from"], e["to"]) for e in d["edges"]]
    layer = layer_dag(ids, pairs)
    return layer, order_layers(ids, pairs, layer)


def _flow_columns(d: Dict[str, Any]) -> int:
    return len(_flow_layout(d)[1]) if d.get("nodes") else 0


def _locale(data: dict) -> str:
    locale = data.get("locale", "en")
    if locale not in LANGS:
        raise WebSceneError(f"field 'locale' must be one of {LANGS}")
    return locale


def reveal_steps(template: str, data: Dict[str, Any]) -> int:
    """Number of staggered entrance steps (header steps excluded)."""
    if template == "flow":
        return _flow_columns(data) + 1
    return {
        "hero": 4,
        "content": len(data.get("bullets") or []),
        "stat": 3,
        "diagram": len(data.get("nodes") or []),
        "chart": len(data.get("bars") or []),
        "compare": 2,
        "quote": 2,
        "code": len(data.get("lines") or []),
        "line": 4,
        "donut": len(data.get("segments") or []),
        "timeline": len(data.get("events") or []),
        "cycle": len(data.get("steps") or []),
        "layers": len(data.get("layers") or []),
        "console_still": 1 + len(data.get("callouts") or []),
    }[template]


def scene_items(template: str, data: Dict[str, Any]) -> List[Tuple[str, int]]:
    """(label, reveal step) per data item, in data order (ADR-2245): what the
    narration can name, and which elements reveal and focus together."""
    d = data
    if template == "content":
        return [(b, 2 + k) for k, b in enumerate(d["bullets"])]
    if template == "diagram":
        return [(nd["label"], 2 + k) for k, nd in enumerate(d["nodes"])]
    if template == "chart":
        return [(b["label"], 2 + k) for k, b in enumerate(d["bars"])]
    if template == "compare":
        return [(d["left"]["title"], 2), (d["right"]["title"], 3)]
    if template == "code":
        return [(ln.strip(), 2 + k) for k, ln in enumerate(d["lines"])]
    if template == "donut":
        return [(sg["label"], 2 + k) for k, sg in enumerate(d["segments"])]
    if template == "flow":
        layer, _ = _flow_layout(d)
        return [(nd["label"], 2 + layer[nd["id"]]) for nd in d["nodes"]]
    if template == "timeline":
        return [(e["label"], 2 + k) for k, e in enumerate(d["events"])]
    if template == "cycle":
        return [(st["label"], 2 + k) for k, st in enumerate(d["steps"])]
    if template == "layers":
        n = len(d["layers"])
        return [(it["label"], 2 + (n - 1 - k)) for k, it in enumerate(d["layers"])]
    if template == "console_still":
        return [(c["label"], 3 + k) for k, c in enumerate(d.get("callouts") or [])]
    return []  # hero, quote, stat, line: one statement, no items to walk through


def scene_item_subs(template: str, data: Dict[str, Any]) -> List[str]:
    """Each item's secondary text (sub-line, bullet points, timestamp), aligned with scene_items."""
    d = data
    key = {"diagram": "nodes", "flow": "nodes", "cycle": "steps", "layers": "layers", "timeline": "events"}.get(template)
    if key:
        return [" ".join(x for x in (it.get("sub"), it.get("tag"), it.get("when")) if x) for it in d[key]]
    if template == "compare":
        return [" ".join(d["left"]["points"]), " ".join(d["right"]["points"])]
    return [""] * len(scene_items(template, d))


# Ambient motion (pulses, orbits, ring pulses) loops with this period once the
# entrance has settled; every ambient animation's duration must divide it so
# the renderer can sample exactly one seamless period (web_renderer).
AMBIENT_PERIOD_S = 4.0


def ambient_start(t0: float, stagger: float, steps: int, rise_ms: int) -> float:
    """When ambient motion begins: once the last staggered entrance step (index
    steps + 1, after eyebrow and title) has risen. Chart draws are scheduled
    inside that window, so nothing ambient moves over a half-drawn graphic."""
    return t0 + (steps + 2) * stagger + rise_ms / 1000.0


def timing(duration_s: float, steps: int) -> Tuple[float, float]:
    """(t0, stagger) in seconds: all content is on screen by ~55% of the narration."""
    t0 = 0.35
    window = min(max(duration_s * 0.55, 1.2), 9.0)
    stagger = min(max(window / max(steps + 2, 1), 0.18), 1.6)
    return t0, stagger


# ── HTML builders ───────────────────────────────────────────────────────────

def _e(s: Optional[str]) -> str:
    return html.escape(s or "", quote=True)


def _fmt(value: float, decimals: int, locale: str) -> str:
    s = f"{value:,.{decimals}f}"
    if locale == "de":
        s = s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return s


def _header(d: Dict[str, Any], title_cls: str = "title") -> str:
    parts = []
    if d.get("eyebrow"):
        parts.append(f'<div class="eyebrow r" style="--i:0">{_e(d["eyebrow"])}</div>')
    if d.get("title"):
        parts.append(f'<h2 class="{title_cls} r" style="--i:1">{_e(d["title"])}</h2>')
    return "".join(parts)


def _hero(d):
    out = ['<div class="frame center">']
    if d.get("badge"):
        out.append(f'<div class="badge r" style="--i:0"><i></i>{_e(d["badge"])}</div>')
    elif d.get("eyebrow"):
        out.append(f'<div class="eyebrow r" style="--i:0">{_e(d["eyebrow"])}</div>')
    title = _e(d["title"])
    if d.get("accent"):
        title += f'<br><span class="accent-italic">{_e(d["accent"])}</span>'
    size = "display" if len(d["title"]) + len(d.get("accent") or "") <= 48 else "display md"
    out.append(f'<h1 class="{size} r" style="--i:1">{title}</h1>')
    if d.get("subtitle"):
        out.append(f'<p class="lead r" style="--i:2">{_e(d["subtitle"])}</p>')
    out.append('<div class="rule r grow" style="--i:3"></div></div>')
    return "".join(out)


def _content(d):
    items = "".join(
        f'<li class="r" style="--i:{2 + k}"><span class="n">{k + 1:02d}</span><span>{_e(b)}</span></li>'
        for k, b in enumerate(d["bullets"])
    )
    return f'<div class="frame">{_header(d)}<ul class="bullets">{items}</ul></div>'


def _stat(d):
    text = _fmt(d["value"], d["decimals"], d["locale"])
    chars, k = [], 0
    if d.get("prefix"):
        chars.append(f'<span class="ch r" style="--i:2;font-size:.55em;margin-right:.08em">{_e(d["prefix"])}</span>')
    for ch in text:
        if ch.isdigit():
            strip = "".join(f"<span>{n % 10}</span>" for n in range(20))
            chars.append(f'<span class="odo"><span class="strip d{ch}" style="--d:{k}">{strip}</span></span>')
            k += 1
        else:
            chars.append(f'<span class="ch">{_e(ch)}</span>')
    if d.get("suffix"):
        chars.append(f'<span class="ch r" style="--i:2;font-size:.45em;margin-left:.12em;margin-bottom:.12em">{_e(d["suffix"])}</span>')
    out = ['<div class="frame center">']
    if d.get("eyebrow"):
        out.append(f'<div class="eyebrow r" style="--i:0">{_e(d["eyebrow"])}</div>')
    out.append(f'<div class="stat-value">{"".join(chars)}</div>')
    out.append(f'<div class="stat-label r" style="--i:3">{_e(d["label"])}</div>')
    if d.get("caption"):
        out.append(f'<div class="stat-caption r" style="--i:4">{_e(d["caption"])}</div>')
    out.append("</div>")
    return "".join(out)


def _diagram(d):
    nodes = d["nodes"]
    n = len(nodes)
    width, gap = 1580, 84
    w = min(340, (width - (n - 1) * gap) / n)
    x0 = (width - (n * w + (n - 1) * gap)) / 2
    cards, edges, pulses = [], [], []
    longest = max((len(word) for nd in nodes for word in nd["label"].split()), default=1)
    fs = max(22, min(40, int((w - 56) / (longest * 0.52))))
    for k, node in enumerate(nodes):
        x = x0 + k * (w + gap)
        hl = " hl" if d.get("highlight") == k else ""
        sub = f'<div class="s">{_e(node["sub"])}</div>' if node.get("sub") else ""
        cards.append(
            f'<div class="node r{hl}" style="--i:{2 + k};left:{x:.1f}px;width:{w:.1f}px">'
            f'<div class="k">{k + 1:02d}</div><div class="l" style="font-size:{fs}px">{_e(node["label"])}</div>{sub}</div>'
        )
        if k < n - 1:
            ax, bx, y = x + w + 10, x + w + gap - 14, 150
            edges.append(f'<path class="edge" pathLength="1" style="--i:{3 + k}" d="M{ax:.1f} {y} L{bx:.1f} {y}"/>')
            edges.append(f'<path class="head" style="--i:{3 + k}" d="M{bx + 12:.1f} {y} L{bx - 2:.1f} {y - 9} L{bx - 2:.1f} {y + 9} Z"/>')
            pulses.append(f'<i class="amb pulse" style="--amb:{3 + k};offset-path:path(\'M{ax:.1f} {y} L{bx:.1f} {y}\');--ph:{k * 0.5:.2f}s"></i>')
    svg = f'<svg width="{width}" height="300" viewBox="0 0 {width} 300">{"".join(edges)}</svg>'
    return f'<div class="frame">{_header(d)}<div class="flow{" dense" if n >= 5 else ""}">{svg}{"".join(pulses)}{"".join(cards)}</div></div>'


def _chart(d):
    vmax = max(b["value"] for b in d["bars"])
    unit = _e(d.get("unit"))
    cols = []
    for k, b in enumerate(d["bars"]):
        h = max(6, round(460 * b["value"] / vmax)) if b["value"] > 0 else 0
        hl = " hl" if d.get("highlight") == k else ""
        label = _fmt(b["value"], d["decimals"], d["locale"]) + (f" {unit}" if unit else "")
        cols.append(
            f'<div class="bar{hl}"><div class="v r" style="--i:{2 + k}">{label}</div>'
            f'<div class="col" style="--i:{2 + k};height:{h}px"></div>'
            f'<div class="lb r" style="--i:{2 + k}">{_e(b["label"])}</div></div>'
        )
    return f'<div class="frame">{_header(d)}<div class="chart{" dense" if len(d["bars"]) >= 6 else ""}">{"".join(cols)}</div></div>'


def _compare(d):
    def card(side, cls, i):
        pts = "".join(f"<li>{_e(p)}</li>" for p in side["points"])
        return f'<div class="card {cls} r" style="--i:{i}"><h3>{_e(side["title"])}</h3><ul>{pts}</ul></div>'
    return (f'<div class="frame">{_header(d)}<div class="compare">'
            f'{card(d["left"], "before", 2)}{card(d["right"], "after", 3)}</div></div>')


def _quote(d):
    open_q, close_q = ("„", "“") if d["locale"] == "de" else ("“", "”")
    out = ['<div class="frame center">']
    if d.get("eyebrow"):
        out.append(f'<div class="eyebrow r" style="--i:0">{_e(d["eyebrow"])}</div>')
    out.append(f'<blockquote class="quote r" style="--i:2"><span class="mark">{open_q}</span>'
               f'{_e(d["quote"])}<span class="mark">{close_q}</span></blockquote>')
    if d.get("attribution"):
        out.append(f'<div class="attribution r" style="--i:3">{_e(d["attribution"])}</div>')
    out.append("</div>")
    return "".join(out)


def _code(d):
    lines = []
    for k, raw in enumerate(d["lines"]):
        stripped = raw.lstrip()
        cls = " c" if stripped.startswith(("#", "//")) else ""
        if stripped.startswith("$ "):
            body = f'<span class="p">$</span>{_e(raw[raw.index("$") + 1:])}'
        else:
            body = _e(raw) or "&#8203;"
        lines.append(f'<span class="ln{cls}" style="--i:{2 + k}">{body}</span>')
    lang = f"<span>{_e(d.get('language'))}</span>" if d.get("language") else ""
    return (f'<div class="frame">{_header(d)}<div class="term r" style="--i:1">'
            f'<div class="bar-top"><i></i><i></i><i></i>{lang}</div><pre>{"".join(lines)}</pre></div></div>')


_VIZ_W = 1580


def _tick_decimals(ticks: List[float], decimals: int) -> int:
    step = ticks[1] - ticks[0] if len(ticks) > 1 else 1.0
    need = 0 if step >= 1 else min(2, int(math.ceil(-math.log10(step) - 1e-9)))
    return max(decimals, need)


def _spread(ys: List[float], gap: float) -> List[float]:
    """Push label baselines apart so no two are closer than ``gap`` (order kept)."""
    order = sorted(range(len(ys)), key=lambda k: ys[k])
    out = list(ys)
    for a, b in zip(order, order[1:]):
        if out[b] - out[a] < gap:
            out[b] = out[a] + gap
    return out


def _line(d):
    labels, series = d["labels"], d["series"]
    W, H = _VIZ_W, 540
    left, right, top, bottom = 110, 190, 34, 70
    pw, ph = W - left - right, H - top - bottom
    values = [v for sr in series for v in sr["values"]]
    ticks = nice_ticks(min(min(values), 0.0), max(max(values), 0.0), 5)
    lo, hi = ticks[0], ticks[-1]
    n = len(labels)
    unit = d.get("unit")
    suffix = f" {unit}" if unit else ""

    def X(i: int) -> float:
        return left + pw * i / (n - 1)

    def Y(v: float) -> float:
        return top + ph * (1 - (v - lo) / (hi - lo))

    tick_dec = _tick_decimals(ticks, d["decimals"])
    svg = ['<defs><linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1">'
           '<stop offset="0" class="ag0"/><stop offset="1" class="ag1"/></linearGradient></defs>']
    for k, tv in enumerate(ticks):
        y = Y(tv)
        svg.append(f'<line class="grid{" zero" if tv == 0 else ""}" x1="{left}" x2="{W - right + 30}" '
                   f'y1="{y:.1f}" y2="{y:.1f}" style="--k:{k}"/>')
        svg.append(f'<text class="ytick" x="{left - 24}" y="{y + 8:.1f}" text-anchor="end" style="--k:{k}">'
                   f'{_e(_fmt(tv, tick_dec, d["locale"]))}</text>')
    for i, lab in enumerate(labels):
        svg.append(f'<text class="xtick" x="{X(i):.1f}" y="{H - 18}" text-anchor="middle" '
                   f'style="--f:{i / (n - 1):.3f}">{_e(lab)}</text>')
    base = Y(0.0) if lo <= 0 <= hi else Y(lo)
    ends = []
    for k, sr in enumerate(series):
        pts = [(X(i), Y(v)) for i, v in enumerate(sr["values"])]
        path = monotone_path(pts)
        if k == 0:
            svg.append(f'<path class="area" d="{path}L{pts[-1][0]:.1f},{base:.1f}L{pts[0][0]:.1f},{base:.1f}Z"/>')
        svg.append(f'<path class="ln c{k}" pathLength="1" d="{path}"/>')
        for i, (x, y) in enumerate(pts):
            svg.append(f'<circle class="pt c{k}" cx="{x:.1f}" cy="{y:.1f}" r="7" style="--f:{i / (n - 1):.3f}"/>')
        ends.append((k, pts[-1], sr["values"][-1]))
    label_ys = _spread([p[1] + 10 for _, p, _ in ends], 40)
    for (k, (x, _), v), ly in zip(ends, label_ys):
        svg.append(f'<text class="endv c{k}" x="{x + 24:.1f}" y="{ly:.1f}">'
                   f'{_e(_fmt(v, d["decimals"], d["locale"]) + suffix)}</text>')
    x_last, y_last = ends[0][1]
    svg.append(f'<circle class="amb ring-pulse c0" cx="{x_last:.1f}" cy="{y_last:.1f}" r="7"/>')
    h = d.get("highlight")
    if h is not None:
        x, y = X(h), Y(series[0]["values"][h])
        text = _fmt(series[0]["values"][h], d["decimals"], d["locale"]) + suffix
        w = 40 + 17 * len(text)
        by = y - 78 if y - 78 > -20 else y + 26
        svg.append(f'<g class="callout"><line class="guide" x1="{x:.1f}" x2="{x:.1f}" y1="{y + 12:.1f}" y2="{base:.1f}"/>'
                   f'<rect x="{x - w / 2:.1f}" y="{by:.1f}" width="{w:.0f}" height="50" rx="14"/>'
                   f'<text x="{x:.1f}" y="{by + 34:.1f}" text-anchor="middle">{_e(text)}</text></g>')
    legend = ""
    if len(series) > 1:
        items = "".join(f'<span><i class="sw c{k}"></i>{_e(sr["name"])}</span>' for k, sr in enumerate(series))
        legend = f'<div class="legend r" style="--i:2">{items}</div>'
    return (f'<div class="frame">{_header(d)}{legend}<div class="viz" style="height:{H}px">'
            f'<svg class="viz-svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{"".join(svg)}</svg></div></div>')


def _pct(p: float, locale: str) -> str:
    return f"{p:.0f} %" if locale == "de" else f"{p:.0f}%"


def _donut(d):
    segs = d["segments"]
    total = sum(sg["value"] for sg in segs)
    size, r = 540, 200
    c = size / 2
    unit = d.get("unit")
    suffix = f" {unit}" if unit else ""
    hl = d.get("highlight")
    arcs, rows, cum = [], [], 0.0
    for k, sg in enumerate(segs):
        pct = 100.0 * sg["value"] / total
        cls = " hl" if hl == k else ""
        if pct > 0:
            dash = max(pct - 0.8, 0.05) if pct < 100 else 100
            arcs.append(f'<circle class="seg c{k}{cls}" cx="{c:.0f}" cy="{c:.0f}" r="{r}" pathLength="100" '
                        f'stroke-dasharray="{dash:.3f} 100" stroke-dashoffset="{-cum:.3f}" style="--i:{2 + k}"/>')
        cum += pct
        rows.append(
            f'<div class="lg-row r{cls}" style="--i:{2 + k}"><i class="sw c{k}"></i>'
            f'<span class="lg-l">{_e(sg["label"])}</span>'
            + ("" if unit == "%" else  # the value already is the share: one column, not two
               f'<span class="lg-v">{_e(_fmt(sg["value"], d["decimals"], d["locale"]) + suffix)}</span>')
            + f'<span class="lg-p">{_pct(pct, d["locale"])}</span></div>'
        )
    if d.get("center_value"):
        cv, cl = d["center_value"], d.get("center_label")
    elif hl is not None:
        cv, cl = _pct(100.0 * segs[hl]["value"] / total, d["locale"]), d.get("center_label") or segs[hl]["label"]
    else:
        cv, cl = _fmt(total, d["decimals"], d["locale"]) + suffix, d.get("center_label")
    center = f'<div class="dn-v">{_e(cv)}</div>' + (f'<div class="dn-l">{_e(cl)}</div>' if cl else "")
    svg = (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
           f'<circle class="track" cx="{c:.0f}" cy="{c:.0f}" r="{r}"/>'
           f'<g transform="rotate(-90 {c:.0f} {c:.0f})">{"".join(arcs)}</g></svg>')
    return (f'<div class="frame">{_header(d)}<div class="donut"><div class="dn-chart">{svg}'
            f'<div class="dn-center r" style="--i:{2 + len(segs)}">{center}</div></div>'
            f'<div class="dn-legend">{"".join(rows)}</div></div></div>')


def _flow(d):
    layer, groups = _flow_layout(d)
    nodes = {nd["id"]: nd for nd in d["nodes"]}
    W, H = _VIZ_W, 560
    cols = len(groups)
    gapx = 140 if cols > 1 else 0
    w = min(300.0, (W - (cols - 1) * gapx) / cols)
    h = 120 if any(nd.get("sub") for nd in d["nodes"]) else 88
    x0 = (W - (cols * w + (cols - 1) * gapx)) / 2
    pos = {}
    for k, g in enumerate(groups):
        for j, nid in enumerate(g):
            pos[nid] = (x0 + k * (w + gapx), H * (j + 0.5) / len(g))
    svg, pulses, labels, cards = [], [], [], []
    for m, e in enumerate(d["edges"]):
        (ax, ay), (bx, by) = pos[e["from"]], pos[e["to"]]
        x1, y1, x2, y2 = ax + w + 8, ay, bx - 16, by
        dx = (x2 - x1) * 0.5
        path = f"M{x1:.1f} {y1:.1f} C{x1 + dx:.1f} {y1:.1f} {x2 - dx:.1f} {y2:.1f} {x2:.1f} {y2:.1f}"
        i = 2 + layer[e["to"]]
        svg.append(f'<path class="edge" pathLength="1" style="--i:{i}" d="{path}"/>')
        svg.append(f'<path class="head" style="--i:{i}" d="M{x2 + 13:.1f} {y2:.1f} L{x2 - 1:.1f} {y2 - 9:.1f} '
                   f'L{x2 - 1:.1f} {y2 + 9:.1f} Z"/>')
        pulses.append(f'<i class="amb pulse" style="--amb:{i};offset-path:path(\'{path}\');--ph:{(m * 0.55) % 2:.2f}s"></i>')
        if e.get("label"):
            # a dimmed label pill turns translucent and the edge strikes through it: never focus-dimmed
            labels.append(f'<div class="elabel r" style="--i:{i};--nofocus:1;left:{(x1 + x2) / 2 - 100:.1f}px;'
                          f'top:{(y1 + y2) / 2 - 22:.1f}px"><span>{_e(e["label"])}</span></div>')
    for nid, (x, cy) in pos.items():
        nd = nodes[nid]
        cls = " hl" if d.get("highlight") == nid else ""
        sub = f'<div class="s">{_e(nd["sub"])}</div>' if nd.get("sub") else ""
        cards.append(f'<div class="gnode r{cls}" style="--i:{2 + layer[nid]};left:{x:.1f}px;top:{cy - h / 2:.1f}px;'
                     f'width:{w:.1f}px;height:{h}px"><div class="l">{_e(nd["label"])}</div>{sub}</div>')
    return (f'<div class="frame">{_header(d)}<div class="viz" style="height:{H}px">'
            f'<svg class="viz-svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{"".join(svg)}</svg>'
            f'{"".join(pulses)}{"".join(labels)}{"".join(cards)}</div></div>')


def _timeline(d):
    ev = d["events"]
    n = len(ev)
    W, H, ay, pad = _VIZ_W, 430, 150, 140
    xs = [pad + i * (W - 2 * pad) / (n - 1) for i in range(n)]
    cur = d.get("current")
    reach = cur if cur is not None else n - 1
    cw = min(330.0, (W - 2 * pad) / (n - 1) - 30) if n > 1 else 330.0
    svg = [f'<line class="tl-base" x1="30" x2="{W - 30}" y1="{ay}" y2="{ay}"/>',
           f'<line class="tl-prog" pathLength="1" x1="30" x2="{xs[reach]:.1f}" y1="{ay}" y2="{ay}" '
           f'style="--n:{reach + 1};--tl-at:var(--tl-at0);--tl-span:var(--tl-span0)"/>']
    html_parts = []
    for k, (x, e) in enumerate(zip(xs, ev)):
        state = "cur" if k == cur else ("done" if k < reach or cur is None else "next")
        svg.append(f'<circle class="tl-dot {state}" cx="{x:.1f}" cy="{ay}" r="{17 if state == "cur" else 12}" '
                   f'style="--i:{2 + k}"/>')
        if state == "cur":
            svg.append(f'<circle class="amb ring-pulse c0" style="--amb:{2 + k}" cx="{x:.1f}" cy="{ay}" r="17"/>')
        left = x - cw / 2
        html_parts.append(f'<div class="tl-when r {state}" style="--i:{2 + k};left:{left:.1f}px;top:{ay - 92}px;'
                          f'width:{cw:.1f}px">{_e(e["when"])}</div>')
        sub = f'<div class="s">{_e(e["sub"])}</div>' if e.get("sub") else ""
        html_parts.append(f'<div class="tl-label r {state}" style="--i:{2 + k};left:{left:.1f}px;top:{ay + 44}px;'
                          f'width:{cw:.1f}px"><div class="l">{_e(e["label"])}</div>{sub}</div>')
    return (f'<div class="frame">{_header(d)}<div class="viz" style="height:{H}px">'
            f'<svg class="viz-svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{"".join(svg)}</svg>'
            f'{"".join(html_parts)}</div></div>')


def _cycle(d):
    steps = d["steps"]
    n = len(steps)
    VW, VH, cx, cy, R = 960, 780, 480, 390, 215
    angles = [-math.pi / 2 + 2 * math.pi * k / n for k in range(n)]
    gap = 0.2
    svg = [f'<circle class="cy-track" cx="{cx}" cy="{cy}" r="{R}"/>']
    for k in range(n):
        a1 = angles[k] + gap
        a2 = angles[(k + 1) % n] - gap + (2 * math.pi if k == n - 1 else 0)
        (x1, y1), (x2, y2) = polar(cx, cy, R, a1), polar(cx, cy, R, a2)
        arc_i = 3 + k if k < n - 1 else 2 + n
        svg.append(f'<path class="cy-arc" pathLength="1" style="--i:{arc_i}" '
                   f'd="M{x1:.1f} {y1:.1f} A{R} {R} 0 0 1 {x2:.1f} {y2:.1f}"/>')
        tx, ty, nx, ny = -math.sin(a2), math.cos(a2), math.cos(a2), math.sin(a2)
        svg.append(f'<path class="cy-head" style="--i:{arc_i}" d="M{x2 + tx * 15:.1f} {y2 + ty * 15:.1f} '
                   f'L{x2 - nx * 9:.1f} {y2 - ny * 9:.1f} L{x2 + nx * 9:.1f} {y2 + ny * 9:.1f} Z"/>')
    html_parts = []
    for k, (a, st) in enumerate(zip(angles, steps)):
        x, y = polar(cx, cy, R, a)
        cls = " hl" if d.get("highlight") == k else ""
        svg.append(f'<g class="cy-node{cls}" style="--i:{2 + k}"><circle cx="{x:.1f}" cy="{y:.1f}" r="31"/>'
                   f'<text x="{x:.1f}" y="{y + 8:.1f}" text-anchor="middle">{k + 1:02d}</text></g>')
        lx, ly = polar(cx, cy, R + 58, a)
        c, s_ = math.cos(a), math.sin(a)
        lw = 250
        if c > 0.3:
            left, top, align = lx, ly - 34, "left"
        elif c < -0.3:
            left, top, align = lx - lw, ly - 34, "right"
        else:
            left, top, align = lx - lw / 2, (ly - 84 if s_ < 0 else ly - 6), "center"
        sub = f'<div class="s">{_e(st["sub"])}</div>' if st.get("sub") else ""
        html_parts.append(f'<div class="cy-label r{cls}" style="--i:{2 + k};left:{left:.1f}px;top:{top:.1f}px;'
                          f'width:{lw}px;text-align:{align}"><div class="l">{_e(st["label"])}</div>{sub}</div>')
    orbit = (f"M{cx} {cy - R} A{R} {R} 0 1 1 {cx} {cy + R} A{R} {R} 0 1 1 {cx} {cy - R}")
    center = (f'<div class="cy-center r" style="--i:{2 + n};left:{cx - 160}px;top:{cy - 40}px">{_e(d["center"])}</div>'
              if d.get("center") else "")
    text = []
    if d.get("eyebrow"):
        text.append(f'<div class="eyebrow r" style="--i:0">{_e(d["eyebrow"])}</div>')
    if d.get("title"):
        text.append(f'<h2 class="title r" style="--i:1">{_e(d["title"])}</h2>')
    if d.get("caption"):
        text.append(f'<p class="caption r" style="--i:2">{_e(d["caption"])}</p>')
    return (f'<div class="frame split"><div class="split-text">{"".join(text)}</div>'
            f'<div class="viz" style="width:{VW}px;height:{VH}px">'
            f'<svg class="viz-svg" width="{VW}" height="{VH}" viewBox="0 0 {VW} {VH}">{"".join(svg)}</svg>'
            f'<i class="amb orbit" style="--amb:{2 + n};offset-path:path(\'{orbit}\')"></i>{center}{"".join(html_parts)}</div></div>')


def _layers(d):
    ly = d["layers"]
    n = len(ly)
    rows = []
    for k, item in enumerate(ly):
        cls = " hl" if d.get("highlight") == k else ""
        sub = f'<span class="sl-s">{_e(item["sub"])}</span>' if item.get("sub") else ""
        tag = f'<span class="sl-t">{_e(item["tag"])}</span>' if item.get("tag") else ""
        shine = f'<i class="amb shine" style="--amb:{2 + (n - 1 - k)}"></i>' if cls else ""
        rows.append(f'<div class="slab r{cls}" style="--i:{2 + (n - 1 - k)}"><span class="sl-l">{_e(item["label"])}</span>'
                    f'{sub}{tag}{shine}</div>')
    return f'<div class="frame">{_header(d)}<div class="stack">{"".join(rows)}</div></div>'


def _console_still(d):
    entry = _console_catalog()[d["asset"]]
    data = base64.b64encode(entry["file"].read_bytes()).decode("ascii")
    # fit the image into the content box keeping its aspect ratio; callouts sit in
    # that box in percent, so they stay on target while it zooms
    w, h = entry["w"], entry["h"]
    scale = min(1480 / w, 640 / h)
    bw, bh = round(w * scale), round(h * scale)
    spots = entry["spots"]
    z = dict(d.get("zoom") or {"scale": 1.0})
    z.update(spots.get(z.get("spot"), {"x": 0.5, "y": 0.5}))
    marks = []
    for k, c in enumerate(d.get("callouts") or []):
        c = {**c, **spots[c["spot"]]}
        side = " left" if c["x"] > 0.62 else ""
        marks.append(f'<div class="callout{side}" style="--i:{3 + k};left:{c["x"] * 100:.2f}%;top:{c["y"] * 100:.2f}%">'
                     f'<i></i><span>{_e(c["label"])}</span></div>')
    cap = f'<div class="still-cap r" style="--i:{3 + len(marks)}">{_e(d["caption"])}</div>' if d.get("caption") else ""
    return (f'<div class="frame still">{_header(d)}'
            f'<div class="still-box r" style="--i:2;width:{bw}px;height:{bh}px">'
            f'<div class="still-zoom" style="transform-origin:{z["x"] * 100:.2f}% {z["y"] * 100:.2f}%;--zs:{z["scale"]:.3f}">'
            f'<img alt="" src="data:image/jpeg;base64,{data}">{"".join(marks)}</div></div>{cap}</div>')


def _map_strip(focus: str) -> str:
    rows = "".join(f'<div class="mp{" on" if key == focus else ""}">{_e(label)}</div>'
                   for key, label in MAP_LAYERS.items())
    return f'<div class="map">{rows}</div>'


_BUILDERS = {"hero": _hero, "content": _content, "stat": _stat, "diagram": _diagram,
             "chart": _chart, "compare": _compare, "quote": _quote, "code": _code,
             "line": _line, "donut": _donut, "flow": _flow, "timeline": _timeline, "cycle": _cycle,
             "console_still": _console_still,
             "layers": _layers}


def _stars(seed: int) -> str:
    """Constellation dots and a few short lines, kept out of the content area."""
    rng = random.Random(seed)

    # Graphics span the full 1580 px content width (170..1750) and the wordmark
    # sits at the bottom left: keep decoration in the outer margin only.
    def outside(x: float, y: float) -> bool:
        return not (140 < x < 1780 and 80 < y < 1040)

    pts: List[Tuple[float, float, float, float]] = []
    while len(pts) < 18:
        x, y = rng.uniform(50, 1870), rng.uniform(40, 1040)
        if outside(x, y):
            pts.append((x, y, rng.uniform(1.2, 2.6), rng.uniform(.25, .7)))
    dots = "".join(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.1f}" opacity="{o:.2f}"/>' for x, y, r, o in pts)
    lines = []
    for i, (ax, ay, _, _) in enumerate(pts):
        for bx, by, _, _ in pts[i + 1:]:
            if len(lines) >= 4:
                break
            mx, my = (ax + bx) / 2, (ay + by) / 2
            if math.hypot(ax - bx, ay - by) < 320 and all(
                    outside(ax + (bx - ax) * f, ay + (by - ay) * f) for f in (0.25, 0.5, 0.75)):
                lines.append(f'<line x1="{ax:.0f}" y1="{ay:.0f}" x2="{bx:.0f}" y2="{by:.0f}"/>')
    return f'<svg class="stars" width="1920" height="1080">{"".join(lines)}{dots}</svg>'


def build_document(
    template: str,
    data: Dict[str, Any],
    *,
    duration_s: float,
    theme: str = "dark",
    tokens: Optional[Dict[str, Any]] = None,
    scene_index: Optional[int] = None,
    total_scenes: Optional[int] = None,
    lang: str = "en",
    map_focus: Optional[str] = None,
    timeline: Optional["Timeline"] = None,
    compact: bool = False,
    chips: bool = True,
) -> str:
    """Validate and render one slide to a self-contained HTML string.

    With a ``timeline`` (ADR-2245) every element is revealed at its cue and a
    focus clock leads the eye; without one the reveal is spread evenly over the
    first 55 % of the narration, as before."""
    d = validate_scene_data(template, data)
    if theme not in THEMES:
        raise WebSceneError(f"unknown theme {theme!r} (allowed: {', '.join(THEMES)})")
    if lang not in LANGS:
        lang = "en"
    tokens = validate_tokens(tokens) if tokens is not None else load_tokens()
    palette, typo, anim = tokens[theme], tokens["typography"], tokens["animation"]
    if timeline is None:
        t0, stagger = timing(duration_s, reveal_steps(template, d))
        tend = ambient_start(t0, stagger, reveal_steps(template, d), anim["rise_ms"])
        time_of = (lambda s: t0 + s * stagger)
        chip_list: List[Tuple[float, str]] = []
    else:
        t0, stagger = max(timeline.first_content - 0.2, 0.35), 0.45
        tend = timeline.last_reveal + anim["rise_ms"] / 1000.0
        time_of = timeline.time_of
        chip_list = timeline.chips if chips and template in SPARSE_TEMPLATES else []

    css_vars = "".join(f"--{k.replace('_', '-')}:{palette[k]};" for k in THEME_KEYS)
    css_vars += (f"--font-heading:'{typo['heading_family']}',serif;"
                 f"--font-body:'{typo['body_family']}',sans-serif;"
                 f"--font-mono:'{typo['mono_family']}',monospace;"
                 f"--rise:{anim['rise_ms']}ms;--ease:{anim['easing']};"
                 f"--t0:{t0:.3f}s;--stagger:{stagger:.3f}s;--tend:{tend:.3f}s;")
    if timeline is not None and template == "timeline":
        cur = d.get("current")
        reach = cur if cur is not None else len(d["events"]) - 1
        css_vars += (f"--tl-at0:{max(time_of(2) - 0.2, 0):.3f}s;"
                     f"--tl-span0:{max(time_of(2 + reach) - time_of(2) + 0.4, 0.4):.3f}s;")

    if map_focus is not None and map_focus not in MAP_LAYERS:
        raise WebSceneError(f"unknown map focus {map_focus!r} (allowed: {', '.join(MAP_LAYERS)})")
    # CorvinOS symbol: hexagon + rings + yellow accent dot (ADR-2238 Amendment)
    symbol = _corvinOS_symbol_svg(48)
    chrome = f'<div class="wordmark">{symbol}CorvinOS</div>'
    if scene_index and total_scenes:
        chrome += f"<div>{int(scene_index):02d} / {int(total_scenes):02d}</div>"
    seed = zlib.crc32(f"{template}|{d.get('title') or d.get('quote') or d.get('label') or ''}".encode("utf-8"))

    body = _BUILDERS[template](d)
    if scene_index == 1:
        body = _with_intro_mark(template, body)
    if chip_list:
        row = "".join(f'<span class="chip r" style="--i:{CHIP_STEP0 + c}">{_e(_clean_chip(t))}</span>'
                      for c, (_, t) in enumerate(chip_list))
        body = body[: body.rfind("</div>")] + f'<div class="chips">{row}</div></div>'
    focus_css, stage_style = "", ""
    if timeline is not None and timeline.focus:
        focus_css, stage_style = _focus_clock(timeline)
    focus_steps = set(timeline.item_steps) if timeline is not None and timeline.focus else set()

    def cue(m: "re.Match") -> str:
        step = int(m.group(1))
        at = chip_list[step - CHIP_STEP0][0] if step >= CHIP_STEP0 else time_of(step)
        out = f'style="--i:{step};--at:{at:.3f}s'
        if m.group(2):
            return out
        if step in focus_steps:
            # a tight glow: a wide soft one bands into dark contour rings once encoded to 8-bit H.264
            out += (f";filter:opacity(var(--f{step})) drop-shadow(0 0 calc(var(--g{step}) * 10px) "
                    f"rgb(from var(--accent) r g b / calc(var(--g{step}) * .55)))")
        return out

    body = re.sub(r'style="--i:(\d+)(;--nofocus:1)?', cue, body)
    body = re.sub(r"--amb:(\d+)", lambda m: f"--amb-at:{time_of(int(m.group(1))) + anim['rise_ms'] / 1000.0:.3f}s", body)
    classes = f"theme-{theme}" + (" compact" if compact else "")
    return (
        f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
        f"<style>{_font_faces()}:root{{{css_vars}}}{_base_css()}{focus_css}</style></head>"
        f'<body class="{classes}"><div class="stage"{stage_style}><div class="glow"></div><div class="ring"></div>'
        f"{_stars(seed)}{body}{_map_strip(map_focus) if map_focus else ''}"
        f"<div class=\"chrome\">{chrome}</div></div></body></html>"
    )


INTRO_MARK_PX = 150
INTRO_MARK_CORNER_PX = 120


def _with_intro_mark(template: str, body: str) -> str:
    """The CorvinOS mark, large, at the start of EVERY video: in flow above the title on the
    hero slide, a corner mark on the first slide when it is not a hero. Not an ``.r`` element,
    so it takes no reveal step and no focus."""
    if template == "hero":
        mark = f'<div class="intro-mark">{_corvinOS_symbol_svg(INTRO_MARK_PX)}</div>'
        return body.replace('<div class="frame center">', '<div class="frame center">' + mark, 1)
    return body + f'<div class="intro-mark corner">{_corvinOS_symbol_svg(INTRO_MARK_CORNER_PX)}</div>'


CHIP_STEP0 = 40
FOCUS_DIM = 0.38
FOCUS_FADE_S = 0.35


def _clean_chip(text: str) -> str:
    return " ".join(_CTRL.sub("", text).split())[:28]


def _focus_clock(tl: "Timeline") -> Tuple[str, str]:
    """One animation on the stage drives registered per-step numbers: --fN (opacity
    factor) and --gN (glow). Elements read them in their filter, so focus never
    competes with an element's own entrance animation (ADR-2245 §3)."""
    steps = tl.item_steps
    D = max(tl.duration, 0.1)

    def state(target: Optional[int]) -> str:
        return "".join(
            f"--f{s}:{1 if target is None or target == s else FOCUS_DIM};--g{s}:{1 if target == s else 0};"
            for s in steps)

    frames: List[Tuple[float, str]] = [(0.0, state(None))]
    current: Optional[int] = None
    for t, target in tl.focus:
        a, b = min(t, D), min(t + FOCUS_FADE_S, D)
        frames.append((a, state(current)))
        frames.append((b, state(target)))
        current = target
    frames.append((D, state(current)))
    kf = "".join(f"{100.0 * t / D:.4f}%{{{body}}}" for t, body in frames)
    props = "".join(
        f"@property --f{s}{{syntax:'<number>';inherits:true;initial-value:1}}"
        f"@property --g{s}{{syntax:'<number>';inherits:true;initial-value:0}}" for s in steps)
    return props + f"@keyframes fclock{{{kf}}}", f' style="animation:fclock {D:.3f}s linear 0s both"'


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
import json
import math
import random
import re
import zlib
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

WEB_DIR = Path(__file__).parent / "web"
DEFAULT_TOKENS_PATH = WEB_DIR / "design_tokens.json"
BASE_CSS_PATH = WEB_DIR / "css" / "base.css"

TEMPLATES = ("hero", "content", "stat", "diagram", "chart", "compare", "quote", "code")
THEMES = ("dark", "light")
LANGS = ("de", "en")

# family name -> (file, style) ; only bundled families may appear in tokens
BUNDLED_FONTS: Dict[str, List[Tuple[str, str]]] = {
    "Newsreader": [("Newsreader.woff2", "normal"), ("Newsreader-Italic.woff2", "italic")],
    "Instrument Sans": [("InstrumentSans.woff2", "normal")],
    "JetBrains Mono": [("JetBrainsMono.woff2", "normal")],
}

THEME_KEYS = ("bg", "bg_card", "border", "text", "text_muted", "text_faint", "accent", "accent_hi", "glow", "success")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_RGBA = re.compile(r"^rgba\((\d{1,3}), ?(\d{1,3}), ?(\d{1,3}), ?(0|1|0?\.\d{1,3}|1\.0)\)$")
_EASING = re.compile(r"^cubic-bezier\((-?\d(?:\.\d{1,3})?), ?(-?\d(?:\.\d{1,3})?), ?(-?\d(?:\.\d{1,3})?), ?(-?\d(?:\.\d{1,3})?)\)$")


class WebSceneError(ValueError):
    """Scene data or design tokens do not satisfy the template contract."""


# ── design tokens ───────────────────────────────────────────────────────────

def _valid_color(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if _HEX.match(value):
        return True
    m = _RGBA.match(value)
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
    if not isinstance(anim.get("easing"), str) or not _EASING.match(anim["easing"]):
        raise WebSceneError("design tokens: animation.easing must be cubic-bezier(a, b, c, d)")
    return tokens


def load_tokens(path: Optional[Path] = None) -> Dict[str, Any]:
    p = Path(path) if path else DEFAULT_TOKENS_PATH
    try:
        tokens = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise WebSceneError(f"design tokens unreadable at {p}: {e}") from None
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
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _text(data: dict, key: str, limit: int, required: bool = True) -> Optional[str]:
    value = data.get(key)
    if value is None or value == "":
        if required:
            raise WebSceneError(f"missing required field {key!r}")
        return None
    if not isinstance(value, str):
        raise WebSceneError(f"field {key!r} must be a string")
    value = _WS.sub(" ", _CTRL.sub("", value)).strip()
    if not value and required:
        raise WebSceneError(f"missing required field {key!r}")
    if len(value) > limit:
        raise WebSceneError(f"field {key!r} is {len(value)} chars, limit {limit}")
    return value or None


def _code_line(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        raise WebSceneError("code lines must be strings")
    value = _CTRL.sub("", value.replace("\t", "    ")).rstrip()
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
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise WebSceneError(f"field {key!r} must be a finite number")
    if abs(value) > 1e12:
        raise WebSceneError(f"field {key!r} is out of range")
    return float(value)


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
    return out


def reveal_steps(template: str, data: Dict[str, Any]) -> int:
    """Number of staggered entrance steps (header steps excluded)."""
    return {
        "hero": 4,
        "content": len(data.get("bullets") or []),
        "stat": 3,
        "diagram": len(data.get("nodes") or []),
        "chart": len(data.get("bars") or []),
        "compare": 2,
        "quote": 2,
        "code": len(data.get("lines") or []),
    }[template]


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
            chars.append(f'<span class="odo"><span class="strip d{ch}" style="--i:{k}">{strip}</span></span>')
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
    cards, edges = [], []
    for k, node in enumerate(nodes):
        x = x0 + k * (w + gap)
        hl = " hl" if d.get("highlight") == k else ""
        sub = f'<div class="s">{_e(node["sub"])}</div>' if node.get("sub") else ""
        cards.append(
            f'<div class="node r{hl}" style="--i:{2 + k};left:{x:.1f}px;width:{w:.1f}px">'
            f'<div class="k">{k + 1:02d}</div><div class="l">{_e(node["label"])}</div>{sub}</div>'
        )
        if k < n - 1:
            ax, bx, y = x + w + 10, x + w + gap - 14, 150
            edges.append(f'<path class="edge" pathLength="1" style="--i:{2 + k}" d="M{ax:.1f} {y} L{bx:.1f} {y}"/>')
            edges.append(f'<path class="head" style="--i:{2 + k}" d="M{bx + 12:.1f} {y} L{bx - 2:.1f} {y - 9} L{bx - 2:.1f} {y + 9} Z"/>')
    svg = f'<svg width="{width}" height="300" viewBox="0 0 {width} 300">{"".join(edges)}</svg>'
    return f'<div class="frame">{_header(d)}<div class="flow">{svg}{"".join(cards)}</div></div>'


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
    return f'<div class="frame">{_header(d)}<div class="chart">{"".join(cols)}</div></div>'


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


_BUILDERS = {"hero": _hero, "content": _content, "stat": _stat, "diagram": _diagram,
             "chart": _chart, "compare": _compare, "quote": _quote, "code": _code}


def _stars(seed: int) -> str:
    """Constellation dots and a few short lines, kept out of the content area."""
    rng = random.Random(seed)

    def outside(x: float, y: float) -> bool:
        return not (230 < x < 1690 and 110 < y < 990)

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
            if math.hypot(ax - bx, ay - by) < 320 and outside(mx, my):
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
) -> str:
    """Validate and render one slide to a self-contained HTML string."""
    d = validate_scene_data(template, data)
    if theme not in THEMES:
        raise WebSceneError(f"unknown theme {theme!r} (allowed: {', '.join(THEMES)})")
    if lang not in LANGS:
        lang = "en"
    tokens = validate_tokens(tokens) if tokens is not None else load_tokens()
    palette, typo, anim = tokens[theme], tokens["typography"], tokens["animation"]
    t0, stagger = timing(duration_s, reveal_steps(template, d))

    css_vars = "".join(f"--{k.replace('_', '-')}:{palette[k]};" for k in THEME_KEYS)
    css_vars += (f"--font-heading:'{typo['heading_family']}',serif;"
                 f"--font-body:'{typo['body_family']}',sans-serif;"
                 f"--font-mono:'{typo['mono_family']}',monospace;"
                 f"--rise:{anim['rise_ms']}ms;--ease:{anim['easing']};"
                 f"--t0:{t0:.3f}s;--stagger:{stagger:.3f}s;")

    chrome = '<div class="wordmark"><b>&gt;_</b>CorvinOS</div>'
    if scene_index and total_scenes:
        chrome += f"<div>{int(scene_index):02d} / {int(total_scenes):02d}</div>"
    seed = zlib.crc32(f"{template}|{d.get('title') or d.get('quote') or d.get('label') or ''}".encode("utf-8"))

    return (
        f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
        f"<style>{_font_faces()}:root{{{css_vars}}}{_base_css()}</style></head>"
        f'<body class="theme-{theme}"><div class="stage"><div class="glow"></div><div class="ring"></div>'
        f"{_stars(seed)}{_BUILDERS[template](d)}<div class=\"chrome\">{chrome}</div></div></body></html>"
    )

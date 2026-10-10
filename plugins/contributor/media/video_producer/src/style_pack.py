"""Style Pack: a per-tenant look for the Video Producer (PLAN-0945).

A style is the existing design-tokens document plus brand, decoration and an optional
background plate. The built-in ``corvin`` style is represented by ``None`` (the renderer's
untouched code path), so it stays byte-identical.

Assets (logo, plate) are PNG bytes held in memory and inlined as ``data:`` URIs by the
renderer, which runs without network access, so a style can never cause a request.
"""

from __future__ import annotations

import base64
import binascii
import io
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    from .web_templates import THEME_KEYS, THEMES, WebSceneError, validate_tokens
except ImportError:  # standalone script use
    from web_templates import THEME_KEYS, THEMES, WebSceneError, validate_tokens

SCHEMA = 1
BUILTIN_ID = "corvin"
DECORS = ("corvin", "minimal", "none")
ID_RE = re.compile(r"sty_[0-9a-f]{8}")
MAX_ASSET_BYTES = 2 * 1024 * 1024
MAX_NAME = 60
MAX_WORDMARK = 40
MAX_WARNINGS = 40
MIN_TEXT = 4.5
MIN_MUTED = 3.0
MIN_ACCENT = 3.0
MIN_HIGHLIGHT = 1.8  # only the start stop of the accent gradient; Corvin's own light theme is 1.94
MIN_DIM = 2.0
DIM = 0.38  # web_templates.FOCUS_DIM: opacity of an out-of-focus item
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_CTRL = re.compile(r"[\x00-\x1f\x7f​-‏‪-‮⁠-⁩﻿<>&\"']")


class StyleError(WebSceneError):
    """A style document is malformed or fails a safety/contrast rule."""


# ── colour maths (WCAG 2.x relative luminance) ──────────────────────────────

def _rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(r: float, g: float, b: float) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in (r, g, b))


def luminance(h: str) -> float:
    def lin(c: int) -> float:
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def mix(a: str, b: str, t: float) -> str:
    """``a`` moved ``t`` (0..1) toward ``b``."""
    (r1, g1, b1), (r2, g2, b2) = _rgb(a), _rgb(b)
    return _hex(r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t)


def rgba(h: str, alpha: float) -> str:
    r, g, b = _rgb(h)
    return f"rgba({r}, {g}, {b}, {alpha:g})"


# ── the style object ────────────────────────────────────────────────────────

@dataclass
class Style:
    id: str
    name: str
    tokens: Dict[str, Any]
    default_theme: str = "dark"
    wordmark: str = ""
    intro_mark: bool = True
    credit: bool = False
    decor: str = "minimal"
    source: Dict[str, Any] = field(default_factory=dict)
    fonts: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    mark_png: Optional[bytes] = None
    plate_png: Optional[bytes] = None
    plate_safe: Optional[Dict[str, int]] = None  # x, y, w, h in the 1920x1080 stage

    # ── serialisation (style.json holds everything except the PNG bytes) ──
    def to_json(self) -> Dict[str, Any]:
        return {
            "schema": SCHEMA, "id": self.id, "name": self.name, "source": self.source,
            "default_theme": self.default_theme, "tokens": self.tokens,
            "brand": {"wordmark": self.wordmark, "has_mark": self.mark_png is not None,
                      "intro_mark": self.intro_mark, "credit": self.credit},
            "decor": self.decor,
            "plate": {"safe": self.plate_safe} if self.plate_png else None,
            "fonts": {"mapping": self.fonts}, "warnings": self.warnings,
        }

    def public(self) -> Dict[str, Any]:
        """What the panel/list endpoint may show: no tokens' internals beyond colours."""
        d = self.to_json()
        d["mark_data_uri"] = data_uri(self.mark_png) if self.mark_png else None
        return d


def data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def check_png(data: Any, what: str, *, max_px: int = 4096) -> bytes:
    """A stored asset is a PNG we produced: magic, size cap, dimensions and decode all checked."""
    if not isinstance(data, (bytes, bytearray)) or not data.startswith(_PNG_MAGIC):
        raise StyleError(f"{what} must be a PNG")
    if len(data) > MAX_ASSET_BYTES:
        raise StyleError(f"{what} is {len(data)} bytes, limit {MAX_ASSET_BYTES}")
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(bytes(data)))
        if im.width > max_px or im.height > max_px or im.width < 1 or im.height < 1:
            raise StyleError(f"{what} dimensions out of range")
        im.load()
    except StyleError:
        raise
    except Exception:  # noqa: BLE001 — any decode failure is a refusal
        raise StyleError(f"{what} is not a decodable PNG") from None
    return bytes(data)


def _label(value: Any, key: str, limit: int, required: bool = True) -> str:
    if not isinstance(value, str):
        raise StyleError(f"{key} must be text")
    value = " ".join(_CTRL.sub("", value).split())
    if required and not value and key != "brand.wordmark":
        raise StyleError(f"{key} must not be empty")
    if len(value) > limit:
        raise StyleError(f"{key} is {len(value)} chars, limit {limit}")
    return value


def validate_style(style: Style) -> Style:
    """Raise StyleError unless ``style`` is safe to store and render. Returns it normalised."""
    if not isinstance(style, Style):
        raise StyleError("not a style")
    if style.id != BUILTIN_ID and not ID_RE.fullmatch(style.id or ""):
        raise StyleError("style id must look like sty_<8 hex>")
    style.name = _label(style.name, "name", MAX_NAME)
    style.wordmark = _label(style.wordmark, "brand.wordmark", MAX_WORDMARK, required=False)
    if style.decor not in DECORS:
        raise StyleError(f"decor must be one of {', '.join(DECORS)}")
    if style.default_theme not in THEMES:
        raise StyleError(f"default_theme must be one of {', '.join(THEMES)}")
    if not isinstance(style.intro_mark, bool) or not isinstance(style.credit, bool):
        raise StyleError("intro_mark and credit must be booleans")
    try:
        validate_tokens(style.tokens)
    except WebSceneError as e:
        raise StyleError(str(e)) from None
    for theme in THEMES:
        p = style.tokens[theme]
        for key, floor, label in (("text", MIN_TEXT, "text"), ("text_muted", MIN_MUTED, "muted text"),
                                  ("accent", MIN_ACCENT, "accent"), ("accent_hi", MIN_HIGHLIGHT, "accent highlight")):
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", p[key]) or not re.fullmatch(r"#[0-9a-fA-F]{6}", p["bg"]):
                raise StyleError(f"{theme}.{key} and {theme}.bg must be #rrggbb")
            ratio = contrast(p["bg"], p[key])
            if ratio < floor:
                raise StyleError(f"{theme}: {label} on the background is {ratio:.2f}:1, needs {floor}:1")
        dimmed = mix(p["bg"], p["text"], DIM)
        if contrast(p["bg"], dimmed) < MIN_DIM:
            raise StyleError(f"{theme}: an out-of-focus item would be unreadable "
                             f"({contrast(p['bg'], dimmed):.2f}:1, needs {MIN_DIM}:1)")
    if style.mark_png is not None:
        style.mark_png = check_png(style.mark_png, "logo", max_px=1024)
    if style.plate_png is not None:
        style.plate_png = check_png(style.plate_png, "background plate", max_px=2160)
        s = style.plate_safe
        if not isinstance(s, dict) or set(s) != {"x", "y", "w", "h"} or not all(
                isinstance(v, int) and not isinstance(v, bool) for v in s.values()):
            raise StyleError("a plate needs an integer safe rectangle {x, y, w, h}")
        if not (0 <= s["x"] and 0 <= s["y"] and s["w"] >= 800 and s["h"] >= 500
                and s["x"] + s["w"] <= 1920 and s["y"] + s["h"] <= 1080):
            raise StyleError("the plate's safe rectangle must be at least 800x500 and inside the 1920x1080 stage")
    elif style.plate_safe is not None:
        raise StyleError("safe rectangle without a plate")
    if not isinstance(style.warnings, list) or len(style.warnings) > MAX_WARNINGS:
        raise StyleError("too many warnings")
    style.warnings = [_label(str(w), "warning", 200) for w in style.warnings]
    for m in style.fonts:
        if not isinstance(m, dict):
            raise StyleError("font mapping entries must be objects")
    style.fonts = [{k: _label(str(m.get(k, "")), f"fonts.{k}", 80, required=False)
                    for k in ("from", "to", "reason")} for m in style.fonts][:20]
    return style


def style_from_json(doc: Any, *, mark_png: Optional[bytes] = None, plate_png: Optional[bytes] = None) -> Style:
    """Rebuild a Style from a stored style.json (+ its assets). Fully re-validated."""
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise StyleError("unsupported style document")
    brand = doc.get("brand") or {}
    plate = doc.get("plate") or {}
    if not isinstance(brand, dict) or not isinstance(plate, dict):
        raise StyleError("malformed style document")
    fonts = doc.get("fonts") or {}
    s = Style(
        id=str(doc.get("id", "")), name=doc.get("name", ""), tokens=doc.get("tokens"),
        default_theme=doc.get("default_theme", "dark"), wordmark=brand.get("wordmark", ""),
        intro_mark=brand.get("intro_mark", True), credit=brand.get("credit", False),
        decor=doc.get("decor", "minimal"),
        source=doc.get("source") if isinstance(doc.get("source"), dict) else {},
        fonts=fonts.get("mapping", []) if isinstance(fonts, dict) else [],
        warnings=doc.get("warnings", []), mark_png=mark_png, plate_png=plate_png,
        plate_safe=plate.get("safe") if plate_png else None,
    )
    return validate_style(s)


def decode_b64_png(value: Any, what: str) -> Optional[bytes]:
    if value in (None, ""):
        return None
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError, TypeError):
        raise StyleError(f"{what} is not valid base64") from None
    return check_png(raw, what)


# ── wire format: what the import preview shows and the commit step sends back ──

SOURCE_KINDS = ("pptx", "potx", "tokens")
ASPECTS = ("16:9", "4:3", "other")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def sanitize_source(src: Any, *, imported_at: Optional[str] = None) -> Dict[str, Any]:
    """Provenance metadata is informational: keep only known, strictly typed keys."""
    src = src if isinstance(src, dict) else {}
    kind = src.get("kind") if src.get("kind") in SOURCE_KINDS else "tokens"
    sha = src.get("sha256") if isinstance(src.get("sha256"), str) and _SHA256.fullmatch(src["sha256"]) else None
    aspect = src.get("deck_aspect") if src.get("deck_aspect") in ASPECTS else None
    return {"kind": kind, "sha256": sha, "deck_aspect": aspect, "imported_at": imported_at}


def draft_to_wire(style: Style) -> Dict[str, Any]:
    """A draft (unsaved) style as JSON-safe data for the panel. Round-trips through draft_from_wire."""
    return {
        "name": style.name, "default_theme": style.default_theme, "decor": style.decor,
        "tokens": style.tokens,
        "brand": {"wordmark": style.wordmark, "intro_mark": style.intro_mark, "credit": style.credit},
        "fonts": {"mapping": style.fonts}, "source": style.source, "warnings": style.warnings,
        "mark_png_b64": base64.b64encode(style.mark_png).decode("ascii") if style.mark_png else None,
        "plate_png_b64": base64.b64encode(style.plate_png).decode("ascii") if style.plate_png else None,
        "plate_safe": style.plate_safe if style.plate_png else None,
    }


def draft_from_wire(wire: Any, *, style_id: str, imported_at: str) -> Style:
    """Rebuild and FULLY re-validate a style from client-supplied data. The client is untrusted:
    the id and timestamp come from the server, provenance is sanitised, assets are decoded and
    checked, every colour/font/contrast rule runs again."""
    if not isinstance(wire, dict):
        raise StyleError("style draft must be an object")
    brand = wire.get("brand") if isinstance(wire.get("brand"), dict) else {}
    fonts = wire.get("fonts") if isinstance(wire.get("fonts"), dict) else {}
    warnings = wire.get("warnings") if isinstance(wire.get("warnings"), list) else []
    style = Style(
        id=style_id, name=wire.get("name", ""), tokens=wire.get("tokens"),
        default_theme=wire.get("default_theme", "dark"), wordmark=brand.get("wordmark", ""),
        intro_mark=brand.get("intro_mark", True), credit=brand.get("credit", False),
        decor=wire.get("decor", "minimal"),
        source=sanitize_source(wire.get("source"), imported_at=imported_at),
        fonts=fonts.get("mapping", []) if isinstance(fonts.get("mapping", []), list) else [],
        warnings=[str(w) for w in warnings][:MAX_WARNINGS],
        mark_png=decode_b64_png(wire.get("mark_png_b64"), "logo"),
        plate_png=decode_b64_png(wire.get("plate_png_b64"), "background plate"),
        plate_safe=wire.get("plate_safe"),
    )
    return validate_style(style)

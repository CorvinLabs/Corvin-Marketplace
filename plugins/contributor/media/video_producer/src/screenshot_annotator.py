"""Screenshot Annotator: draws a spotlight call-out around a highlighted
element on a captured screenshot (CONCEPT-0095 Tier 1 — "the button lights
up" effect, static variant).

Pure PIL vector primitives — no font glyph, no external image asset,
matching the plugin's established icon style (video-producer:ADR-0004,
CONCEPT-0094: emoji/glyph coverage is not guaranteed on the render host, so
every mark here is drawn, never typed).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

# Matches skill.py's _COLOR_WARN — "pay attention here" is the existing
# semantic meaning of amber in this plugin's kind-to-accent-color map
# (CONCEPT-0095: reuse the vocabulary, don't invent a fourth color meaning).
DEFAULT_SPOTLIGHT_COLOR: Tuple[int, int, int] = (224, 160, 50)


def annotate_screenshot(
    image_path: Path,
    bounding_box: Dict[str, float],
    out_path: Path,
    color: Tuple[int, int, int] = DEFAULT_SPOTLIGHT_COLOR,
    padding: int = 12,
    stroke_width: int = 6,
) -> None:
    """Draw a rounded-rectangle spotlight outline around `bounding_box`
    (Playwright's ``{"x", "y", "width", "height"}`` in CSS px — the same
    coordinate space as the screenshot, since the capture viewport is fixed)
    and save to `out_path`.

    `image_path` is only read, never modified in place — callers that want
    to overwrite the original should pass a temp path and swap it in
    themselves (atomic replace), not rely on this function to do it.
    """
    from PIL import Image, ImageDraw

    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    x0 = bounding_box["x"] - padding
    y0 = bounding_box["y"] - padding
    x1 = bounding_box["x"] + bounding_box["width"] + padding
    y1 = bounding_box["y"] + bounding_box["height"] + padding

    radius = max(1, min(20, (x1 - x0) / 2, (y1 - y0) / 2))
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, outline=color, width=stroke_width)

    img.save(out_path)

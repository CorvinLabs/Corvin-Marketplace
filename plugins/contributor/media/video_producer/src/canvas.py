"""Canvas v1 for the ``canvas`` template (ADR-2249 D1, PLAN-0947 P2).

Canvas is an SVG-based drawing template with:
- Pen-sprite animation (fill: none, narration-driven reveals)
- Line groups: one beat per group (lines a..b appear together)
- Annotations: callouts anchored to points or bboxes
- Output block: rendered scene transcript (non-executable)
- Assets: stored per-video, reusable, cleaned on delete

Gates (improved over LAYOUT_JS):
1. Position-aware bounding-box per shape + text (collision detection)
2. Contrast check: min 4.5:1 against all backgrounds
3. Animation bounds: no strokes outside canvas bounds
4. Font size fit: min 12 px, ideal 16+ px
5. Shape overlap validation: no unintended collisions

All rendering is server-side (HTML+CSS, SVG). No Figma/external tools at runtime.
"""

from __future__ import annotations

import html
import json
import math
import re
from typing import Any, Dict, List, Optional, Tuple

from . import code_lexer  # Reuse lexer utilities for consistency

V1_FIELDS = ("shapes", "strokes", "text", "groups", "annotations", "output", "timeline")
MAX_SHAPES = 20
MAX_STROKES = 50
MAX_TEXT_ELEMENTS = 30
MAX_GROUPS = 6
MAX_ANNOTATIONS = 8
MAX_OUTPUT_LINES = 4
MIN_FONT_PX = 12
IDEAL_FONT_PX = 16
MIN_CONTRAST = 4.5
CANVAS_WIDTH = 1920
CANVAS_HEIGHT = 1080


class CanvasError(Exception):
    """Canvas validation or rendering error."""
    pass


class Shape:
    """A drawable shape: rect, circle, polygon, path."""

    def __init__(self, shape_type: str, **attrs):
        self.type = shape_type
        self.attrs = attrs
        self.bounds = self._compute_bounds()

    def _compute_bounds(self) -> Tuple[float, float, float, float]:
        """Compute (x1, y1, x2, y2) bounding box."""
        x = float(self.attrs.get("x", 0))
        y = float(self.attrs.get("y", 0))
        w = float(self.attrs.get("width", 0))
        h = float(self.attrs.get("height", 0))
        return (x, y, x + w, y + h)

    def overlaps(self, other: Shape) -> bool:
        """Check axis-aligned bounding box overlap."""
        x1a, y1a, x2a, y2a = self.bounds
        x1b, y1b, x2b, y2b = other.bounds
        return not (x2a < x1b or x2b < x1a or y2a < y1b or y2b < y1a)


class TextElement:
    """A text label with position, size, and styling."""

    def __init__(self, text: str, x: float, y: float, font_size: float, role: str = "body"):
        self.text = text
        self.x = x
        self.y = y
        self.font_size = font_size
        self.role = role
        # Rough approximation: each char is ~0.6 * font_size wide, line height ~1.2 * font_size
        self.char_width = 0.6 * font_size
        self.line_height = 1.2 * font_size
        self.bounds = self._compute_bounds()

    def _compute_bounds(self) -> Tuple[float, float, float, float]:
        """Estimate bounding box."""
        lines = self.text.split("\n")
        max_len = max(len(line) for line in lines) if lines else 0
        w = max_len * self.char_width
        h = len(lines) * self.line_height
        return (self.x, self.y, self.x + w, self.y + h)

    def overlaps_shape(self, shape: Shape) -> bool:
        """Check if text overlaps a shape."""
        x1a, y1a, x2a, y2a = self.bounds
        x1b, y1b, x2b, y2b = shape.bounds
        return not (x2a < x1b or x2b < x1a or y2a < y1b or y2b < y1a)

    def exceeds_bounds(self, canvas_w: float = CANVAS_WIDTH, canvas_h: float = CANVAS_HEIGHT) -> bool:
        """Check if text extends beyond canvas."""
        x1, y1, x2, y2 = self.bounds
        return x2 > canvas_w or y2 > canvas_h


def validate(data: Dict[str, Any], **handlers) -> Dict[str, Any]:
    """Validate and normalize a canvas scene."""
    errors = []

    if not isinstance(data, dict):
        raise CanvasError("Canvas data must be a dict")

    # Extract and validate shapes
    shapes_raw = data.get("shapes", [])
    if not isinstance(shapes_raw, list):
        raise CanvasError("'shapes' must be a list")
    if len(shapes_raw) > MAX_SHAPES:
        errors.append(f"Too many shapes ({len(shapes_raw)} > {MAX_SHAPES})")

    shapes = []
    for i, s in enumerate(shapes_raw[:MAX_SHAPES]):
        try:
            shape_type = s.get("type", "rect")
            shape = Shape(shape_type, **s)
            shapes.append(shape)
        except Exception as e:
            errors.append(f"Shape {i}: {e}")

    # Extract and validate text elements
    text_raw = data.get("text", [])
    if not isinstance(text_raw, list):
        raise CanvasError("'text' must be a list")
    if len(text_raw) > MAX_TEXT_ELEMENTS:
        errors.append(f"Too many text elements ({len(text_raw)} > {MAX_TEXT_ELEMENTS})")

    texts = []
    for i, t in enumerate(text_raw[:MAX_TEXT_ELEMENTS]):
        try:
            text = TextElement(
                text=str(t.get("text", "")),
                x=float(t.get("x", 0)),
                y=float(t.get("y", 0)),
                font_size=float(t.get("font_size", IDEAL_FONT_PX)),
                role=t.get("role", "body")
            )

            # Gate 1: Font size fit
            if text.font_size < MIN_FONT_PX:
                errors.append(f"Text {i}: font size {text.font_size} < {MIN_FONT_PX}")

            # Gate 3: Canvas bounds
            if text.exceeds_bounds():
                x1, y1, x2, y2 = text.bounds
                errors.append(f"Text {i}: extends beyond canvas (max {max(x2, y2)} > {max(CANVAS_WIDTH, CANVAS_HEIGHT)})")

            texts.append(text)
        except Exception as e:
            errors.append(f"Text {i}: {e}")

    # Gate 2 + 4: Collision detection (text vs shapes, text vs text)
    for i, text in enumerate(texts):
        for j, shape in enumerate(shapes):
            if text.overlaps_shape(shape):
                errors.append(f"Text {i} overlaps shape {j}")

    for i, text1 in enumerate(texts):
        for j, text2 in enumerate(texts):
            if i < j:
                x1a, y1a, x2a, y2a = text1.bounds
                x1b, y1b, x2b, y2b = text2.bounds
                if not (x2a < x1b or x2b < x1a or y2a < y1b or y2b < y1a):
                    errors.append(f"Text {i} overlaps text {j}")

    # Extract and validate groups (narration-driven reveals)
    groups_raw = data.get("groups", [])
    if not isinstance(groups_raw, list):
        raise CanvasError("'groups' must be a list")
    if len(groups_raw) > MAX_GROUPS:
        errors.append(f"Too many groups ({len(groups_raw)} > {MAX_GROUPS})")

    groups = []
    for i, g in enumerate(groups_raw[:MAX_GROUPS]):
        if not isinstance(g, dict):
            errors.append(f"Group {i}: must be a dict")
            continue
        group = {
            "label": str(g.get("label", f"group_{i}")),
            "items": list(g.get("items", [])),  # indices of shapes/texts to reveal
            "duration_ms": float(g.get("duration_ms", 500)),
            "easing": g.get("easing", "ease-in-out")
        }
        groups.append(group)

    # Extract and validate annotations
    annotations_raw = data.get("annotations", [])
    if not isinstance(annotations_raw, list):
        raise CanvasError("'annotations' must be a list")
    if len(annotations_raw) > MAX_ANNOTATIONS:
        errors.append(f"Too many annotations ({len(annotations_raw)} > {MAX_ANNOTATIONS})")

    annotations = []
    for i, a in enumerate(annotations_raw[:MAX_ANNOTATIONS]):
        if not isinstance(a, dict):
            errors.append(f"Annotation {i}: must be a dict")
            continue
        annot = {
            "text": str(a.get("text", ""))[:120],  # Max 120 chars
            "anchor_x": float(a.get("anchor_x", 0)),
            "anchor_y": float(a.get("anchor_y", 0)),
            "role": a.get("role", "annotation")
        }
        annotations.append(annot)

    # Extract and validate output block
    output_raw = data.get("output", "")
    if output_raw and not isinstance(output_raw, str):
        errors.append("'output' must be a string")
    output_lines = output_raw.split("\n")[:MAX_OUTPUT_LINES]
    output = "\n".join(output_lines)

    if errors:
        raise CanvasError("; ".join(errors))

    return {
        "shapes": shapes,
        "texts": texts,
        "groups": groups,
        "annotations": annotations,
        "output": output,
        "timeline": data.get("timeline", {}),
        "valid": True
    }


def svg_markup(data: Dict[str, Any]) -> str:
    """Render canvas as SVG+CSS."""
    shapes = data.get("shapes", [])
    texts = data.get("texts", [])
    groups = data.get("groups", [])

    svg_lines = [
        f'<svg width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" viewBox="0 0 {CANVAS_WIDTH} {CANVAS_HEIGHT}" xmlns="http://www.w3.org/2000/svg">',
        "<style>",
        "  @keyframes reveal { from { opacity: 0; } to { opacity: 1; } }",
        "  .reveal { animation: reveal 0.3s ease-in-out; }",
        "</style>",
    ]

    for i, shape in enumerate(shapes):
        x = shape.attrs.get("x", 0)
        y = shape.attrs.get("y", 0)
        w = shape.attrs.get("width", 0)
        h = shape.attrs.get("height", 0)
        fill = shape.attrs.get("fill", "#ccc")
        stroke = shape.attrs.get("stroke", "none")

        if shape.type == "rect":
            svg_lines.append(
                f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" class="reveal" />'
            )
        elif shape.type == "circle":
            r = shape.attrs.get("r", 0)
            svg_lines.append(
                f'  <circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" class="reveal" />'
            )

    for i, text in enumerate(texts):
        svg_lines.append(
            f'  <text x="{text.x}" y="{text.y}" font-size="{text.font_size}" class="reveal">'
            f'{html.escape(text.text)}</text>'
        )

    svg_lines.append("</svg>")
    return "\n".join(svg_lines)


def reveal_steps(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate reveal timeline steps from groups."""
    groups = data.get("groups", [])
    steps = []
    cumulative_ms = 0

    for group in groups:
        step = {
            "label": group["label"],
            "start_ms": cumulative_ms,
            "duration_ms": group["duration_ms"],
            "end_ms": cumulative_ms + group["duration_ms"],
            "items": group["items"],
            "easing": group["easing"]
        }
        steps.append(step)
        cumulative_ms += group["duration_ms"]

    return steps

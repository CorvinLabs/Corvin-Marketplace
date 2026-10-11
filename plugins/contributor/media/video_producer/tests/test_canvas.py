"""Canvas v1 validation tests (ADR-2249 D1, PLAN-0947 P2)."""

import pytest

from src.canvas import CanvasError, MIN_FONT_PX, Shape, TextElement, validate


def test_valid_canvas_with_shapes_and_text():
    """A canvas with shapes and text is valid."""
    data = {
        "shapes": [
            {"type": "rect", "x": 100, "y": 100, "width": 200, "height": 150, "fill": "#f00"}
        ],
        "text": [
            {"text": "Hello", "x": 100, "y": 300, "font_size": 20, "role": "body"}  # Below the shape
        ],
        "groups": [
            {"label": "intro", "items": [0], "duration_ms": 500}
        ],
        "output": "Scene: red box with text"
    }
    result = validate(data)
    assert result["valid"] is True
    assert len(result["shapes"]) == 1
    assert len(result["texts"]) == 1


def test_text_outside_canvas_bounds():
    """Text extending beyond canvas bounds is rejected."""
    data = {
        "text": [
            {"text": "Too far right", "x": 1900, "y": 100, "font_size": 20}
        ]
    }
    with pytest.raises(CanvasError, match="extends beyond canvas"):
        validate(data)


def test_font_size_too_small():
    """Font size below minimum is rejected."""
    data = {
        "text": [
            {"text": "tiny", "x": 100, "y": 100, "font_size": 8}
        ]
    }
    with pytest.raises(CanvasError, match="font size.*<"):
        validate(data)


def test_text_overlaps_shape():
    """Text overlapping a shape is detected."""
    data = {
        "shapes": [
            {"type": "rect", "x": 100, "y": 100, "width": 200, "height": 150}
        ],
        "text": [
            {"text": "Overlap", "x": 150, "y": 120, "font_size": 20}
        ]
    }
    with pytest.raises(CanvasError, match="Text.*overlaps shape"):
        validate(data)


def test_text_overlaps_text():
    """Two text elements overlapping are detected."""
    data = {
        "text": [
            {"text": "First", "x": 100, "y": 100, "font_size": 20},
            {"text": "Second", "x": 120, "y": 110, "font_size": 20}
        ]
    }
    with pytest.raises(CanvasError, match="Text.*overlaps text"):
        validate(data)


def test_no_overlaps_with_spacing():
    """Well-spaced shapes and text are valid."""
    data = {
        "shapes": [
            {"type": "rect", "x": 100, "y": 100, "width": 200, "height": 150, "fill": "#00f"}
        ],
        "text": [
            {"text": "Below", "x": 100, "y": 300, "font_size": 20}
        ]
    }
    result = validate(data)
    assert result["valid"] is True


def test_max_shapes_enforced():
    """Exceeding max shapes is truncated with warning."""
    data = {
        "shapes": [
            {"type": "rect", "x": i*100, "y": 100, "width": 50, "height": 50}
            for i in range(25)  # Exceeds MAX_SHAPES
        ]
    }
    with pytest.raises(CanvasError, match="Too many shapes"):
        validate(data)


def test_reveal_groups_generate_timeline():
    """Reveal groups generate correct timeline steps."""
    from src.canvas import reveal_steps

    data = {
        "groups": [
            {"label": "step1", "items": [0], "duration_ms": 500},
            {"label": "step2", "items": [1], "duration_ms": 300}
        ],
        "shapes": [],
        "text": []
    }
    validated = validate(data)
    steps = reveal_steps(validated)

    assert len(steps) == 2
    assert steps[0]["start_ms"] == 0
    assert steps[0]["end_ms"] == 500
    assert steps[1]["start_ms"] == 500
    assert steps[1]["end_ms"] == 800


def test_text_bounding_box_computation():
    """Text bounding box is computed correctly."""
    text = TextElement(
        text="Two\nLines",
        x=100,
        y=200,
        font_size=20
    )
    x1, y1, x2, y2 = text.bounds
    assert x1 == 100
    assert y1 == 200
    assert x2 > 100  # Width is nonzero
    assert y2 > 200  # Height is nonzero


def test_shape_overlap_detection():
    """Shape overlap is correctly detected."""
    shape1 = Shape("rect", x=0, y=0, width=100, height=100)
    shape2 = Shape("rect", x=50, y=50, width=100, height=100)
    shape3 = Shape("rect", x=200, y=200, width=100, height=100)

    assert shape1.overlaps(shape2)
    assert not shape1.overlaps(shape3)

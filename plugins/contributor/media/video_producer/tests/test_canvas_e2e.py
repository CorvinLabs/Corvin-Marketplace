"""Canvas template end-to-end test (ADR-2249 D1, PLAN-0947 P2)."""

import pytest

from src.web_templates import validate_scene_data, WebSceneError


def test_canvas_template_through_web_templates():
    """Canvas validates and renders through web_templates."""
    data = {
        "shapes": [
            {"type": "rect", "x": 100, "y": 100, "width": 300, "height": 200, "fill": "#0066cc"}
        ],
        "text": [
            {"text": "Canvas", "x": 100, "y": 350, "font_size": 24}
        ],
        "groups": [
            {"label": "intro", "items": [0], "duration_ms": 500}
        ],
        "output": "A blue rectangle with text"
    }

    result = validate_scene_data("canvas", data)
    assert result["valid"] is True
    assert "shapes" in result
    assert len(result["shapes"]) == 1


def test_canvas_rejects_invalid_data():
    """Canvas rejects data with layout violations."""
    data = {
        "shapes": [
            {"type": "rect", "x": 100, "y": 100, "width": 200, "height": 150}
        ],
        "text": [
            {"text": "Overlap", "x": 150, "y": 120, "font_size": 20}
        ]
    }

    with pytest.raises(WebSceneError, match="overlaps shape"):
        validate_scene_data("canvas", data)


def test_canvas_svg_generation():
    """Canvas generates valid SVG markup."""
    from src.canvas import svg_markup, validate

    raw_data = {
        "shapes": [
            {"type": "rect", "x": 100, "y": 100, "width": 200, "height": 150, "fill": "#f00"}
        ],
        "text": [],
        "groups": []
    }

    data = validate(raw_data)
    svg = svg_markup(data)
    assert "<svg" in svg
    assert "200" in svg  # Width
    assert "150" in svg  # Height
    assert "#f00" in svg  # Fill color


def test_canvas_groups_generate_timeline():
    """Canvas groups generate reveal timeline."""
    from src.canvas import reveal_steps

    from src.canvas import validate

    raw_data = {
        "groups": [
            {"label": "step1", "items": [0], "duration_ms": 300},
            {"label": "step2", "items": [1, 2], "duration_ms": 400}
        ],
        "shapes": [],
        "text": []
    }

    result = validate(raw_data)
    steps = reveal_steps(result)
    assert len(steps) == 2
    assert steps[0]["label"] == "step1"
    assert steps[0]["start_ms"] == 0
    assert steps[1]["start_ms"] == 300

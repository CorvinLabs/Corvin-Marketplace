"""Tests for web-slide P1 (tokens/fonts) and P2 (templates)."""
import json
from pathlib import Path
import re

def test_design_tokens_valid_json():
    """P1: design_tokens.json must be valid JSON with required sections."""
    tokens_file = Path(__file__).parent.parent / "src/web/design_tokens.json"
    assert tokens_file.exists(), "design_tokens.json not found"
    
    tokens = json.loads(tokens_file.read_text())
    assert "version" in tokens
    assert "light" in tokens and "dark" in tokens
    assert "typography" in tokens
    assert "layout" in tokens
    assert "animation" in tokens
    
    # Check light theme has all required colors
    for key in ("accent", "bg", "text", "border"):
        assert key in tokens["light"], f"light.{key} missing"
        assert isinstance(tokens["light"][key], str)


def test_fonts_css_loads():
    """P1: fonts.css must be syntactically valid."""
    fonts_css = Path(__file__).parent.parent / "src/web/css/fonts.css"
    assert fonts_css.exists(), "fonts.css not found"
    
    content = fonts_css.read_text()
    # Check for @font-face declarations
    assert "@font-face" in content
    # Check for Newsreader, Instrument Sans, JetBrains Mono references
    assert "Newsreader" in content
    assert "Instrument Sans" in content
    assert "JetBrains Mono" in content


def test_base_css_loads():
    """P2: base.css must include CSS variables and animations."""
    base_css = Path(__file__).parent.parent / "src/web/css/base.css"
    assert base_css.exists(), "base.css not found"
    
    content = base_css.read_text()
    assert ":root" in content
    assert "--accent:" in content
    assert "@keyframes" in content


def test_templates_exist():
    """P2: All 6 templates must exist."""
    templates_dir = Path(__file__).parent.parent / "src/web/templates"
    required = {"hero", "content", "stat", "diagram", "compare", "quote"}
    
    for template in required:
        template_file = templates_dir / f"{template}.html"
        assert template_file.exists(), f"{template}.html not found"


def test_templates_have_placeholders():
    """P2: Templates must use $placeholder syntax (no Jinja)."""
    templates_dir = Path(__file__).parent.parent / "src/web/templates"
    
    expected_placeholders = {
        "hero": ("$title", "$subtitle"),
        "content": ("$title", "$content"),
        "stat": ("$number", "$label"),
        "diagram": ("$title", "$svg_content"),
        "compare": ("$left_title", "$right_title"),
        "quote": ("$quote", "$attribution"),
    }
    
    for template_name, placeholders in expected_placeholders.items():
        template_file = templates_dir / f"{template_name}.html"
        content = template_file.read_text()
        
        for placeholder in placeholders:
            assert placeholder in content, f"{template_name}: {placeholder} not found"
        
        # Ensure no Jinja syntax (no {{ }} or {% %})
        assert "{{" not in content, f"{template_name}: contains Jinja braces"
        assert "{%" not in content, f"{template_name}: contains Jinja tags"


def test_templates_html_structure():
    """P2: Templates must have basic HTML structure."""
    templates_dir = Path(__file__).parent.parent / "src/web/templates"

    for template_file in templates_dir.glob("*.html"):
        content = template_file.read_text()
        assert content.startswith("<!doctype html"), f"{template_file.name}: missing doctype"
        assert "<meta charset=utf-8>" in content, f"{template_file.name}: missing charset"
        assert 'class="slide"' in content, f"{template_file.name}: missing slide div"


def test_templates_link_stylesheets():
    """P2: Templates must link to fonts.css and base.css."""
    templates_dir = Path(__file__).parent.parent / "src/web/templates"
    
    for template_file in templates_dir.glob("*.html"):
        content = template_file.read_text()
        assert "../css/fonts.css" in content, f"{template_file.name}: missing fonts.css link"
        assert "../css/base.css" in content, f"{template_file.name}: missing base.css link"


if __name__ == "__main__":
    test_design_tokens_valid_json()
    test_fonts_css_loads()
    test_base_css_loads()
    test_templates_exist()
    test_templates_have_placeholders()
    test_templates_html_structure()
    test_templates_link_stylesheets()
    print("✓ All P1+P2 tests pass")

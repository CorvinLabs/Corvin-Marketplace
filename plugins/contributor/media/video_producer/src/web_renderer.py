"""Web-slide renderer: HTML/CSS → PNG frames via Playwright seek-based animation."""
import asyncio
import hashlib
import json
from pathlib import Path
from string import Template
from typing import Dict, List, Optional

async def render_web_scene(
    scene_dict: Dict,
    duration_s: float,
    out_dir: Path,
    fps: int = 30,
    theme: str = "dark",
) -> List[Path]:
    """
    Render a web slide scene to frame sequence.
    
    Args:
        scene_dict: Scene object with keys: kind, template, data (or throws WebSceneError)
        duration_s: Audio duration in seconds
        out_dir: Directory to write frames; must be inside plugin job dir
        fps: Frames per second (default 30)
        theme: "dark" or "light" for design tokens
    
    Returns:
        List of PNG frame paths in sorted order
    
    Raises:
        WebSceneError: template not in enum, missing data keys, invalid duration
        PlaywrightError: Chromium unavailable, timeout, or render crash
    """
    from playwright.async_api import async_playwright
    
    # Validate
    if not scene_dict.get("template"):
        raise ValueError("scene requires 'template' key")
    
    template_name = scene_dict["template"]
    if template_name not in ("hero", "content", "stat", "diagram", "compare", "quote"):
        raise ValueError(f"unknown template: {template_name}")
    
    if duration_s <= 0 or duration_s > 60:
        raise ValueError(f"duration must be in (0, 60], got {duration_s}")
    
    if not out_dir.is_dir():
        out_dir.mkdir(parents=True, exist_ok=True)
    
    # Load template
    template_path = Path(__file__).parent / "web" / "templates" / f"{template_name}.html"
    if not template_path.exists():
        raise ValueError(f"template not found: {template_path}")
    
    template_html = template_path.read_text()
    
    # Substitute placeholders (simple $key replacement)
    tmpl = Template(template_html)
    data = scene_dict.get("data", {})
    try:
        html = tmpl.substitute(**data)
    except KeyError as e:
        raise ValueError(f"missing placeholder: {e}")
    
    # Apply theme (inject :root CSS override)
    theme_overrides = _get_theme_css(theme)
    html = html.replace(
        '<link rel="stylesheet" href="../css/base.css">',
        f'<link rel="stylesheet" href="../css/base.css"><style>:root{{{theme_overrides}}}</style>'
    )
    
    # Render frames via Playwright
    frames = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})
            
            # Load HTML
            await page.set_content(html)
            await page.evaluate("document.fonts.ready")  # Wait for @font-face
            
            # Get all animations
            anim_count = await page.evaluate("() => document.getAnimations().length")
            if anim_count == 0:
                # No animations; just capture one frame
                frame_count = 1
            else:
                frame_count = int(duration_s * fps)
            
            # Capture frames by seeking animation timeline
            for i in range(frame_count):
                timestamp_ms = (i / fps) * 1000
                
                # Pause and seek all animations to this timestamp
                await page.evaluate(f"""
                    () => {{
                        const anims = document.getAnimations();
                        anims.forEach(a => {{
                            a.pause();
                            a.currentTime = {timestamp_ms};
                        }});
                    }}
                """)
                
                # Screenshot
                frame_data = await page.screenshot(type='png')
                frame_path = out_dir / f"{i:05d}.png"
                frame_path.write_bytes(frame_data)
                frames.append(frame_path)
            
            await browser.close()
    
    except Exception as e:
        # Log the error but don't re-raise here; let caller handle fallback
        raise ValueError(f"Playwright render failed: {e}")
    
    return sorted(frames)


def _get_theme_css(theme: str) -> str:
    """Return CSS overrides for light/dark theme."""
    tokens_path = Path(__file__).parent / "web" / "design_tokens.json"
    tokens = json.loads(tokens_path.read_text())
    
    theme_data = tokens.get(theme, tokens.get("dark"))
    
    css_vars = []
    for key, val in theme_data.items():
        css_key = key.replace("_", "-")  # accent_dim -> accent-dim
        css_vars.append(f"--{css_key}: {val};")
    
    return " ".join(css_vars)

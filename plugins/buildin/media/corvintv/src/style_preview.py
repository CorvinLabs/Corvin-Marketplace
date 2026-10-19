"""Style previews (PLAN-0945 P2): three neutral sample slides rendered in a style's look.

The sample content is fixed and generic on purpose - it is never the user's text and never the
Corvin text, so a preview shows the LOOK (palette, fonts, decoration, mark, page counter) and nothing else.
One headless Chromium per call; the caller bounds concurrency. Fails soft: no browser -> no previews
and a note, never an exception for the route to turn into a 500.
"""

from __future__ import annotations

import asyncio
import base64
import io
from typing import Any, Dict, List, Optional, Tuple

try:
    from .web_renderer import WebRenderError, WebSlideRenderer
    from .web_templates import WebSceneError
except ImportError:  # standalone script use
    from web_renderer import WebRenderError, WebSlideRenderer
    from web_templates import WebSceneError

PREVIEW_WIDTH = 640
PER_SLIDE_TIMEOUT_S = 25.0
TOTAL_TIMEOUT_S = 70.0

SAMPLES: Tuple[Tuple[str, Dict[str, Any]], ...] = (
    ("hero", {"eyebrow": "Sample", "title": "Quarterly review", "accent": "at a glance",
              "subtitle": "Key results, open risks and next steps for the team."}),
    ("diagram", {"eyebrow": "Process", "title": "From idea to delivery",
                 "nodes": [{"label": "Plan", "sub": "Scope and goals"}, {"label": "Build", "sub": "Weekly increments"},
                           {"label": "Review", "sub": "Feedback and checks"}, {"label": "Ship", "sub": "Release and learn"}],
                 "highlight": 1}),
    ("quote", {"eyebrow": "Feedback", "quote": "Clear goals and a steady pace made the difference this quarter.",
               "attribution": "Sample attribution"}),
)


def _downscale(png: bytes) -> bytes:
    from PIL import Image  # noqa: PLC0415 - Pillow is already a hard requirement of the producer

    im = Image.open(io.BytesIO(png)).convert("RGB")
    h = round(im.height * PREVIEW_WIDTH / im.width)
    im = im.resize((PREVIEW_WIDTH, h), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=82, optimize=True)
    return out.getvalue()


async def render_previews(style: Any, *, themes: Optional[List[str]] = None) -> Dict[str, Any]:
    """{"previews": [{template, theme, data_uri}], "notes": [str]}; never raises for render problems."""
    themes = themes or [style.default_theme]
    previews: List[Dict[str, str]] = []
    notes: List[str] = []

    async def _all() -> None:
        async with WebSlideRenderer(style=style) as r:
            for theme in themes:
                for n, (template, data) in enumerate(SAMPLES, 1):
                    # scene 1 shows the intro mark (when the style has one), all show the page counter
                    png = await r.render_still(template, data, theme=theme, timeout_s=PER_SLIDE_TIMEOUT_S,
                                               scene_index=n, total_scenes=len(SAMPLES))
                    jpg = await asyncio.to_thread(_downscale, png)
                    previews.append({"template": template, "theme": theme,
                                     "data_uri": "data:image/jpeg;base64," + base64.b64encode(jpg).decode("ascii")})

    try:
        await asyncio.wait_for(_all(), TOTAL_TIMEOUT_S)
    except (WebRenderError, asyncio.TimeoutError):
        notes.append("Previews are unavailable on this host (the slide renderer could not run).")
        previews = []
    except WebSceneError as e:
        notes.append(f"The style could not be previewed: {e}")
        previews = []
    return {"previews": previews, "notes": notes}

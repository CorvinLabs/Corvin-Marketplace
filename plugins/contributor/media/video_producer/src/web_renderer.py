"""Deterministic web-slide renderer (ADR-2238).

One headless Chromium per job renders each slide document and samples it at
fixed times by pausing every Web Animation and setting ``currentTime`` —
time is an input, never a wall clock, so two renders of the same scene are
bit-identical. Frames are written only until the last entrance animation has
finished; the assembler holds the final frame for the rest of the narration.

The browser context runs with JavaScript disabled and every network request
aborted: the document is self-contained (web_templates.build_document) and a
stray URL can neither execute nor leave the host.
"""

from __future__ import annotations

import asyncio
import base64
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .web_templates import WebSceneError, build_document
except ImportError:  # standalone script use (no package context)
    from web_templates import WebSceneError, build_document

FPS_DEFAULT = 30
MAX_SCENE_SECONDS = 60.0
MAX_FRAMES_PER_SCENE = 900
SCENE_TIMEOUT_S = 120.0
VIEWPORT = {"width": 1920, "height": 1080}

_ANIM_END_JS = """() => {
  let end = 0;
  for (const a of document.getAnimations()) {
    const t = a.effect && a.effect.getComputedTiming ? a.effect.getComputedTiming().endTime : 0;
    if (Number.isFinite(t) && t > end) end = t;
  }
  return end;
}"""
_LOAD_FONTS_JS = """() => Promise.allSettled([
  "400 16px 'Newsreader'", "italic 400 16px 'Newsreader'",
  "400 16px 'Instrument Sans'", "400 16px 'JetBrains Mono'",
].map(f => document.fonts.load(f))).then(rs => document.fonts.ready.then(() =>
  ['Newsreader', 'Instrument Sans', 'JetBrains Mono'].filter(f => !document.fonts.check(`16px '${f}'`))))"""
_SEEK_JS = "t => { for (const a of document.getAnimations()) { a.pause(); a.currentTime = t; } }"


class WebRenderError(RuntimeError):
    """Rendering failed after validation (browser unavailable, timeout, crash)."""


class WebSlideRenderer:
    """Async context manager: one browser for many scenes.

    ``async with WebSlideRenderer() as r: await r.render(...)``
    """

    def __init__(self, fps: int = FPS_DEFAULT, tokens: Optional[Dict[str, Any]] = None):
        if not isinstance(fps, int) or isinstance(fps, bool) or not 12 <= fps <= 60:
            raise ValueError("fps must be an integer in [12, 60]")
        self.fps = fps
        self.tokens = tokens
        self._pw = None
        self._browser = None

    async def __aenter__(self) -> "WebSlideRenderer":
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise WebRenderError("playwright is not installed (pip install playwright && playwright install chromium)") from e
        try:
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True)
        except Exception as e:  # noqa: BLE001 — any launch failure means "no web renderer"
            await self._close()
            raise WebRenderError(f"chromium could not be launched: {type(e).__name__}: {e}") from None
        return self

    async def __aexit__(self, *exc) -> None:
        await self._close()

    async def _close(self) -> None:
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:  # noqa: BLE001
                pass
            self._browser = None
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:  # noqa: BLE001
                pass
            self._pw = None

    async def render(
        self,
        template: str,
        data: Dict[str, Any],
        duration_s: float,
        out_dir: Path,
        *,
        theme: str = "dark",
        scene_index: Optional[int] = None,
        total_scenes: Optional[int] = None,
        lang: str = "en",
    ) -> List[Path]:
        """Render one scene to ``out_dir/00000.png ...``; returns the frame paths.

        Raises WebSceneError for invalid data (before the browser is touched)
        and WebRenderError for render failures.
        """
        if self._browser is None:
            raise WebRenderError("renderer is not open (use 'async with WebSlideRenderer()')")
        if isinstance(duration_s, bool) or not isinstance(duration_s, (int, float)) \
                or not math.isfinite(duration_s) or not 0 < duration_s <= MAX_SCENE_SECONDS:
            raise WebSceneError(f"duration must be in (0, {MAX_SCENE_SECONDS:.0f}] seconds, got {duration_s!r}")
        document = build_document(
            template, data, duration_s=float(duration_s), theme=theme, tokens=self.tokens,
            scene_index=scene_index, total_scenes=total_scenes, lang=lang,
        )
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        if any(out_dir.glob("*.png")):
            raise WebRenderError(f"frame directory {out_dir} is not empty")
        try:
            return await asyncio.wait_for(self._capture(document, float(duration_s), out_dir), SCENE_TIMEOUT_S)
        except asyncio.TimeoutError:
            raise WebRenderError(f"scene render exceeded {SCENE_TIMEOUT_S:.0f}s") from None
        except WebRenderError:
            raise
        except Exception as e:  # noqa: BLE001
            raise WebRenderError(f"scene render failed: {type(e).__name__}: {e}") from None

    async def _capture(self, document: str, duration_s: float, out_dir: Path) -> List[Path]:
        context = await self._browser.new_context(
            viewport=VIEWPORT, device_scale_factor=1, java_script_enabled=False,
            reduced_motion="no-preference", service_workers="block",
        )
        try:
            await context.route("**/*", lambda route: route.abort())
            page = await context.new_page()
            # CDP capture with optimizeForSpeed: same lossless pixels as page.screenshot,
            # ~3x faster PNG encoding (measured 16.4 vs 5.1 fps at 1920x1080).
            cdp = await context.new_cdp_session(page)
            await page.set_content(document, wait_until="load")
            missing = await page.evaluate(_LOAD_FONTS_JS)
            if missing:
                raise WebRenderError(f"bundled fonts did not load: {missing}")
            anim_end_ms = float(await page.evaluate(_ANIM_END_JS))
            span_ms = min(anim_end_ms, duration_s * 1000.0)
            n_frames = min(MAX_FRAMES_PER_SCENE, max(1, math.ceil(span_ms / 1000.0 * self.fps) + 1))
            frames: List[Path] = []
            for i in range(n_frames):
                await page.evaluate(_SEEK_JS, i * 1000.0 / self.fps)
                path = out_dir / f"{i:05d}.png"
                tmp = path.with_suffix(".png.tmp")
                shot = await cdp.send("Page.captureScreenshot", {"format": "png", "optimizeForSpeed": True})
                tmp.write_bytes(base64.b64decode(shot["data"]))
                os.replace(tmp, path)
                frames.append(path)
            return frames
        finally:
            await context.close()


async def render_web_scene(
    scene: Dict[str, Any],
    duration_s: float,
    out_dir: Path,
    fps: int = FPS_DEFAULT,
    theme: str = "dark",
) -> List[Path]:
    """Convenience wrapper for a single scene ({"template": ..., "data": {...}})."""
    async with WebSlideRenderer(fps=fps) as renderer:
        return await renderer.render(scene.get("template"), scene.get("data"), duration_s, out_dir, theme=theme)

"""Deterministic web-slide renderer (ADR-2238).

One headless Chromium per job renders each slide document and samples it at
fixed times by pausing every Web Animation and setting ``currentTime`` —
time is an input, never a wall clock, so two renders of the same scene are
bit-identical. Without a timeline, frames are written only until the last
entrance animation has finished and the assembler holds the final frame (or
loops the ambient period) for the rest of the narration. With a timeline
(ADR-2245) the whole narration is sampled: reveals and focus moves happen at
their cues until the very end, and frames in which nothing animates are not
captured again but scheduled as repeats of the previous one.

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
    from .web_templates import FOCUS_FADE_S, WebSceneError, build_document
    from .web_layout import LAYOUT_JS, TOLERANCE_PX
except ImportError:  # standalone script use (no package context)
    from web_templates import FOCUS_FADE_S, WebSceneError, build_document
    from web_layout import LAYOUT_JS, TOLERANCE_PX

FPS_DEFAULT = 30
MAX_SCENE_SECONDS = 60.0
MAX_FRAMES_PER_SCENE = 900
SCENE_TIMEOUT_S = 120.0
VIEWPORT = {"width": 1920, "height": 1080}

# [entrance end, ambient start, ambient period] in ms. Ambient = an animation with
# infinite iterations; it never ends, so it is excluded from the entrance end.
_ANIM_TIMING_JS = """() => {
  let end = 0, loopStart = 0, period = 0;
  for (const a of document.getAnimations()) {
    if (!a.effect || !a.effect.getComputedTiming) continue;
    const t = a.effect.getComputedTiming();
    if (t.iterations === Infinity) {
      period = Math.max(period, Number(t.duration) || 0);
      loopStart = Math.max(loopStart, Number(t.delay) || 0);
    } else if (Number.isFinite(t.endTime) && t.endTime > end) {
      end = t.endTime;
    }
  }
  return [end, loopStart, period];
}"""
_LOAD_FONTS_JS = """() => Promise.allSettled([
  "400 16px 'Newsreader'", "italic 400 16px 'Newsreader'",
  "400 16px 'Instrument Sans'", "400 16px 'JetBrains Mono'",
].map(f => document.fonts.load(f))).then(rs => document.fonts.ready.then(() =>
  ['Newsreader', 'Instrument Sans', 'JetBrains Mono'].filter(f => !document.fonts.check(`16px '${f}'`))))"""
_SEEK_JS = "t => { for (const a of document.getAnimations()) { a.pause(); a.currentTime = t; } }"
# Active windows [start, end] (ms) of every finite animation except the focus clock
# (its windows come from the timeline), and the earliest start of an infinite one.
_ACTIVE_JS = """() => {
  const spans = []; let inf = Infinity;
  for (const a of document.getAnimations()) {
    if (a.animationName === 'fclock' || !a.effect || !a.effect.getComputedTiming) continue;
    const t = a.effect.getComputedTiming();
    const d = Number(t.delay) || 0;
    if (t.iterations === Infinity) { inf = Math.min(inf, d); continue; }
    if (Number.isFinite(t.endTime)) spans.push([d, t.endTime]);
  }
  return [spans, Number.isFinite(inf) ? inf : -1];
}"""


# Transform/opacity animations otherwise run on the compositor thread, which can
# draw a frame that lags the paused currentTime: measured 54 of 149 frames
# differing between two browser instances (and a flaky in-process test). With
# animations ticked on the main thread and every compositor stage run before a
# draw, repeated cross-instance renders were identical.
_CHROMIUM_ARGS = (
    "--disable-threaded-animation",
    "--run-all-compositor-stages-before-draw",
    "--disable-checker-imaging",
)


class WebRenderError(RuntimeError):
    """Rendering failed after validation (browser unavailable, timeout, crash)."""


class FrameSequence(list):
    """The rendered frame paths. ``loop_start`` is the index of the first frame
    of one seamless ambient-motion period (frames[loop_start:] repeat), or None
    when the slide has no ambient motion and its last frame is held."""

    loop_start: Optional[int] = None
    layout_issues: List[Dict[str, Any]] = []  # collisions measured at the settled end state (web_layout)
    # Timeline renders: output frame -> index into this list. Repeats are frames in
    # which nothing animates; the assembler links them into a contiguous sequence.
    schedule: Optional[List[int]] = None


class WebSlideRenderer:
    """Async context manager: one browser for many scenes.

    ``async with WebSlideRenderer() as r: await r.render(...)``
    """

    def __init__(self, fps: int = FPS_DEFAULT, tokens: Optional[Dict[str, Any]] = None, style: Any = None):
        if not isinstance(fps, int) or isinstance(fps, bool) or not 12 <= fps <= 60:
            raise ValueError("fps must be an integer in [12, 60]")
        self.fps = fps
        self.tokens = tokens
        self.style = style
        self._pw = None
        self._browser = None

    async def __aenter__(self) -> "WebSlideRenderer":
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise WebRenderError("playwright is not installed (pip install playwright && playwright install chromium)") from e
        try:
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True, args=list(_CHROMIUM_ARGS))
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
        map_focus: Optional[str] = None,
        timeline: Any = None,
        compact: bool = False,
        chips: bool = True,
    ) -> FrameSequence:
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
            scene_index=scene_index, total_scenes=total_scenes, lang=lang, map_focus=map_focus,
            timeline=timeline, compact=compact, chips=chips, style=self.style,
        )
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        if any(out_dir.glob("*.png")):
            raise WebRenderError(f"frame directory {out_dir} is not empty")
        # a timeline render samples the whole narration: its budget grows with it
        budget = SCENE_TIMEOUT_S if timeline is None else max(SCENE_TIMEOUT_S, 30.0 + 3.0 * float(duration_s))
        try:
            return await asyncio.wait_for(self._capture(document, float(duration_s), out_dir, timeline), budget)
        except asyncio.TimeoutError:
            raise WebRenderError(f"scene render exceeded {budget:g}s") from None
        except WebRenderError:
            raise
        except Exception as e:  # noqa: BLE001
            raise WebRenderError(f"scene render failed: {type(e).__name__}: {e}") from None

    async def _capture(self, document: str, duration_s: float, out_dir: Path, timeline: Any = None) -> FrameSequence:
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
            # Always render the complete entrance animation, even when the narration is
            # shorter: a frame cut mid-reveal can show a half-rolled number. The assembler
            # pads the audio instead (see skill._assemble_frames_clip).
            anim_end_ms, loop_start_ms, period_ms = (float(x) for x in await page.evaluate(_ANIM_TIMING_JS))
            if timeline is not None:
                return await self._capture_timeline(page, cdp, out_dir, duration_s, anim_end_ms, timeline)
            n_frames = max(1, math.ceil(anim_end_ms / 1000.0 * self.fps) + 1)
            frames = FrameSequence()
            await page.evaluate(_SEEK_JS, anim_end_ms)
            frames.layout_issues = await page.evaluate(LAYOUT_JS, TOLERANCE_PX)
            # Ambient motion: sample exactly one period after everything has started.
            # Frame loop_start + period_frames equals frame loop_start only when the
            # period is a whole number of frames — otherwise the loop would jump.
            period_frames = period_ms / 1000.0 * self.fps
            if period_ms > 0 and abs(period_frames - round(period_frames)) < 1e-6:
                start = max(n_frames, math.ceil(loop_start_ms / 1000.0 * self.fps))
                if start + round(period_frames) <= MAX_FRAMES_PER_SCENE:
                    frames.loop_start = start
                    n_frames = start + int(round(period_frames))
            n_frames = min(MAX_FRAMES_PER_SCENE, n_frames)
            for i in range(n_frames):
                await page.evaluate(_SEEK_JS, i * 1000.0 / self.fps)
                frames.append(await self._shot(cdp, out_dir, i))
            return frames
        finally:
            await context.close()

    async def render_still(
        self,
        template: str,
        data: Dict[str, Any],
        *,
        theme: str = "dark",
        duration_s: float = 6.0,
        timeout_s: float = 30.0,
    ) -> bytes:
        """One PNG of a slide at the END state of its entrance animation (style previews).

        Same hardening as the video path: JavaScript off, every request aborted, bundled fonts
        required. Raises WebSceneError for invalid data and WebRenderError for render failures."""
        if self._browser is None:
            raise WebRenderError("renderer is not open (use 'async with WebSlideRenderer()')")
        document = build_document(template, data, duration_s=float(duration_s), theme=theme,
                                  tokens=self.tokens, style=self.style)

        async def _go() -> bytes:
            context = await self._browser.new_context(
                viewport=VIEWPORT, device_scale_factor=1, java_script_enabled=False,
                reduced_motion="no-preference", service_workers="block",
            )
            try:
                await context.route("**/*", lambda route: route.abort())
                page = await context.new_page()
                cdp = await context.new_cdp_session(page)
                await page.set_content(document, wait_until="load")
                missing = await page.evaluate(_LOAD_FONTS_JS)
                if missing:
                    raise WebRenderError(f"bundled fonts did not load: {missing}")
                anim_end_ms = float((await page.evaluate(_ANIM_TIMING_JS))[0])
                await page.evaluate(_SEEK_JS, anim_end_ms)
                shot = await cdp.send("Page.captureScreenshot", {"format": "png"})
                return base64.b64decode(shot["data"])
            finally:
                await context.close()

        try:
            return await asyncio.wait_for(_go(), timeout_s)
        except asyncio.TimeoutError:
            raise WebRenderError(f"still render exceeded {timeout_s:g}s") from None
        except WebRenderError:
            raise
        except Exception as e:  # noqa: BLE001
            raise WebRenderError(f"still render failed: {type(e).__name__}: {e}") from None

    async def _shot(self, cdp, out_dir: Path, index: int) -> Path:
        path = out_dir / f"{index:05d}.png"
        tmp = path.with_suffix(".png.tmp")
        shot = await cdp.send("Page.captureScreenshot", {"format": "png", "optimizeForSpeed": True})
        tmp.write_bytes(base64.b64decode(shot["data"]))
        os.replace(tmp, path)
        return path

    async def _capture_timeline(self, page, cdp, out_dir: Path, duration_s: float, anim_end_ms: float,
                                timeline: Any) -> FrameSequence:
        """Sample [0, max(narration, last animation)] at fps. A frame is captured only
        when something can have changed since the previous capture; every other
        output frame repeats it (``schedule``). Nothing past the frame budget is
        dropped silently: a cue the budget cannot reach is an error (ADR-2245 §5)."""
        total_s = max(duration_s, anim_end_ms / 1000.0)
        n_out = math.ceil(total_s * self.fps) + 1
        cap = int(MAX_SCENE_SECONDS * self.fps) + 2 * self.fps
        last_cue = max(timeline.event_times() or [0.0])
        if n_out > cap or last_cue * self.fps >= n_out:
            raise WebRenderError(f"timeline does not fit the frame budget ({n_out} frames, cue at {last_cue:.1f}s)")
        spans, inf_start_ms = await page.evaluate(_ACTIVE_JS)
        windows = [(a / 1000.0, b / 1000.0) for a, b in spans]
        windows += [(t, t + FOCUS_FADE_S) for t, _ in timeline.focus]
        inf_start = inf_start_ms / 1000.0 if inf_start_ms >= 0 else None
        step = 1.0 / self.fps

        def active(t: float) -> bool:
            if inf_start is not None and t >= inf_start:
                return True
            # one extra frame on both sides: the frame that shows the settled state is captured
            return any(a - step <= t <= b + step for a, b in windows)

        await page.evaluate(_SEEK_JS, total_s * 1000.0)
        frames = FrameSequence()
        frames.layout_issues = await page.evaluate(LAYOUT_JS, TOLERANCE_PX)
        frames.schedule = []
        for i in range(n_out):
            t = i * step
            if not frames or active(t):
                await page.evaluate(_SEEK_JS, t * 1000.0)
                frames.append(await self._shot(cdp, out_dir, len(frames)))
            frames.schedule.append(len(frames) - 1)
        return frames


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

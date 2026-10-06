"""Screenshot Capturer: real Playwright-based screenshot capture (CONCEPT-0095).

Captures a single screenshot of a URL, optionally resolving a CSS selector to
its bounding box so a caller can draw a highlight over it
(screenshot_annotator.py). Three fail-closed gates, all hard errors — the
first two are new, the third is ported from the dead reference
`core/skills/video_producer/workers/screenshot_capturer.py` (CONCEPT-0095
§Evidence, "a correct, already-proven pattern, worth carrying forward"):

1. URL allowlist (security/egress boundary — CONCEPT-0095 "must not be
   skipped"): only localhost/127.0.0.1 targets are permitted. A worker that
   can navigate Playwright to an arbitrary URL is a new network-egress
   surface; CorvinOS's L35 egress model is deny-by-default, and CONCEPT-0095
   explicitly deferred relaxing it to a future ADR rather than defaulting
   open here.
2. Selector-resolution gate: if a highlight_selector is given and it does not
   resolve to a visible element, this is a hard error — never a silently
   un-annotated screenshot shipped as if it were correct.
3. Visual-Content-Spec gate: rejects a placeholder/solid-color screenshot
   (insufficient color diversity, or one color dominating the frame) before
   it can ship in a video.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

ALLOWED_SCREENSHOT_HOSTS = {"localhost", "127.0.0.1"}


class ScreenshotCaptureError(ValueError):
    """Raised by any fail-closed gate in this module — always a hard stop,
    never a silent fallback to a placeholder or an un-annotated image."""


@dataclass
class CaptureResult:
    path: Path
    # Playwright's bounding_box() shape: {"x", "y", "width", "height"} in
    # CSS px, in the SAME coordinate space as the saved screenshot (the
    # capture viewport is fixed, so no rescaling is needed by callers).
    bounding_box: Optional[Dict[str, float]]


def validate_screenshot_url(url: str) -> None:
    """Fail-closed allowlist gate. Only http(s)://localhost or 127.0.0.1
    (any port) are permitted today. Raises ScreenshotCaptureError otherwise.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ScreenshotCaptureError(
            f"screenshot_url must be http(s), got scheme {parsed.scheme!r} in {url!r}"
        )
    if parsed.hostname not in ALLOWED_SCREENSHOT_HOSTS:
        raise ScreenshotCaptureError(
            f"screenshot_url host {parsed.hostname!r} is not in the allowlist "
            f"{sorted(ALLOWED_SCREENSHOT_HOSTS)} (CONCEPT-0095 scopes this worker "
            f"to localhost only; a non-localhost target needs its own ADR — a new "
            f"network-egress surface is not something this worker defaults open)"
        )


async def capture_screenshot(
    url: str,
    out_path: Path,
    highlight_selector: Optional[str] = None,
    viewport_width: int = 1280,
    viewport_height: int = 720,
    timeout_ms: int = 10_000,
) -> CaptureResult:
    """Navigate to `url`, optionally resolve `highlight_selector`'s bounding
    box, capture a screenshot to `out_path`.

    This is a plain async function — callers that are already inside an
    async context (``orchestrate_video``) should ``await`` it directly.
    It does NOT spin up its own event loop (unlike the dead reference
    implementation it was ported from): nesting ``asyncio.new_event_loop()``
    inside an already-running loop is a real hazard, and the live caller
    here is async end-to-end at this call site, so there is nothing to
    bridge.

    Raises ScreenshotCaptureError (fail-closed) if:
    - ``url`` fails the allowlist gate
    - ``highlight_selector`` is given but doesn't resolve to a visible element
    - the captured image fails the Visual-Content-Spec gate
    """
    validate_screenshot_url(url)

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for screenshot scenes but is not installed — "
            "pip install playwright && playwright install chromium"
        ) from exc

    bounding_box: Optional[Dict[str, float]] = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(
                viewport={"width": viewport_width, "height": viewport_height}
            )
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)

            if highlight_selector:
                from playwright.async_api import Error as PlaywrightError

                # bounding_box() does NOT return None when the selector never
                # resolves (measured, not assumed) — it waits up to `timeout`
                # and then raises Playwright's own TimeoutError. A caller
                # that only checked `if box is None` would never see that
                # branch; translate it into our own fail-closed error type
                # instead of leaking a third-party exception class.
                try:
                    box = await page.locator(highlight_selector).bounding_box(
                        timeout=timeout_ms
                    )
                except PlaywrightError as exc:
                    raise ScreenshotCaptureError(
                        f"highlight_selector {highlight_selector!r} did not resolve "
                        f"to a visible element on {url!r} within {timeout_ms}ms — "
                        f"fix the selector or the page; never shipping an "
                        f"un-annotated screenshot silently ({exc})"
                    ) from exc
                if box is None:
                    # Reachable in principle (a detached/hidden element can
                    # resolve the locator but have no box) even though the
                    # not-found case above raises instead — keep this as a
                    # second, independent fail-closed path.
                    raise ScreenshotCaptureError(
                        f"highlight_selector {highlight_selector!r} resolved but has "
                        f"no bounding box (detached or not rendered) on {url!r}"
                    )
                bounding_box = box

            await page.screenshot(path=str(out_path))
        finally:
            await browser.close()

    _validate_screenshot_content(out_path)

    return CaptureResult(path=out_path, bounding_box=bounding_box)


def _validate_screenshot_content(
    path: Path,
    min_unique_colors: int = 10,
    max_solid_color_ratio: float = 0.999,
) -> None:
    """Gate 3: Visual-Content-Spec (ported from the dead reference
    implementation, recalibrated here — the inherited 0.95 threshold was
    measured, not assumed, to reject legitimate content). Rejects
    placeholder/solid-color screenshots — Playwright does not raise when a
    page is blank or fails to render; this is the only thing that catches it
    before a broken frame ships in a video.

    Measured on a real Console-style page (dark flat background, one
    button): dominant_ratio=0.9913, unique_colors=158 — the inherited 0.95
    threshold rejected this as a "placeholder", a false positive, because
    admin/console UIs are routinely >95% one background color by design. A
    genuinely blank page (no elements at all) measured dominant_ratio=1.0
    EXACTLY, unique_colors=1 — the real discriminating signal is
    unique_colors (1 vs. 158, two orders of magnitude), which
    min_unique_colors already catches independently. max_solid_color_ratio
    is raised to 0.999 so it only fires on an almost-exactly-blank frame,
    not on legitimately sparse real content.
    """
    from PIL import Image

    if not path.exists():
        raise ScreenshotCaptureError(f"Screenshot not found: {path}")

    img = Image.open(path)
    width, height = img.size
    if width < 100 or height < 100:
        raise ScreenshotCaptureError(
            f"Screenshot too small ({width}x{height}px, minimum 100x100px) — "
            f"likely a broken capture"
        )

    pixels = list(img.convert("RGB").getdata())
    unique_colors = len(set(pixels))
    if unique_colors < min_unique_colors:
        raise ScreenshotCaptureError(
            f"Screenshot has only {unique_colors} unique colors "
            f"(< {min_unique_colors} minimum) — likely a solid-color placeholder, "
            f"not real content"
        )

    color_counts: Dict[tuple, int] = {}
    for px in pixels:
        color_counts[px] = color_counts.get(px, 0) + 1
    dominant_ratio = max(color_counts.values()) / len(pixels)
    if dominant_ratio > max_solid_color_ratio:
        raise ScreenshotCaptureError(
            f"Screenshot is {dominant_ratio * 100:.1f}% one color "
            f"(> {max_solid_color_ratio * 100:.0f}% threshold) — likely a "
            f"placeholder, not real content"
        )

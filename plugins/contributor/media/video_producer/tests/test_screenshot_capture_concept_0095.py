"""E2E + call-site-wiring proof for annotated screenshot capture (CONCEPT-0095).

Mirrors the methodology established in test_e2e_didactic_corvin_compliance.py
(ADR-0004): real Playwright navigation + real HTTP server + real PIL pixel
checks, not mocks — a mocked "E2E" test proves the mock works, not the
pipeline. Requires `playwright install chromium` to have been run once in
this environment; skips (not fails) if Playwright or its browser isn't
available, consistent with the suite's existing Ollama/ffmpeg skip pattern.
"""
import asyncio
import http.server
import re
import shutil
import threading
from pathlib import Path

import pytest

from src.screenshot_capturer import (
    capture_screenshot,
    validate_screenshot_url,
    ScreenshotCaptureError,
    ALLOWED_SCREENSHOT_HOSTS,
)
from src.screenshot_annotator import annotate_screenshot, DEFAULT_SPOTLIGHT_COLOR
from src.models import Scene

SKILL_PY = Path(__file__).parent.parent / "src" / "skill.py"

try:
    import playwright  # noqa: F401
    PLAYWRIGHT_INSTALLED = True
except ImportError:
    PLAYWRIGHT_INSTALLED = False


def _chromium_available() -> bool:
    if not PLAYWRIGHT_INSTALLED:
        return False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            b.close()
        return True
    except Exception:
        return False


CHROMIUM_AVAILABLE = _chromium_available()


@pytest.fixture(scope="module")
def local_test_page():
    """A real local HTTP server serving a page with one button at a known
    position — real navigation + real selector resolution, not a stub."""
    site_dir = Path("/tmp/concept_0095_test_site")
    site_dir.mkdir(exist_ok=True)
    (site_dir / "index.html").write_text(
        '<html><body style="margin:0;background:#1d2a44">'
        '<button id="save-btn" style="position:absolute;left:300px;top:150px;'
        'width:160px;height:50px;background:#e0a032">Save</button>'
        "</body></html>"
    )

    handler = http.server.SimpleHTTPRequestHandler
    import functools
    handler = functools.partial(handler, directory=str(site_dir))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/"
    server.shutdown()


# ===========================================================================
# PART 1 — Call-site-wiring proof (the "tote Mechanismen" feedback)
# ===========================================================================

class TestCallSiteWiring:
    """Proves the new screenshot mechanisms have a real caller in
    orchestrate_video(), not just a unit test that imports them directly."""

    def test_render_screenshot_scene_is_called_from_orchestrate_video(self):
        src = SKILL_PY.read_text()
        fn_start = src.index("async def orchestrate_video")
        fn_body = src[fn_start:fn_start + 6000]
        assert "_render_screenshot_scene(" in fn_body, (
            "orchestrate_video() must call _render_screenshot_scene() for "
            "kind=='screenshot' scenes — a regression that removes this call "
            "silently reverts to the placeholder slide."
        )

    def test_capture_screenshot_is_called_from_render_screenshot_scene(self):
        src = SKILL_PY.read_text()
        fn_start = src.index("async def _render_screenshot_scene")
        fn_end = src.index("\ndef _assemble_scene_clip", fn_start)
        fn_body = src[fn_start:fn_end]
        assert "capture_screenshot(" in fn_body
        assert "annotate_screenshot(" in fn_body

    def test_screenshot_kind_branches_before_placeholder_renderer(self):
        """orchestrate_video's scene loop must check kind=='screenshot'
        BEFORE falling through to the placeholder _render_slide_image call —
        otherwise every screenshot scene silently gets the placeholder."""
        src = SKILL_PY.read_text()
        fn_start = src.index("async def orchestrate_video")
        fn_body = src[fn_start:fn_start + 6000]
        m = re.search(
            r'if scene\.kind == "screenshot":\s*\n\s*await _render_screenshot_scene',
            fn_body,
        )
        assert m, "expected an `if scene.kind == \"screenshot\"` branch guarding _render_screenshot_scene"


# ===========================================================================
# PART 2 — Allowlist gate (security/egress boundary, CONCEPT-0095 "must not
# be skipped")
# ===========================================================================

class TestAllowlistGate:
    def test_localhost_is_allowed_by_default(self):
        assert "localhost" in ALLOWED_SCREENSHOT_HOSTS
        assert "127.0.0.1" in ALLOWED_SCREENSHOT_HOSTS

    def test_rejects_external_host(self):
        with pytest.raises(ScreenshotCaptureError, match="not in the allowlist"):
            validate_screenshot_url("http://example.com/")

    def test_rejects_non_http_scheme(self):
        with pytest.raises(ScreenshotCaptureError, match="must be http"):
            validate_screenshot_url("file:///etc/passwd")

    def test_accepts_localhost_with_port(self):
        validate_screenshot_url("http://127.0.0.1:8765/console/")
        validate_screenshot_url("http://localhost:3000/app")


# ===========================================================================
# PART 3 — Annotation (pure PIL, real pixels)
# ===========================================================================

class TestAnnotation:
    def test_draws_spotlight_outline_at_bounding_box(self, tmp_path):
        from PIL import Image

        src_img = tmp_path / "src.png"
        Image.new("RGB", (400, 300), color=(20, 20, 20)).save(src_img)

        out_img = tmp_path / "out.png"
        bbox = {"x": 100.0, "y": 100.0, "width": 80.0, "height": 40.0}
        annotate_screenshot(src_img, bbox, out_img, color=DEFAULT_SPOTLIGHT_COLOR)

        assert out_img.exists()
        img = Image.open(out_img)
        px = img.load()
        # The outline is a rounded rect `padding` outside the bbox — scan a
        # generous ring area (not just one exact row, which can land on the
        # curved corner instead of the straight edge or stroke antialiasing)
        # for the spotlight color, same approach as the passing full-pipeline
        # E2E test below.
        found = any(
            px[x, y] == DEFAULT_SPOTLIGHT_COLOR
            for x in range(70, 210)
            for y in range(75, 170)
        )
        assert found, "expected spotlight color somewhere around the outline"

    def test_does_not_modify_source_image(self, tmp_path):
        from PIL import Image

        src_img = tmp_path / "src.png"
        Image.new("RGB", (200, 200), color=(50, 50, 50)).save(src_img)
        original_bytes = src_img.read_bytes()

        out_img = tmp_path / "out.png"
        annotate_screenshot(
            src_img, {"x": 10.0, "y": 10.0, "width": 20.0, "height": 20.0}, out_img
        )

        assert src_img.read_bytes() == original_bytes, "source must not be mutated"


# ===========================================================================
# PART 4 — Full E2E: real Playwright capture against a real local server
# ===========================================================================

@pytest.mark.e2e
@pytest.mark.skipif(not CHROMIUM_AVAILABLE, reason="Playwright/Chromium not available in this environment")
class TestRealCapture:
    @pytest.mark.asyncio
    async def test_captures_real_screenshot_with_resolved_bounding_box(self, local_test_page, tmp_path):
        out = tmp_path / "capture.png"
        result = await capture_screenshot(local_test_page, out, highlight_selector="#save-btn")

        assert out.exists()
        assert result.bounding_box is not None
        assert abs(result.bounding_box["x"] - 300) < 1
        assert abs(result.bounding_box["y"] - 150) < 1
        assert abs(result.bounding_box["width"] - 160) < 1

        # Real PNG, real pixels — not a 1x1 placeholder.
        with open(out, "rb") as f:
            assert f.read(8) == b"\x89PNG\r\n\x1a\n"

    @pytest.mark.asyncio
    async def test_missing_selector_raises_fail_closed(self, local_test_page, tmp_path):
        out = tmp_path / "capture.png"
        with pytest.raises(ScreenshotCaptureError, match="did not resolve"):
            await capture_screenshot(
                local_test_page, out, highlight_selector="#does-not-exist", timeout_ms=1500
            )

    @pytest.mark.asyncio
    async def test_capture_without_selector_has_no_bounding_box(self, local_test_page, tmp_path):
        out = tmp_path / "capture.png"
        result = await capture_screenshot(local_test_page, out)
        assert result.bounding_box is None
        assert out.exists()

    @pytest.mark.asyncio
    async def test_full_pipeline_capture_then_annotate(self, local_test_page, tmp_path):
        """The actual Scene-driven path: capture, then annotate in place —
        same two-call sequence _render_screenshot_scene uses."""
        image_path = tmp_path / "scene_001.png"
        scene = Scene(
            id="s1", kind="screenshot", duration_ms=5000,
            screenshot_url=local_test_page, highlight_selector="#save-btn",
        )

        result = await capture_screenshot(
            scene.screenshot_url, image_path, highlight_selector=scene.highlight_selector
        )
        assert result.bounding_box is not None

        annotated = tmp_path / "scene_001.annotated.png"
        annotate_screenshot(image_path, result.bounding_box, annotated)

        from PIL import Image
        img = Image.open(annotated)
        px = img.load()
        found = any(
            px[x, y] == DEFAULT_SPOTLIGHT_COLOR
            for x in range(280, 480)
            for y in range(130, 220)
        )
        assert found, "expected the spotlight outline color somewhere around the button"

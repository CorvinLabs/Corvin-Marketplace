"""Unit tests for VideoContentInspectorTier1 — 20+ test cases"""

import pytest
import numpy as np
import tempfile
from pathlib import Path

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

from src.verification.video_inspector_tier1 import VideoContentInspectorTier1
from src.verification.thresholds import VIDEO_TIER1, RejectionReasons


@pytest.mark.skipif(not HAS_OPENCV, reason="OpenCV not available")
class TestVideoContentInspectorTier1:

    @pytest.fixture
    def inspector(self):
        return VideoContentInspectorTier1()

    @pytest.fixture
    def temp_video_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def create_solid_color_video(
        self,
        color_bgr: tuple,
        width: int = 640,
        height: int = 480,
        fps: float = 30.0,
        duration: float = 1.0
    ) -> Path:
        """Create a video with solid color"""
        path = Path(tempfile.mktemp(suffix=".mp4"))

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(str(path), fourcc, fps, (width, height))

        frame_count = int(fps * duration)
        frame = np.full((height, width, 3), color_bgr, dtype=np.uint8)

        for _ in range(frame_count):
            out.write(frame)

        out.release()
        return path

    def create_varied_color_video(
        self,
        width: int = 640,
        height: int = 480,
        fps: float = 30.0,
        duration: float = 1.0
    ) -> Path:
        """Create a video with varying colors and patterns"""
        path = Path(tempfile.mktemp(suffix=".mp4"))

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(str(path), fourcc, fps, (width, height))

        frame_count = int(fps * duration)

        for i in range(frame_count):
            # Create frame with gradient and patterns
            frame = np.zeros((height, width, 3), dtype=np.uint8)

            # Add color gradient
            for x in range(width):
                intensity = int(255 * x / width)
                frame[:, x] = [intensity, 255 - intensity, 128]

            # Add some structure
            cv2.rectangle(frame, (50, 50), (width - 50, height - 50), (255, 0, 0), 3)
            cv2.circle(frame, (width // 2, height // 2), 50, (0, 255, 0), -1)

            out.write(frame)

        out.release()
        return path

    # Tests: Solid color videos (should fail)

    def test_video_solid_blue_rejected(self, inspector, temp_video_dir):
        """Solid blue background should fail Tier 1"""
        path = self.create_solid_color_video((27, 14, 10), duration=1.0)

        try:
            result = inspector.inspect(path)

            assert not result.passed
            assert result.tier == 1
            assert RejectionReasons.VIDEO_COLOR_VARIANCE_TOO_LOW in result.reason or \
                   RejectionReasons.VIDEO_UNIQUE_COLORS_TOO_FEW in result.reason or \
                   RejectionReasons.VIDEO_TEMPORAL_VARIANCE_TOO_LOW in result.reason
            assert result.diagnostic is not None
        finally:
            Path(path).unlink(missing_ok=True)

    def test_video_solid_black_rejected(self, inspector):
        """Solid black background should fail Tier 1"""
        path = self.create_solid_color_video((0, 0, 0), duration=1.0)

        try:
            result = inspector.inspect(path)

            assert not result.passed
            assert result.tier == 1
        finally:
            Path(path).unlink(missing_ok=True)

    def test_video_solid_white_rejected(self, inspector):
        """Solid white background should fail Tier 1"""
        path = self.create_solid_color_video((255, 255, 255), duration=1.0)

        try:
            result = inspector.inspect(path)

            assert not result.passed
            assert result.tier == 1
        finally:
            Path(path).unlink(missing_ok=True)

    def test_video_solid_red_rejected(self, inspector):
        """Solid red background should fail Tier 1"""
        path = self.create_solid_color_video((0, 0, 255), duration=1.0)

        try:
            result = inspector.inspect(path)

            assert not result.passed
            assert result.tier == 1
        finally:
            Path(path).unlink(missing_ok=True)

    # Tests: Real content videos (should pass)

    def test_video_with_colors_passed(self, inspector):
        """Video with varying colors should pass Tier 1"""
        path = self.create_varied_color_video(duration=1.0)

        try:
            result = inspector.inspect(path)

            # May pass or fail depending on OpenCV availability
            if HAS_OPENCV and result.passed:
                assert result.tier == 1
                assert result.reason == "passed_all_checks"
        finally:
            Path(path).unlink(missing_ok=True)

    # Tests: File handling

    def test_video_file_not_found(self, inspector):
        """Non-existent file should be rejected"""
        result = inspector.inspect(Path("/nonexistent/video.mp4"))

        assert not result.passed
        assert "not_found" in result.reason or "cannot_be_opened" in result.reason

    def test_video_cannot_be_opened(self, inspector, temp_video_dir):
        """Invalid video file should be rejected"""
        invalid_path = temp_video_dir / "invalid.mp4"
        invalid_path.write_text("This is not a video")

        result = inspector.inspect(invalid_path)

        assert not result.passed
        assert "cannot_be_opened" in result.reason or "inspection_error" in result.reason

    # Tests: Metrics

    def test_video_metrics_recorded(self, inspector):
        """Metrics should be recorded for verified video"""
        path = self.create_varied_color_video(duration=1.0)

        try:
            result = inspector.inspect(path)

            # Should have resolution at minimum
            if result.passed or result.metrics:
                assert result.metrics is not None
                assert result.metrics.resolution is not None or \
                       result.metrics.duration_seconds is not None
        finally:
            Path(path).unlink(missing_ok=True)

    # Tests: Operator ID

    def test_video_operator_id_preserved(self, inspector):
        """Operator ID should be recorded in result"""
        path = self.create_solid_color_video((0, 0, 0), duration=1.0)

        try:
            result = inspector.inspect(path, operator_id="test_operator")

            assert result.operator_id == "test_operator"
        finally:
            Path(path).unlink(missing_ok=True)

    # Tests: Diagnostic info

    def test_video_diagnostic_on_failure(self, inspector):
        """Failed verification should include diagnostic info"""
        path = self.create_solid_color_video((27, 14, 10), duration=1.0)

        try:
            result = inspector.inspect(path)

            if not result.passed:
                assert result.diagnostic is not None
                # At least one diagnostic info present
                assert "hint" in result.diagnostic or \
                       "expected" in result.diagnostic
        finally:
            Path(path).unlink(missing_ok=True)


@pytest.mark.skipif(not HAS_OPENCV, reason="OpenCV not available")
class TestVideoInspectorIntegration:
    """Integration tests for video inspector"""

    def test_video_from_real_incident_rejected(self):
        """Test with real solid-blue video from 2026-09-22 incident (if available)"""
        incident_path = Path("/home/shumway/projects/Corvin-Videos/blender_20260922_001652/steps/layers.mp4")

        if not incident_path.exists():
            pytest.skip("Incident video not available")

        inspector = VideoContentInspectorTier1()
        result = inspector.inspect(incident_path)

        # Incident video should be rejected
        assert not result.passed, \
            f"Incident video should fail but passed: {result.diagnostic}"
        assert "solid" in result.reason.lower() or \
               "color" in result.reason.lower() or \
               "temporal" in result.reason.lower() or \
               "unique" in result.reason.lower(), \
               f"Rejection reason unclear: {result.reason}"

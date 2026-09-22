"""Tests for VerificationOrchestrator"""

import pytest
import tempfile
from pathlib import Path

try:
    import librosa
    import soundfile
    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

from src.verification.orchestrator import VerificationOrchestrator, VerificationTier


@pytest.mark.skipif(not (HAS_AUDIO and HAS_OPENCV), reason="librosa or OpenCV not available")
class TestVerificationOrchestrator:

    @pytest.fixture
    def orchestrator(self):
        return VerificationOrchestrator(operator_id="test_op")

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def create_sine_audio(self, freq: float, duration: float, sr: int = 48000) -> Path:
        """Create sine tone audio"""
        import numpy as np
        t = np.linspace(0, duration, int(sr * duration))
        audio = np.sin(2 * np.pi * freq * t).astype(np.float32)

        path = Path(tempfile.mktemp(suffix=".wav"))
        soundfile.write(str(path), audio, sr)
        return path

    def create_noise_audio(self, duration: float, sr: int = 48000) -> Path:
        """Create noise audio"""
        import numpy as np
        audio = np.random.randn(int(sr * duration)).astype(np.float32) * 0.5

        path = Path(tempfile.mktemp(suffix=".wav"))
        soundfile.write(str(path), audio, sr)
        return path

    def create_solid_video(self, color_bgr: tuple = (27, 14, 10)) -> Path:
        """Create solid color video"""
        path = Path(tempfile.mktemp(suffix=".mp4"))

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(str(path), fourcc, 30.0, (640, 480))

        import numpy as np
        frame = np.full((480, 640, 3), color_bgr, dtype=np.uint8)

        for _ in range(30):
            out.write(frame)

        out.release()
        return path

    # Skip verification tests

    def test_skip_verification(self, orchestrator):
        """Test skipping verification"""
        video_path = Path("/tmp/test_video.mp4")

        passed, reason = orchestrator.verify_video(
            video_path,
            skip_verification=True,
            skip_reason="test_skip"
        )

        assert passed
        assert "verification_skipped" in reason

    # Audio verification tests

    def test_audio_verification_fails_sine(self, orchestrator):
        """Sine audio should fail verification"""
        audio_path = self.create_sine_audio(440, 1.0)

        try:
            passed, reason = orchestrator.verify_audio_only(audio_path)

            assert not passed
        finally:
            audio_path.unlink(missing_ok=True)

    def test_audio_verification_passes_noise(self, orchestrator):
        """Noise audio should pass verification"""
        audio_path = self.create_noise_audio(1.0)

        try:
            passed, reason = orchestrator.verify_audio_only(audio_path)

            assert passed
            assert "audio_verification_passed" in reason
        finally:
            audio_path.unlink(missing_ok=True)

    # Video verification tests

    def test_video_verification_fails_solid(self, orchestrator):
        """Solid color video should fail verification"""
        video_path = self.create_solid_video()

        try:
            passed, reason = orchestrator.verify_video_only(video_path)

            assert not passed
        finally:
            video_path.unlink(missing_ok=True)

    # Combined verification tests

    def test_combined_verification_all_bad(self, orchestrator):
        """Both audio and video bad should fail"""
        audio_path = self.create_sine_audio(440, 1.0)
        video_path = self.create_solid_video()

        try:
            passed, reason = orchestrator.verify_video(
                video_path,
                audio_path=audio_path
            )

            assert not passed
        finally:
            audio_path.unlink(missing_ok=True)
            video_path.unlink(missing_ok=True)

    # Tier selection tests

    def test_tier_1_only(self, orchestrator):
        """Test Tier 1 only verification"""
        video_path = self.create_solid_video()

        try:
            passed, reason = orchestrator.verify_video(
                video_path,
                tier=VerificationTier.TIER_1_ONLY
            )

            assert not passed
        finally:
            video_path.unlink(missing_ok=True)

    def test_operator_id_preserved(self, orchestrator):
        """Operator ID should be preserved throughout verification"""
        audio_path = self.create_noise_audio(1.0)

        try:
            result = orchestrator.audio_inspector.inspect(audio_path, "my_op")

            assert result.operator_id == "my_op"
        finally:
            audio_path.unlink(missing_ok=True)

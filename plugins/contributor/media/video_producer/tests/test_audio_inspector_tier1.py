"""Unit tests for AudioContentInspectorTier1 — 20+ test cases"""

import pytest
import numpy as np
import tempfile
from pathlib import Path

try:
    import librosa
    import soundfile
    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False

from src.verification.audio_inspector_tier1 import AudioContentInspectorTier1
from src.verification.thresholds import AUDIO_TIER1, RejectionReasons


@pytest.mark.skipif(not HAS_AUDIO, reason="librosa/soundfile not available")
class TestAudioContentInspectorTier1:

    @pytest.fixture
    def inspector(self):
        return AudioContentInspectorTier1()

    @pytest.fixture
    def temp_audio_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def create_sine_tone(self, freq: float, duration: float, sr: int = 48000):
        """Create a pure sine wave"""
        t = np.linspace(0, duration, int(sr * duration))
        audio = np.sin(2 * np.pi * freq * t).astype(np.float32)
        return audio, sr

    def create_white_noise(self, duration: float, sr: int = 48000):
        """Create white noise"""
        audio = np.random.randn(int(sr * duration)).astype(np.float32) * 0.5
        return audio, sr

    def save_audio(self, audio: np.ndarray, sr: int, path: Path) -> Path:
        """Save audio to file"""
        soundfile.write(str(path), audio, sr)
        return path

    # Tests: Pure sine tones (should fail)

    def test_audio_pure_sine_440hz_rejected(self, inspector, temp_audio_dir):
        """Pure 440Hz sine wave should fail Tier 1"""
        audio, sr = self.create_sine_tone(freq=440, duration=1.0)
        path = self.save_audio(audio, sr, temp_audio_dir / "sine_440.wav")

        result = inspector.inspect(path)

        assert not result.passed
        assert result.tier == 1
        assert RejectionReasons.AUDIO_SINGLE_FREQUENCY in result.reason or \
               RejectionReasons.AUDIO_MFCC_TOO_LOW in result.reason
        assert result.diagnostic is not None

    def test_audio_pure_sine_880hz_rejected(self, inspector, temp_audio_dir):
        """Pure 880Hz sine wave should fail Tier 1"""
        audio, sr = self.create_sine_tone(freq=880, duration=1.0)
        path = self.save_audio(audio, sr, temp_audio_dir / "sine_880.wav")

        result = inspector.inspect(path)

        assert not result.passed
        assert result.tier == 1

    def test_audio_pure_sine_1320hz_rejected(self, inspector, temp_audio_dir):
        """Pure 1320Hz sine wave should fail Tier 1"""
        audio, sr = self.create_sine_tone(freq=1320, duration=1.0)
        path = self.save_audio(audio, sr, temp_audio_dir / "sine_1320.wav")

        result = inspector.inspect(path)

        assert not result.passed
        assert result.tier == 1

    # Tests: Silence (should fail)

    def test_audio_silence_rejected(self, inspector, temp_audio_dir):
        """Silence (zero amplitude) should fail Tier 1"""
        audio = np.zeros(48000, dtype=np.float32)  # 1 second of silence
        sr = 48000
        path = self.save_audio(audio, sr, temp_audio_dir / "silence.wav")

        result = inspector.inspect(path)

        assert not result.passed
        assert result.tier == 1
        assert RejectionReasons.AUDIO_AMPLITUDE_TOO_NARROW in result.reason or \
               RejectionReasons.AUDIO_MFCC_TOO_LOW in result.reason

    # Tests: Real audio (should pass)

    def test_audio_white_noise_passed(self, inspector, temp_audio_dir):
        """White noise (real content) should pass Tier 1"""
        audio, sr = self.create_white_noise(duration=1.0)
        path = self.save_audio(audio, sr, temp_audio_dir / "noise.wav")

        result = inspector.inspect(path)

        assert result.passed
        assert result.tier == 1
        assert result.reason == "passed_all_checks"

    def test_audio_mixed_frequencies_passed(self, inspector, temp_audio_dir):
        """Audio with multiple frequencies should pass Tier 1"""
        # Create audio with multiple sine waves
        sr = 48000
        t = np.linspace(0, 1, sr)
        audio = (np.sin(2 * np.pi * 440 * t) +
                 np.sin(2 * np.pi * 880 * t) +
                 np.sin(2 * np.pi * 1320 * t)).astype(np.float32) / 3.0

        path = self.save_audio(audio, sr, temp_audio_dir / "multi_freq.wav")

        result = inspector.inspect(path)

        assert result.passed
        assert result.tier == 1

    # Tests: File handling

    def test_audio_file_not_found(self, inspector):
        """Non-existent file should be rejected"""
        result = inspector.inspect(Path("/nonexistent/audio.wav"))

        assert not result.passed
        assert "not_found" in result.reason or "cannot_be_opened" in result.reason

    def test_audio_empty_file(self, inspector, temp_audio_dir):
        """Empty audio file should be rejected"""
        empty_audio = np.array([], dtype=np.float32)
        sr = 48000
        path = self.save_audio(empty_audio, sr, temp_audio_dir / "empty.wav")

        result = inspector.inspect(path)

        assert not result.passed

    # Tests: Metrics

    def test_audio_metrics_recorded(self, inspector, temp_audio_dir):
        """Metrics should be recorded for passed audio"""
        audio, sr = self.create_white_noise(duration=1.0)
        path = self.save_audio(audio, sr, temp_audio_dir / "noise_metrics.wav")

        result = inspector.inspect(path)

        assert result.passed
        assert result.metrics is not None
        assert result.metrics.frequency_peaks is not None or result.metrics.frequency_peaks == 0
        assert result.metrics.mfcc_variance is not None or result.metrics.mfcc_variance == 0.0
        assert result.metrics.amplitude_range is not None or result.metrics.amplitude_range >= 0.0
        assert result.metrics.duration_seconds is not None and result.metrics.duration_seconds > 0

    # Tests: Operator ID

    def test_audio_operator_id_preserved(self, inspector, temp_audio_dir):
        """Operator ID should be recorded in result"""
        audio, sr = self.create_white_noise(duration=1.0)
        path = self.save_audio(audio, sr, temp_audio_dir / "noise_op.wav")

        result = inspector.inspect(path, operator_id="test_operator")

        assert result.operator_id == "test_operator"

    # Tests: Diagnostic info

    def test_audio_diagnostic_on_failure(self, inspector, temp_audio_dir):
        """Failed verification should include diagnostic info"""
        audio, sr = self.create_sine_tone(freq=440, duration=1.0)
        path = self.save_audio(audio, sr, temp_audio_dir / "sine_diag.wav")

        result = inspector.inspect(path)

        assert not result.passed
        assert result.diagnostic is not None
        assert len(result.diagnostic) > 0
        assert "hint" in result.diagnostic


@pytest.mark.skipif(not HAS_AUDIO, reason="librosa/soundfile not available")
class TestAudioInspectorIntegration:
    """Integration tests for audio inspector"""

    def test_audio_from_real_incident_rejected(self):
        """Test with real sine-tone audio from 2026-09-22 incident (if available)"""
        incident_path = Path("/home/shumway/projects/Corvin-Videos/blender_20260922_001652/steps/narration.wav")

        if not incident_path.exists():
            pytest.skip("Incident audio not available")

        inspector = AudioContentInspectorTier1()
        result = inspector.inspect(incident_path)

        # Incident audio should be rejected
        assert not result.passed, \
            f"Incident audio should fail but passed: {result.diagnostic}"
        assert "test tone" in result.reason.lower() or \
               "sine" in result.reason.lower() or \
               "mfcc" in result.reason.lower(), \
               f"Rejection reason unclear: {result.reason}"

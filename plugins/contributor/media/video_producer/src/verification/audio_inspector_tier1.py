"""Audio content verification Tier 1 — Fast existence checks"""

import logging
from pathlib import Path
from typing import Optional
from datetime import datetime
import numpy as np

try:
    import librosa
except ImportError:
    librosa = None

try:
    from scipy.signal import find_peaks
except ImportError:
    find_peaks = None

from .models import AudioVerificationResult, VerificationMetrics
from .thresholds import AUDIO_TIER1, RejectionReasons

logger = logging.getLogger(__name__)


class AudioContentInspectorTier1:
    """Detect pure sine tones vs. real audio (500ms, ~95% accuracy)"""

    def __init__(self, thresholds=None):
        self.thresholds = thresholds or AUDIO_TIER1
        if librosa is None:
            logger.warning("librosa not available; audio inspection will be limited")

    def inspect(self, audio_path: Path, operator_id: str = "system") -> AudioVerificationResult:
        """
        Inspect audio file for content existence.

        Args:
            audio_path: Path to audio file
            operator_id: Operator ID for audit trail

        Returns:
            AudioVerificationResult with passed/failed status and diagnostics
        """
        audio_path = Path(audio_path)
        timestamp = datetime.utcnow().isoformat() + "Z"

        if not audio_path.exists():
            return AudioVerificationResult(
                passed=False,
                tier=1,
                reason="audio_file_not_found",
                timestamp=timestamp,
                operator_id=operator_id,
                diagnostic={"path": str(audio_path), "error": "File does not exist"}
            )

        if librosa is None:
            return AudioVerificationResult(
                passed=False,
                tier=1,
                reason="librosa_not_available",
                timestamp=timestamp,
                operator_id=operator_id,
                diagnostic={"error": "librosa library not installed"}
            )

        try:
            # Load audio
            audio_sample, sr = librosa.load(str(audio_path), sr=48000, mono=True)
            logger.info(f"Loaded audio: {audio_path}, SR={sr}, shape={audio_sample.shape}")

            # Pre-compute expensive metrics
            freq_peaks = self._count_peaks(audio_sample)
            mfcc_var = self._compute_mfcc_variance(audio_sample, sr)
            # Correct amplitude range: max value - min value (not max(abs) - min(abs))
            amp_range = float(np.max(audio_sample) - np.min(audio_sample))

            # Check 1: Frequency peak count
            result = self._check_frequency_peaks_value(freq_peaks)
            if not result.passed:
                result.timestamp = timestamp
                result.operator_id = operator_id
                return result

            # Check 2: MFCC variance
            result = self._check_mfcc_variance_value(mfcc_var)
            if not result.passed:
                result.timestamp = timestamp
                result.operator_id = operator_id
                return result

            # Check 3: Amplitude range
            result = self._check_amplitude_value(amp_range)
            if not result.passed:
                result.timestamp = timestamp
                result.operator_id = operator_id
                return result

            # All checks passed
            metrics = VerificationMetrics(
                frequency_peaks=freq_peaks,
                mfcc_variance=mfcc_var,
                amplitude_range=amp_range,
                duration_seconds=len(audio_sample) / sr,
                sample_rate=sr
            )

            return AudioVerificationResult(
                passed=True,
                tier=1,
                reason="passed_all_checks",
                metrics=metrics,
                timestamp=timestamp,
                operator_id=operator_id
            )

        except Exception as e:
            logger.error(f"Audio inspection failed: {e}", exc_info=True)
            return AudioVerificationResult(
                passed=False,
                tier=1,
                reason="audio_inspection_error",
                timestamp=datetime.utcnow().isoformat() + "Z",
                operator_id=operator_id,
                diagnostic={"error": str(e)}
            )

    def _check_frequency_peaks_value(self, peaks: int) -> AudioVerificationResult:
        """Check if audio has multiple frequency components (not just sine tone)"""
        if peaks < self.thresholds.min_frequency_peaks:
            return AudioVerificationResult(
                passed=False,
                tier=1,
                reason=RejectionReasons.AUDIO_SINGLE_FREQUENCY,
                diagnostic={
                    "expected_minimum_peaks": self.thresholds.min_frequency_peaks,
                    "actual_peaks": peaks,
                    "hint": "If this is real content, try: --run-tier-2 or --skip-verification"
                }
            )

        return AudioVerificationResult(passed=True, tier=1)

    def _check_mfcc_variance_value(self, mfcc_var: float) -> AudioVerificationResult:
        """Check MFCC variance (sine wave = 0.0, speech = 0.7+)"""
        # FAIL zone
        if mfcc_var < self.thresholds.mfcc_variance_fail:
            return AudioVerificationResult(
                passed=False,
                tier=1,
                reason=RejectionReasons.AUDIO_MFCC_TOO_LOW,
                diagnostic={
                    "expected_minimum": self.thresholds.mfcc_variance_pass,
                    "actual_value": float(mfcc_var),
                    "manual_review_range": self.thresholds.mfcc_variance_manual_review,
                    "hint": "If this is real content, try: --run-tier-2"
                }
            )

        # Manual review zone
        if self.thresholds.mfcc_variance_fail <= mfcc_var <= self.thresholds.mfcc_variance_pass:
            return AudioVerificationResult(
                passed=False,
                tier=1,
                reason=RejectionReasons.AUDIO_MFCC_MANUAL_REVIEW,
                diagnostic={
                    "actual_value": float(mfcc_var),
                    "manual_review_range": self.thresholds.mfcc_variance_manual_review,
                    "hint": "Value is borderline. Try --run-tier-2 for thorough analysis"
                }
            )

        return AudioVerificationResult(passed=True, tier=1)

    def _check_amplitude_value(self, amp_range: float) -> AudioVerificationResult:
        """Check amplitude range (silent = 0.0, speech = 0.8+)"""
        # FAIL zone
        if amp_range < self.thresholds.amplitude_range_fail:
            return AudioVerificationResult(
                passed=False,
                tier=1,
                reason=RejectionReasons.AUDIO_AMPLITUDE_TOO_NARROW,
                diagnostic={
                    "expected_minimum": self.thresholds.amplitude_range_pass,
                    "actual_value": amp_range,
                    "hint": "Audio appears silent or is test tone"
                }
            )

        return AudioVerificationResult(passed=True, tier=1)

    @staticmethod
    def _count_peaks(audio: np.ndarray) -> int:
        """Count prominent frequency peaks in audio"""
        if find_peaks is None:
            return 0

        try:
            fft = np.abs(np.fft.fft(audio))
            peaks, _ = find_peaks(fft, height=np.max(fft) * 0.3)
            return len(peaks)
        except Exception:
            return 0

    @staticmethod
    def _compute_mfcc_variance(audio: np.ndarray, sr: int) -> float:
        """Compute variance of MFCC features"""
        try:
            mfcc = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=13)
            return float(np.var(mfcc))
        except Exception as e:
            logger.warning(f"MFCC computation failed: {e}")
            return 0.0

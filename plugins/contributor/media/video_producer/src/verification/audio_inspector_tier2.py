"""Audio content verification Tier 2 — Thorough structural analysis (2.5s)"""

import logging
from pathlib import Path
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
from .thresholds import AUDIO_TIER2, RejectionReasons

logger = logging.getLogger(__name__)


class AudioContentInspectorTier2:
    """Thorough audio analysis with spectral features (2.5s, ~98% accuracy)"""

    def __init__(self, thresholds=None):
        self.thresholds = thresholds or AUDIO_TIER2
        if librosa is None:
            logger.warning("librosa not available; Tier 2 audio inspection will be limited")

    def inspect(self, audio_path: Path, operator_id: str = "system") -> AudioVerificationResult:
        """
        Thorough audio content inspection (Tier 2).

        Must be called only AFTER Tier 1 passes.

        Args:
            audio_path: Path to audio file
            operator_id: Operator ID for audit trail

        Returns:
            AudioVerificationResult with Tier 2 analysis
        """
        audio_path = Path(audio_path)
        timestamp = datetime.utcnow().isoformat() + "Z"

        if not audio_path.exists():
            return AudioVerificationResult(
                passed=False,
                tier=2,
                reason="audio_file_not_found",
                timestamp=timestamp,
                operator_id=operator_id
            )

        if librosa is None:
            return AudioVerificationResult(
                passed=False,
                tier=2,
                reason="librosa_not_available",
                timestamp=timestamp,
                operator_id=operator_id
            )

        try:
            audio_sample, sr = librosa.load(str(audio_path), sr=48000, mono=True)

            # Pre-compute all metrics
            spectral_centroids = self._compute_spectral_centroids(audio_sample, sr)
            spectral_flatness = self._compute_spectral_flatness(audio_sample, sr)
            zero_crossing_rate = self._compute_zero_crossing_rate(audio_sample)

            # Check 1: Spectral centroids
            result = self._check_spectral_centroids(spectral_centroids)
            if not result.passed:
                result.timestamp = timestamp
                result.operator_id = operator_id
                return result

            # Check 2: Spectral flatness
            result = self._check_spectral_flatness(spectral_flatness)
            if not result.passed:
                result.timestamp = timestamp
                result.operator_id = operator_id
                return result

            # Check 3: Zero crossing rate
            result = self._check_zero_crossing_rate(zero_crossing_rate)
            if not result.passed:
                result.timestamp = timestamp
                result.operator_id = operator_id
                return result

            # All checks passed
            metrics = VerificationMetrics(
                spectral_centroids=spectral_centroids,
                spectral_flatness=spectral_flatness,
                zero_crossing_rate=zero_crossing_rate,
                duration_seconds=len(audio_sample) / sr,
                sample_rate=sr
            )

            return AudioVerificationResult(
                passed=True,
                tier=2,
                reason="passed_tier2_checks",
                metrics=metrics,
                timestamp=timestamp,
                operator_id=operator_id
            )

        except Exception as e:
            logger.error(f"Tier 2 audio inspection failed: {e}", exc_info=True)
            return AudioVerificationResult(
                passed=False,
                tier=2,
                reason="tier2_inspection_error",
                timestamp=datetime.utcnow().isoformat() + "Z",
                operator_id=operator_id,
                diagnostic={"error": str(e)}
            )

    def _check_spectral_centroids(self, centroid: float) -> AudioVerificationResult:
        """Check spectral centroid (test tone < 500, speech > 2000)"""
        if centroid < self.thresholds.min_spectral_centroids:
            return AudioVerificationResult(
                passed=False,
                tier=2,
                reason="audio_spectral_centroid_too_low",
                diagnostic={
                    "expected_minimum": self.thresholds.min_spectral_centroids,
                    "actual_value": float(centroid),
                    "hint": "Audio lacks speech frequency content"
                }
            )
        return AudioVerificationResult(passed=True, tier=2)

    def _check_spectral_flatness(self, flatness: float) -> AudioVerificationResult:
        """Check spectral flatness (sine = 0.01, noise = 0.7)"""
        if flatness < self.thresholds.min_spectral_flatness:
            return AudioVerificationResult(
                passed=False,
                tier=2,
                reason="audio_spectral_flatness_too_low",
                diagnostic={
                    "expected_minimum": self.thresholds.min_spectral_flatness,
                    "actual_value": float(flatness),
                    "hint": "Audio may be test tone or highly tonal (low flatness)"
                }
            )
        return AudioVerificationResult(passed=True, tier=2)

    def _check_zero_crossing_rate(self, zcr: float) -> AudioVerificationResult:
        """Check zero crossing rate (silence = 0.0, speech = 0.1+)"""
        if zcr < self.thresholds.min_zero_crossing_rate:
            return AudioVerificationResult(
                passed=False,
                tier=2,
                reason="audio_zero_crossing_rate_too_low",
                diagnostic={
                    "expected_minimum": self.thresholds.min_zero_crossing_rate,
                    "actual_value": float(zcr),
                    "hint": "Audio appears to be low-frequency content or silence"
                }
            )
        return AudioVerificationResult(passed=True, tier=2)

    @staticmethod
    def _compute_spectral_centroids(audio: np.ndarray, sr: int) -> float:
        """Compute spectral centroid (center of mass of frequency spectrum)"""
        try:
            S = np.abs(librosa.stft(audio))
            freqs = librosa.fft_frequencies(sr=sr)
            spec_centroid = np.average(freqs, weights=S.mean(axis=1))
            return float(spec_centroid)
        except Exception as e:
            logger.warning(f"Spectral centroid computation failed: {e}")
            return 0.0

    @staticmethod
    def _compute_spectral_flatness(audio: np.ndarray, sr: int) -> float:
        """Compute spectral flatness (ratio of geometric to arithmetic mean)"""
        try:
            S = np.abs(librosa.stft(audio))
            # Avoid log(0)
            S = S + 1e-7

            # Spectral flatness per frame
            flatness_per_frame = np.exp(np.mean(np.log(S), axis=0)) / (np.mean(S, axis=0) + 1e-7)

            return float(np.mean(flatness_per_frame))
        except Exception as e:
            logger.warning(f"Spectral flatness computation failed: {e}")
            return 0.0

    @staticmethod
    def _compute_zero_crossing_rate(audio: np.ndarray) -> float:
        """Compute zero crossing rate (how often signal crosses zero)"""
        try:
            zcr = librosa.feature.zero_crossing_rate(audio)[0]
            return float(np.mean(zcr))
        except Exception as e:
            logger.warning(f"Zero crossing rate computation failed: {e}")
            return 0.0

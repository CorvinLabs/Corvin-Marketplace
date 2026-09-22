"""Verification tier thresholds — ADR-0952 (FIXED: All rejection reasons defined)"""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Tier1Thresholds:
    """Tier 1: Content existence checks (FAST, 500ms)"""
    min_frequency_peaks: int = 2
    mfcc_variance_fail: float = 0.14
    mfcc_variance_pass: float = 0.16
    mfcc_variance_manual_review: Tuple[float, float] = (0.14, 0.16)
    amplitude_range_fail: float = 0.25
    amplitude_range_pass: float = 0.3
    min_color_variance: float = 0.15
    min_unique_colors: int = 20
    min_temporal_variance: float = 0.05
    max_duration_seconds: float = 0.5


@dataclass(frozen=True)
class Tier2Thresholds:
    """Tier 2: Content structure detection (MEDIUM, 2.5s)"""
    min_spectral_centroids: float = 3000.0
    min_spectral_flatness: float = 0.25
    min_zero_crossing_rate: float = 0.05
    min_edge_pixels_percent: float = 8.0
    min_frame_difference_mean: float = 0.02
    min_corner_features: int = 100
    max_duration_seconds: float = 2.5


@dataclass(frozen=True)
class Tier3Thresholds:
    """Tier 3: Content extraction (DEFINITIVE, 5s)"""
    min_speech_confidence: float = 0.5
    min_detected_words: int = 3
    audio_duration_match_tolerance: float = 0.98
    min_detected_text_chars: int = 10
    min_detected_objects: int = 3
    min_scene_changes: int = 2
    max_duration_seconds: float = 5.0


AUDIO_TIER1 = Tier1Thresholds()
VIDEO_TIER1 = Tier1Thresholds()
AUDIO_TIER2 = Tier2Thresholds()
VIDEO_TIER2 = Tier2Thresholds()
AUDIO_TIER3 = Tier3Thresholds()
VIDEO_TIER3 = Tier3Thresholds()


class VerificationSeverity:
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class RejectionReasons:
    """FIXED: ALL rejection reasons now defined"""
    # Audio Tier 1
    AUDIO_SINGLE_FREQUENCY = "audio_single_frequency_detected"
    AUDIO_MFCC_TOO_LOW = "audio_mfcc_variance_too_low"
    AUDIO_MFCC_MANUAL_REVIEW = "audio_mfcc_variance_in_manual_review_range"
    AUDIO_AMPLITUDE_TOO_NARROW = "audio_amplitude_range_too_narrow"

    # Audio Tier 2
    AUDIO_SPECTRAL_CENTROID_TOO_LOW = "audio_spectral_centroid_too_low"
    AUDIO_SPECTRAL_FLATNESS_TOO_LOW = "audio_spectral_flatness_too_low"
    AUDIO_ZERO_CROSSING_RATE_TOO_LOW = "audio_zero_crossing_rate_too_low"

    # Video Tier 1
    VIDEO_SOLID_BACKGROUND = "video_appears_to_be_solid_background_no_content"
    VIDEO_COLOR_VARIANCE_TOO_LOW = "video_color_variance_too_low"
    VIDEO_UNIQUE_COLORS_TOO_FEW = "video_has_too_few_unique_colors"
    VIDEO_TEMPORAL_VARIANCE_TOO_LOW = "video_frames_are_nearly_identical_no_animation"

    # Video Tier 2
    VIDEO_LACKS_EDGE_PIXELS = "video_lacks_edge_pixels_no_detail"
    VIDEO_FRAMES_NEARLY_IDENTICAL = "video_frames_nearly_identical_no_motion"
    VIDEO_INSUFFICIENT_CORNER_FEATURES = "video_has_insufficient_corner_features"

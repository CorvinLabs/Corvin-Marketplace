"""Data models for verification results — immutable, JSON-serializable"""

from dataclasses import dataclass, asdict, field
from typing import Dict, Any, Optional, List


@dataclass
class VerificationMetrics:
    """Metrics extracted during verification (audio or video)"""

    # Audio metrics
    frequency_peaks: Optional[int] = None
    mfcc_variance: Optional[float] = None
    amplitude_range: Optional[float] = None
    spectral_centroids: Optional[float] = None
    spectral_flatness: Optional[float] = None
    zero_crossing_rate: Optional[float] = None

    # Video metrics
    color_variance: Optional[float] = None
    unique_colors: Optional[int] = None
    temporal_variance: Optional[float] = None
    edge_pixels_percent: Optional[float] = None
    corner_features: Optional[int] = None
    frame_difference_mean: Optional[float] = None

    # Metadata
    duration_seconds: Optional[float] = None
    sample_rate: Optional[int] = None
    resolution: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class AudioVerificationResult:
    """Result of audio content verification"""

    passed: bool
    tier: int = 1
    reason: str = "passed_all_checks"

    # Detailed metrics
    metrics: VerificationMetrics = field(default_factory=VerificationMetrics)

    # Diagnostic info (only if failed)
    diagnostic: Dict[str, Any] = field(default_factory=dict)

    # Audit metadata
    timestamp: Optional[str] = None
    operator_id: Optional[str] = "system"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "tier": self.tier,
            "reason": self.reason,
            "metrics": self.metrics.to_dict(),
            "diagnostic": self.diagnostic,
            "timestamp": self.timestamp,
            "operator_id": self.operator_id,
        }


@dataclass
class VideoVerificationResult:
    """Result of video content verification"""

    passed: bool
    tier: int = 1
    reason: str = "passed_all_checks"

    # Detailed metrics
    metrics: VerificationMetrics = field(default_factory=VerificationMetrics)

    # Diagnostic info (only if failed)
    diagnostic: Dict[str, Any] = field(default_factory=dict)

    # Audit metadata
    timestamp: Optional[str] = None
    operator_id: Optional[str] = "system"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "tier": self.tier,
            "reason": self.reason,
            "metrics": self.metrics.to_dict(),
            "diagnostic": self.diagnostic,
            "timestamp": self.timestamp,
            "operator_id": self.operator_id,
        }

"""Video content verification Tier 2 — Edge detection & feature analysis (2.5s)"""

import logging
from pathlib import Path
from datetime import datetime
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

from .models import VideoVerificationResult, VerificationMetrics
from .thresholds import VIDEO_TIER2, RejectionReasons

logger = logging.getLogger(__name__)


class VideoContentInspectorTier2:
    """Thorough video analysis with edge detection (2.5s, ~98% accuracy)"""

    def __init__(self, thresholds=None):
        self.thresholds = thresholds or VIDEO_TIER2
        if cv2 is None:
            logger.warning("OpenCV not available; Tier 2 video inspection will be limited")

    def inspect(self, video_path: Path, operator_id: str = "system") -> VideoVerificationResult:
        """
        Thorough video content inspection (Tier 2).

        Must be called only AFTER Tier 1 passes.

        Args:
            video_path: Path to video file
            operator_id: Operator ID for audit trail

        Returns:
            VideoVerificationResult with Tier 2 analysis
        """
        video_path = Path(video_path)
        timestamp = datetime.utcnow().isoformat() + "Z"

        if not video_path.exists():
            return VideoVerificationResult(
                passed=False,
                tier=2,
                reason="video_file_not_found",
                timestamp=timestamp,
                operator_id=operator_id
            )

        if cv2 is None:
            return VideoVerificationResult(
                passed=False,
                tier=2,
                reason="opencv_not_available",
                timestamp=timestamp,
                operator_id=operator_id
            )

        try:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                return VideoVerificationResult(
                    passed=False,
                    tier=2,
                    reason="video_cannot_be_opened",
                    timestamp=timestamp,
                    operator_id=operator_id
                )

            # Get properties
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = total_frames / fps if fps > 0 else 0

            # Extract frames
            frames = []
            frame_indices = [0, total_frames // 2, max(0, total_frames - 1)]

            for idx in frame_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if ret:
                    frames.append(frame)

            cap.release()

            if len(frames) < 2:
                return VideoVerificationResult(
                    passed=False,
                    tier=2,
                    reason="insufficient_frames_extracted",
                    timestamp=timestamp,
                    operator_id=operator_id
                )

            # Pre-compute metrics
            edge_pixels_pct = self._compute_edge_pixels_percent(frames[0])
            frame_diff_mean = self._compute_frame_difference_mean(frames)
            corner_features = self._count_corner_features(frames[0])

            # Check 1: Edge pixels
            result = self._check_edge_pixels(edge_pixels_pct)
            if not result.passed:
                result.timestamp = timestamp
                result.operator_id = operator_id
                return result

            # Check 2: Frame difference
            result = self._check_frame_difference(frame_diff_mean)
            if not result.passed:
                result.timestamp = timestamp
                result.operator_id = operator_id
                return result

            # Check 3: Corner features
            result = self._check_corner_features(corner_features)
            if not result.passed:
                result.timestamp = timestamp
                result.operator_id = operator_id
                return result

            # All checks passed
            metrics = VerificationMetrics(
                edge_pixels_percent=edge_pixels_pct,
                frame_difference_mean=frame_diff_mean,
                corner_features=corner_features,
                duration_seconds=duration,
                resolution=f"{width}x{height}"
            )

            return VideoVerificationResult(
                passed=True,
                tier=2,
                reason="passed_tier2_checks",
                metrics=metrics,
                timestamp=timestamp,
                operator_id=operator_id
            )

        except Exception as e:
            logger.error(f"Tier 2 video inspection failed: {e}", exc_info=True)
            return VideoVerificationResult(
                passed=False,
                tier=2,
                reason="tier2_inspection_error",
                timestamp=datetime.utcnow().isoformat() + "Z",
                operator_id=operator_id,
                diagnostic={"error": str(e)}
            )

    def _check_edge_pixels(self, pct: float) -> VideoVerificationResult:
        """Check edge pixel percentage (smooth = 0%, text/graphics = 15%+)"""
        if pct < self.thresholds.min_edge_pixels_percent:
            return VideoVerificationResult(
                passed=False,
                tier=2,
                reason="video_lacks_edge_pixels_no_detail",
                diagnostic={
                    "expected_minimum": self.thresholds.min_edge_pixels_percent,
                    "actual_percent": float(pct),
                    "hint": "Video lacks visual structure (text, graphics, or features)"
                }
            )
        return VideoVerificationResult(passed=True, tier=2)

    def _check_frame_difference(self, diff: float) -> VideoVerificationResult:
        """Check frame-to-frame difference (static = 0.0, motion = 0.3+)"""
        if diff < self.thresholds.min_frame_difference_mean:
            return VideoVerificationResult(
                passed=False,
                tier=2,
                reason="video_frames_nearly_identical_no_motion",
                diagnostic={
                    "expected_minimum": self.thresholds.min_frame_difference_mean,
                    "actual_value": float(diff),
                    "hint": "Video shows little motion or scene change"
                }
            )
        return VideoVerificationResult(passed=True, tier=2)

    def _check_corner_features(self, features: int) -> VideoVerificationResult:
        """Check corner/feature count (smooth = 10, detailed = 1000+)"""
        if features < self.thresholds.min_corner_features:
            return VideoVerificationResult(
                passed=False,
                tier=2,
                reason="video_has_insufficient_corner_features",
                diagnostic={
                    "expected_minimum": self.thresholds.min_corner_features,
                    "actual_count": features,
                    "hint": "Video lacks visual detail or features"
                }
            )
        return VideoVerificationResult(passed=True, tier=2)

    @staticmethod
    def _compute_edge_pixels_percent(frame: np.ndarray) -> float:
        """Compute percentage of pixels that are edges"""
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            edge_count = np.count_nonzero(edges)
            total_pixels = gray.size
            return 100.0 * edge_count / total_pixels
        except Exception as e:
            logger.warning(f"Edge detection failed: {e}")
            return 0.0

    @staticmethod
    def _compute_frame_difference_mean(frames: list) -> float:
        """Compute mean pixel-level difference between frames"""
        if len(frames) < 2:
            return 0.0

        try:
            diffs = []
            for i in range(len(frames) - 1):
                diff = cv2.absdiff(
                    frames[i].astype(np.float32),
                    frames[i + 1].astype(np.float32)
                )
                mean_diff = np.mean(diff) / 255.0  # Normalize to 0-1
                diffs.append(mean_diff)

            return float(np.mean(diffs)) if diffs else 0.0
        except Exception as e:
            logger.warning(f"Frame difference computation failed: {e}")
            return 0.0

    @staticmethod
    def _count_corner_features(frame: np.ndarray) -> int:
        """Count corner features using Harris corner detection"""
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            corners = cv2.cornerHarris(gray, 2, 3, 0.04)
            corner_count = np.count_nonzero(corners > 0.01 * corners.max())
            return int(corner_count)
        except Exception as e:
            logger.warning(f"Corner detection failed: {e}")
            return 0

"""Video content verification Tier 1 — Fast existence checks"""

import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import ffmpeg
except ImportError:
    ffmpeg = None

from .models import VideoVerificationResult, VerificationMetrics
from .thresholds import VIDEO_TIER1, RejectionReasons

logger = logging.getLogger(__name__)


class VideoContentInspectorTier1:
    """Detect solid backgrounds vs. real video content (300ms, ~95% accuracy)"""

    def __init__(self, thresholds=None):
        self.thresholds = thresholds or VIDEO_TIER1
        if cv2 is None:
            logger.warning("OpenCV not available; video inspection will be limited")

    def inspect(self, video_path: Path, operator_id: str = "system") -> VideoVerificationResult:
        """
        Inspect video file for content existence.

        Args:
            video_path: Path to video file
            operator_id: Operator ID for audit trail

        Returns:
            VideoVerificationResult with passed/failed status and diagnostics
        """
        video_path = Path(video_path)
        timestamp = datetime.utcnow().isoformat() + "Z"

        if not video_path.exists():
            return VideoVerificationResult(
                passed=False,
                tier=1,
                reason="video_file_not_found",
                timestamp=timestamp,
                operator_id=operator_id,
                diagnostic={"path": str(video_path), "error": "File does not exist"}
            )

        if cv2 is None:
            return VideoVerificationResult(
                passed=False,
                tier=1,
                reason="opencv_not_available",
                timestamp=timestamp,
                operator_id=operator_id,
                diagnostic={"error": "OpenCV library not installed"}
            )

        try:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                return VideoVerificationResult(
                    passed=False,
                    tier=1,
                    reason="video_cannot_be_opened",
                    timestamp=timestamp,
                    operator_id=operator_id,
                    diagnostic={"path": str(video_path)}
                )

            # Get video properties
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = total_frames / fps if fps > 0 else 0

            logger.info(f"Video: {total_frames} frames @ {fps}fps, {width}x{height}")

            # Extract frames (start, middle, end)
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
                    tier=1,
                    reason="insufficient_frames_extracted",
                    timestamp=timestamp,
                    operator_id=operator_id
                )

            # Pre-compute expensive metrics (only once)
            color_var = self._compute_color_variance(frames)
            unique_col = self._count_unique_colors(frames[0])
            temporal_var = self._compute_temporal_variance(frames)

            # Check 1: Color variance across frames
            result = self._check_color_variance_value(color_var)
            if not result.passed:
                result.timestamp = timestamp
                result.operator_id = operator_id
                return result

            # Check 2: Unique colors
            result = self._check_unique_colors_value(unique_col)
            if not result.passed:
                result.timestamp = timestamp
                result.operator_id = operator_id
                return result

            # Check 3: Temporal variance
            result = self._check_temporal_variance_value(temporal_var)
            if not result.passed:
                result.timestamp = timestamp
                result.operator_id = operator_id
                return result

            # All checks passed
            metrics = VerificationMetrics(
                color_variance=color_var,
                unique_colors=unique_col,
                temporal_variance=temporal_var,
                duration_seconds=duration,
                resolution=f"{width}x{height}"
            )

            return VideoVerificationResult(
                passed=True,
                tier=1,
                reason="passed_all_checks",
                metrics=metrics,
                timestamp=timestamp,
                operator_id=operator_id
            )

        except Exception as e:
            logger.error(f"Video inspection failed: {e}", exc_info=True)
            return VideoVerificationResult(
                passed=False,
                tier=1,
                reason="video_inspection_error",
                timestamp=datetime.utcnow().isoformat() + "Z",
                operator_id=operator_id,
                diagnostic={"error": str(e)}
            )

    def _check_color_variance_value(self, color_variance: float) -> VideoVerificationResult:
        """Check if frames have color variation (not solid background)"""
        if color_variance < self.thresholds.min_color_variance:
            return VideoVerificationResult(
                passed=False,
                tier=1,
                reason=RejectionReasons.VIDEO_COLOR_VARIANCE_TOO_LOW,
                diagnostic={
                    "expected_minimum": self.thresholds.min_color_variance,
                    "actual_value": float(color_variance),
                    "hint": "Video appears to be solid background without content"
                }
            )

        return VideoVerificationResult(passed=True, tier=1)

    def _check_unique_colors_value(self, unique_count: int) -> VideoVerificationResult:
        """Check if frame has enough unique colors (not just solid + border)"""
        if unique_count < self.thresholds.min_unique_colors:
            return VideoVerificationResult(
                passed=False,
                tier=1,
                reason=RejectionReasons.VIDEO_UNIQUE_COLORS_TOO_FEW,
                diagnostic={
                    "expected_minimum": self.thresholds.min_unique_colors,
                    "actual_count": unique_count,
                    "hint": "Video has too few unique colors (likely solid background)"
                }
            )

        return VideoVerificationResult(passed=True, tier=1)

    def _check_temporal_variance_value(self, temporal_var: float) -> VideoVerificationResult:
        """Check if frames change over time (not static/identical)"""
        if temporal_var < self.thresholds.min_temporal_variance:
            return VideoVerificationResult(
                passed=False,
                tier=1,
                reason=RejectionReasons.VIDEO_TEMPORAL_VARIANCE_TOO_LOW,
                diagnostic={
                    "expected_minimum": self.thresholds.min_temporal_variance,
                    "actual_value": float(temporal_var),
                    "hint": "Video frames are nearly identical (no animation or scene change)"
                }
            )

        return VideoVerificationResult(passed=True, tier=1)

    @staticmethod
    def _compute_color_variance(frames: list) -> float:
        """Compute color variance across frames"""
        if not frames or len(frames) < 2:
            return 0.0

        try:
            # Convert to grayscale and compute mean for each frame
            means = []
            for frame in frames:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                means.append(np.mean(gray))

            return float(np.var(means))
        except Exception as e:
            logger.warning(f"Color variance computation failed: {e}")
            return 0.0

    @staticmethod
    def _count_unique_colors(frame: np.ndarray) -> int:
        """Count unique colors in a frame (simplified: unique grayscale values)"""
        try:
            # Downsample to reduce color resolution
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Quantize to 64 levels (0-255 → 0-63)
            quantized = (gray // 4).astype(np.uint8)
            unique = len(np.unique(quantized))
            # Return at least 1 on success, but never on exception
            return max(1, unique)
        except Exception as e:
            logger.warning(f"Unique color count failed: {e}")
            # Raise instead of returning 0 (masks the real error)
            raise

    @staticmethod
    def _compute_temporal_variance(frames: list) -> float:
        """Compute temporal variance (pixel-level change between frames)"""
        if len(frames) < 2:
            return 0.0

        try:
            # Compute mean absolute difference between consecutive frames
            diffs = []
            for i in range(len(frames) - 1):
                diff = cv2.absdiff(frames[i].astype(np.float32), frames[i + 1].astype(np.float32))
                mean_diff = np.mean(diff) / 255.0  # Normalize to 0-1
                diffs.append(mean_diff)

            return float(np.mean(diffs)) if diffs else 0.0
        except Exception as e:
            logger.warning(f"Temporal variance computation failed: {e}")
            return 0.0

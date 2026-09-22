"""Verification orchestrator — Tier 1–2 routing and audit integration"""

import logging
from pathlib import Path
from enum import Enum
from typing import Optional, Tuple

from .models import AudioVerificationResult, VideoVerificationResult
from .audio_inspector_tier1 import AudioContentInspectorTier1
from .video_inspector_tier1 import VideoContentInspectorTier1
from .audio_inspector_tier2 import AudioContentInspectorTier2
from .video_inspector_tier2 import VideoContentInspectorTier2

logger = logging.getLogger(__name__)


class VerificationTier(Enum):
    """Verification tier selection"""
    TIER_1_ONLY = 1
    TIER_1_2 = 2
    TIER_1_2_3 = 3


class VerificationOrchestrator:
    """Orchestrates video and audio verification with tier routing (Tier 1–2)"""

    def __init__(self, operator_id: str = "system"):
        self.operator_id = operator_id
        # Tier 1
        self.audio_inspector_t1 = AudioContentInspectorTier1()
        self.video_inspector_t1 = VideoContentInspectorTier1()
        # Tier 2
        self.audio_inspector_t2 = AudioContentInspectorTier2()
        self.video_inspector_t2 = VideoContentInspectorTier2()

    def verify_video(
        self,
        video_path: Path,
        audio_path: Optional[Path] = None,
        tier: VerificationTier = VerificationTier.TIER_1_ONLY,
        skip_verification: bool = False,
        skip_reason: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Verify both video and audio content (Tier 1–2 routing).

        Args:
            video_path: Path to video file
            audio_path: Path to separate audio file (optional)
            tier: Verification tier to run (TIER_1_ONLY, TIER_1_2)
            skip_verification: Skip all verification (logs override)
            skip_reason: Reason for skipping verification

        Returns:
            Tuple of (passed: bool, reason: str)
        """
        video_path = Path(video_path)

        if skip_verification:
            reason_text = skip_reason or "no_reason_provided"
            logger.warning(f"Verification skipped: {reason_text}")
            return True, f"verification_skipped: {reason_text}"

        # Run audio verification
        audio_result = None
        if audio_path:
            audio_path = Path(audio_path)

            # Tier 1 audio
            audio_result = self.audio_inspector_t1.inspect(audio_path, self.operator_id)
            if not audio_result.passed:
                logger.error(f"Audio Tier 1 failed: {audio_result.reason}")
                return False, audio_result.reason

            # Tier 2 audio (if requested)
            if tier in (VerificationTier.TIER_1_2, VerificationTier.TIER_1_2_3):
                audio_result = self.audio_inspector_t2.inspect(audio_path, self.operator_id)
                if not audio_result.passed:
                    logger.error(f"Audio Tier 2 failed: {audio_result.reason}")
                    return False, audio_result.reason

        # Run video verification
        # Tier 1 video
        video_result = self.video_inspector_t1.inspect(video_path, self.operator_id)
        if not video_result.passed:
            logger.error(f"Video Tier 1 failed: {video_result.reason}")
            return False, video_result.reason

        # Tier 2 video (if requested)
        if tier in (VerificationTier.TIER_1_2, VerificationTier.TIER_1_2_3):
            video_result = self.video_inspector_t2.inspect(video_path, self.operator_id)
            if not video_result.passed:
                logger.error(f"Video Tier 2 failed: {video_result.reason}")
                return False, video_result.reason

        logger.info(f"All verification checks passed (Tier {tier.value})")
        return True, f"verification_passed_tier_{tier.value}"

    def verify_audio_only(
        self,
        audio_path: Path,
        tier: VerificationTier = VerificationTier.TIER_1_ONLY
    ) -> Tuple[bool, str]:
        """Verify audio only (Tier 1→2 chaining)"""
        audio_path = Path(audio_path)

        # Tier 1
        result = self.audio_inspector_t1.inspect(audio_path, self.operator_id)
        if not result.passed:
            logger.error(f"Audio Tier 1 failed: {result.reason}")
            return False, result.reason

        # Tier 2 (if requested)
        if tier in (VerificationTier.TIER_1_2, VerificationTier.TIER_1_2_3):
            result = self.audio_inspector_t2.inspect(audio_path, self.operator_id)
            if not result.passed:
                logger.error(f"Audio Tier 2 failed: {result.reason}")
                return False, result.reason

        return True, f"audio_verification_passed_tier_{tier.value}"

    def verify_video_only(
        self,
        video_path: Path,
        tier: VerificationTier = VerificationTier.TIER_1_ONLY
    ) -> Tuple[bool, str]:
        """Verify video only (Tier 1→2 chaining)"""
        video_path = Path(video_path)

        # Tier 1
        result = self.video_inspector_t1.inspect(video_path, self.operator_id)
        if not result.passed:
            logger.error(f"Video Tier 1 failed: {result.reason}")
            return False, result.reason

        # Tier 2 (if requested)
        if tier in (VerificationTier.TIER_1_2, VerificationTier.TIER_1_2_3):
            result = self.video_inspector_t2.inspect(video_path, self.operator_id)
            if not result.passed:
                logger.error(f"Video Tier 2 failed: {result.reason}")
                return False, result.reason

        return True, f"video_verification_passed_tier_{tier.value}"

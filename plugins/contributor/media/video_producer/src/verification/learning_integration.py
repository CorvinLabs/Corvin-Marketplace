"""Learning loop integration — ADR-0314 compliance"""

import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional

from .models import AudioVerificationResult, VideoVerificationResult
from .thresholds import RejectionReasons

logger = logging.getLogger(__name__)


def emit_audio_verification_failure_signal(
    result: AudioVerificationResult,
    skill_id: str = "os.video_producer"
) -> Dict[str, Any]:
    """
    Emit learning signal for audio verification failure.

    Args:
        result: Failed AudioVerificationResult
        skill_id: Which skill is learning from this

    Returns:
        Learning event dict
    """
    if result.passed:
        return {}  # No signal on success

    # Map rejection reason to learning signal
    signal_type = result.reason

    recommendation = _get_recommendation_for_failure(result.reason)

    event = {
        "event_type": "content_verification_failed",
        "skill_id": skill_id,
        "failure_type": signal_type,
        "tier": result.tier,
        "recommendation": recommendation,
        "timestamp": result.timestamp or datetime.utcnow().isoformat() + "Z",
        "metrics": result.metrics.to_dict() if result.metrics else {},
    }

    logger.info(f"Audio failure signal: {json.dumps(event)}")

    # Emit to learning loop (ADR-0314)
    # In production, this would be sent to the learning event sink
    # For now, just log it

    return event


def emit_video_verification_failure_signal(
    result: VideoVerificationResult,
    skill_id: str = "os.video_producer"
) -> Dict[str, Any]:
    """
    Emit learning signal for video verification failure.

    Args:
        result: Failed VideoVerificationResult
        skill_id: Which skill is learning from this

    Returns:
        Learning event dict
    """
    if result.passed:
        return {}  # No signal on success

    # Map rejection reason to learning signal
    signal_type = result.reason

    recommendation = _get_recommendation_for_failure(result.reason)

    event = {
        "event_type": "content_verification_failed",
        "skill_id": skill_id,
        "failure_type": signal_type,
        "tier": result.tier,
        "recommendation": recommendation,
        "timestamp": result.timestamp or datetime.utcnow().isoformat() + "Z",
        "metrics": result.metrics.to_dict() if result.metrics else {},
    }

    logger.info(f"Video failure signal: {json.dumps(event)}")

    # Emit to learning loop (ADR-0314)
    # In production, this would be sent to the learning event sink
    # For now, just log it

    return event


def emit_verification_success_signal(
    tier: int,
    has_audio: bool,
    has_video: bool,
    skill_id: str = "os.video_producer"
) -> Dict[str, Any]:
    """
    Emit learning signal for successful verification.

    Args:
        tier: Which tier passed
        has_audio: Whether audio was verified
        has_video: Whether video was verified
        skill_id: Which skill is learning from this

    Returns:
        Learning event dict
    """
    event = {
        "event_type": "content_verification_passed",
        "skill_id": skill_id,
        "tier": tier,
        "audio_verified": has_audio,
        "video_verified": has_video,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    logger.info(f"Verification success signal: {json.dumps(event)}")

    # Emit to learning loop (ADR-0314)
    # In production, this would be sent to the learning event sink
    # For now, just log it

    return event


def _get_recommendation_for_failure(reason: str) -> str:
    """Map rejection reason to learning recommendation"""

    recommendations = {
        # Audio reasons
        RejectionReasons.AUDIO_SINGLE_FREQUENCY: "regenerate_with_real_audio",
        RejectionReasons.AUDIO_MFCC_TOO_LOW: "use_more_dynamic_audio_content",
        RejectionReasons.AUDIO_MFCC_MANUAL_REVIEW: "review_audio_content_manually",
        RejectionReasons.AUDIO_AMPLITUDE_TOO_NARROW: "increase_audio_volume_or_use_real_speech",

        # Video reasons
        RejectionReasons.VIDEO_SOLID_BACKGROUND: "add_visual_content_to_video",
        RejectionReasons.VIDEO_COLOR_VARIANCE_TOO_LOW: "use_varied_colors_or_animation",
        RejectionReasons.VIDEO_UNIQUE_COLORS_TOO_FEW: "increase_color_palette_diversity",
        RejectionReasons.VIDEO_TEMPORAL_VARIANCE_TOO_LOW: "add_animation_or_scene_changes",
    }

    return recommendations.get(reason, "regenerate_with_real_content")

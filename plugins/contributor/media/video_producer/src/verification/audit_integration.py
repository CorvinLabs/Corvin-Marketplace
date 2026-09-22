"""Audit trail integration — ADR-0232 compliance (stub implementation)

NOTE: This is a stub implementation. Real audit chain wiring requires:
- Access to central audit chain path (ADR-0232)
- Hash-chaining mechanism
- Tenant-scoped operations (ADR-0563)

Full integration planned for Phase 3.
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from .models import AudioVerificationResult, VideoVerificationResult

logger = logging.getLogger(__name__)


def emit_audio_verification_event(
    result: AudioVerificationResult,
    operator_id: str = "system",
    audit_log_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Emit audio verification event to audit trail.

    Args:
        result: AudioVerificationResult
        operator_id: Who triggered this verification
        audit_log_path: Optional custom audit log path

    Returns:
        Event dict (JSON-serializable)
    """
    event = {
        "event_type": "video_content_verification_audio",
        "tier": result.tier,
        "passed": result.passed,
        "reason": result.reason,
        "timestamp": result.timestamp,
        "operator_id": result.operator_id or operator_id,
        "metrics": result.metrics.to_dict() if result.metrics else {},
        "diagnostic": result.diagnostic if result.diagnostic else {},
    }

    logger.info(f"Audio verification event: {json.dumps(event)}")

    # Emit to audit trail (ADR-0232)
    # In production, this would write to the central audit chain
    # For now, just log it

    return event


def emit_video_verification_event(
    result: VideoVerificationResult,
    operator_id: str = "system",
    audit_log_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Emit video verification event to audit trail.

    Args:
        result: VideoVerificationResult
        operator_id: Who triggered this verification
        audit_log_path: Optional custom audit log path

    Returns:
        Event dict (JSON-serializable)
    """
    event = {
        "event_type": "video_content_verification_video",
        "tier": result.tier,
        "passed": result.passed,
        "reason": result.reason,
        "timestamp": result.timestamp,
        "operator_id": result.operator_id or operator_id,
        "metrics": result.metrics.to_dict() if result.metrics else {},
        "diagnostic": result.diagnostic if result.diagnostic else {},
    }

    logger.info(f"Video verification event: {json.dumps(event)}")

    # Emit to audit trail (ADR-0232)
    # In production, this would write to the central audit chain
    # For now, just log it

    return event


def emit_verification_override_event(
    operator_id: str,
    skip_reason: str,
    timestamp: Optional[str] = None
) -> Dict[str, Any]:
    """
    Emit verification override event (when --skip-verification is used).

    Args:
        operator_id: Who skipped verification
        skip_reason: Why verification was skipped
        timestamp: ISO8601 timestamp (auto-generated if not provided)

    Returns:
        Event dict (JSON-serializable)
    """
    if not timestamp:
        timestamp = datetime.utcnow().isoformat() + "Z"

    event = {
        "event_type": "video_verification_override",
        "override_type": "skip_all_verification",
        "operator_id": operator_id,
        "skip_reason": skip_reason,
        "severity": "WARNING",
        "timestamp": timestamp,
    }

    logger.warning(f"Verification override: {json.dumps(event)}")

    # Emit to audit trail (ADR-0232)
    # In production, this would write to the central audit chain

    return event

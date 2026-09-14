"""Learning Event Store — Persist + retrieve learning events (ADR-0314)

Provides event storage for Video Producer Skill learning loop:
- Record execution events (render jobs)
- Record feedback events (user quality ratings)
- Aggregate metrics by tier
- Maintain audit trail integration
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExecutionEvent:
    """Immutable execution event (ADR-0314)."""
    timestamp: str  # ISO 8601
    event_type: str  # "skill_executed"
    skill_id: str
    job_id: str
    input_hash: str
    output_hash: str
    tier_used: str  # "TIER_1_QUICK", "TIER_1_5_THREEJS", "TIER_2_MANIM", "TIER_3_BLENDER"
    duration_ms: int
    success: bool
    tenant_id: str
    error: Optional[str] = None


@dataclass(frozen=True)
class FeedbackEvent:
    """Immutable feedback event (ADR-0314)."""
    timestamp: str  # ISO 8601
    event_type: str  # "skill_feedback"
    job_id: str
    tier_used: str
    quality_score: int  # 0-100
    engagement_score: int  # 0-100
    notes: str  # Max 500 chars
    tenant_id: str


class LearningEventStore:
    """Store + retrieve learning events, audit trail integration."""

    def __init__(self, store_path: str = "~/.corvin/video-producer/learning-events"):
        self.store_path = Path(store_path).expanduser()
        self.store_path.mkdir(parents=True, exist_ok=True)
        self.events_file = self.store_path / "events.jsonl"
        self.events: List[Dict] = self._load_events()

    def record_execution(
        self,
        job_id: str,
        input_hash: str,
        output_hash: str,
        tier_used: str,
        duration_ms: int,
        success: bool,
        tenant_id: str,
        error: Optional[str] = None,
    ) -> str:
        """Record skill execution event.

        Returns: event ID
        """
        event = ExecutionEvent(
            timestamp=datetime.utcnow().isoformat() + "Z",
            event_type="skill_executed",
            skill_id="video-producer-maestro",
            job_id=job_id,
            input_hash=input_hash,
            output_hash=output_hash,
            tier_used=tier_used,
            duration_ms=duration_ms,
            success=success,
            tenant_id=tenant_id,
            error=error,
        )

        # Store as dict (immutable frozen dataclass)
        event_dict = asdict(event)
        self.events.append(event_dict)

        # Persist to JSONL (append-only)
        try:
            with open(self.events_file, "a") as f:
                f.write(json.dumps(event_dict) + "\n")
            logger.info(f"Recorded execution event: {job_id} ({tier_used})")
        except Exception as e:
            logger.error(f"Failed to persist execution event: {e}")
            raise

        return f"exec_evt_{job_id}"

    def record_feedback(
        self,
        job_id: str,
        tier_used: str,
        quality_score: int,
        engagement_score: int,
        notes: str,
        tenant_id: str,
    ) -> str:
        """Record user feedback event.

        Feedback triggers learning optimizer if >= 5 events for a tier.
        """
        # Validate scores
        quality_score = max(0, min(100, quality_score))
        engagement_score = max(0, min(100, engagement_score))
        notes = notes[:500]  # Max 500 chars

        event = FeedbackEvent(
            timestamp=datetime.utcnow().isoformat() + "Z",
            event_type="skill_feedback",
            job_id=job_id,
            tier_used=tier_used,
            quality_score=quality_score,
            engagement_score=engagement_score,
            notes=notes,
            tenant_id=tenant_id,
        )

        event_dict = asdict(event)
        self.events.append(event_dict)

        try:
            with open(self.events_file, "a") as f:
                f.write(json.dumps(event_dict) + "\n")
            logger.info(f"Recorded feedback: {job_id} — quality={quality_score}, engagement={engagement_score}")
        except Exception as e:
            logger.error(f"Failed to persist feedback event: {e}")
            raise

        return f"fb_evt_{job_id}"

    def get_tier_metrics(self, tier: str, tenant_id: str) -> Dict:
        """Aggregate metrics for a tier (single tenant)."""
        tier_events = [
            e for e in self.events
            if e.get("tier_used") == tier
            and e.get("event_type") == "skill_executed"
            and e.get("tenant_id") == tenant_id
        ]

        if not tier_events:
            return {
                "tier": tier,
                "count": 0,
                "success_rate": 0.0,
                "avg_duration_ms": 0,
                "feedback_count": 0,
                "avg_quality": 0,
                "avg_engagement": 0,
            }

        success_count = sum(1 for e in tier_events if e["success"])
        success_rate = success_count / len(tier_events) if tier_events else 0.0
        avg_duration = sum(e["duration_ms"] for e in tier_events) / len(tier_events)

        # Feedback for this tier
        feedback_events = [
            e for e in self.events
            if e.get("tier_used") == tier
            and e.get("event_type") == "skill_feedback"
            and e.get("tenant_id") == tenant_id
        ]

        avg_quality = sum(e["quality_score"] for e in feedback_events) / len(feedback_events) if feedback_events else 0
        avg_engagement = sum(e["engagement_score"] for e in feedback_events) / len(feedback_events) if feedback_events else 0

        return {
            "tier": tier,
            "count": len(tier_events),
            "success_rate": success_rate,
            "avg_duration_ms": avg_duration,
            "feedback_count": len(feedback_events),
            "avg_quality": avg_quality,
            "avg_engagement": avg_engagement,
        }

    def get_all_metrics(self, tenant_id: str) -> Dict[str, Dict]:
        """Get metrics for all tiers."""
        tiers = ["TIER_1_QUICK", "TIER_1_5_THREEJS", "TIER_2_MANIM", "TIER_3_BLENDER"]
        return {tier: self.get_tier_metrics(tier, tenant_id) for tier in tiers}

    def get_job_events(self, job_id: str) -> List[Dict]:
        """Get all events for a job (execution + feedback)."""
        return [e for e in self.events if e.get("job_id") == job_id]

    def _load_events(self) -> List[Dict]:
        """Load events from JSONL file."""
        events = []
        if self.events_file.exists():
            try:
                with open(self.events_file, "r") as f:
                    for line in f:
                        if line.strip():
                            events.append(json.loads(line))
                logger.info(f"Loaded {len(events)} events from {self.events_file}")
            except Exception as e:
                logger.warning(f"Failed to load events: {e}")
        return events

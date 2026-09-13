"""FeedbackHandlerSkill — Process user quality feedback and trigger learning."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SceneQualityFeedback:
    """User feedback on scene quality."""
    scene_id: str
    job_id: str
    feedback_type: Literal[
        "approved",
        "too_blurry",
        "too_compressed",
        "color_wrong",
        "hallucination",
    ]
    confidence: float  # 0–1
    timestamp: datetime
    tenant_id: str


class FeedbackHandlerSkill:
    """Process user feedback and trigger optimizer."""

    def __init__(self, audit_backend=None, optimizer=None):
        self.audit_backend = audit_backend
        self.optimizer = optimizer
        self.feedback_store: Dict[str, List[SceneQualityFeedback]] = {}

    async def submit_feedback(
        self,
        scene_id: str,
        job_id: str,
        feedback_type: str,
        tenant_id: str,
    ) -> str:
        """
        Submit feedback on a scene.

        Returns: feedback event ID
        """
        feedback = SceneQualityFeedback(
            scene_id=scene_id,
            job_id=job_id,
            feedback_type=feedback_type,
            confidence=0.9,
            timestamp=datetime.now(timezone.utc),
            tenant_id=tenant_id,
        )

        # Validate
        if not self._validate_feedback(feedback):
            logger.warning(f"Invalid feedback for scene {scene_id}")
            return ""

        # Store
        if job_id not in self.feedback_store:
            self.feedback_store[job_id] = []
        self.feedback_store[job_id].append(feedback)

        # Audit log
        if self.audit_backend:
            try:
                self.audit_backend.write_event("scene_quality_feedback", {
                    "scene_id": scene_id,
                    "job_id": job_id,
                    "feedback_type": feedback_type,
                    "confidence": 0.9,
                    "tenant_id": tenant_id,
                })
            except Exception as e:
                logger.warning(f"Audit logging failed: {e}")

        # Check if we should trigger optimizer
        if len(self.feedback_store[job_id]) >= 5:
            logger.info(f"Triggering optimizer for job {job_id} (5+ feedbacks)")
            if self.optimizer:
                try:
                    asyncio.create_task(self.optimizer.optimize(job_id, tenant_id))
                except Exception as e:
                    logger.warning(f"Optimizer trigger failed: {e}")

        logger.info(f"Feedback submitted: {scene_id} → {feedback_type}")
        return f"feedback_evt_{scene_id}"

    def _validate_feedback(self, feedback: SceneQualityFeedback) -> bool:
        """Validate feedback before storing."""
        # Check scene exists (would validate against job in production)
        if not feedback.scene_id:
            return False

        # Check valid feedback type
        valid_types = {
            "approved", "too_blurry", "too_compressed", "color_wrong", "hallucination"
        }
        if feedback.feedback_type not in valid_types:
            return False

        return True

    def get_job_feedback(self, job_id: str) -> List[SceneQualityFeedback]:
        """Get all feedback for a job."""
        return self.feedback_store.get(job_id, [])


import asyncio

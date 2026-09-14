"""Quality gate enforcement (DRAFT / PRODUCTION / BROADCAST)."""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class QualityGate(Enum):
    """Quality gate states (hard-enforced, no override)."""
    DRAFT = "draft"  # 0-50 points: must iterate
    PRODUCTION = "production"  # 50-85 points: auto-queue or manual edit
    BROADCAST = "broadcast"  # 85-100 points: requires human approval


@dataclass
class GateDecision:
    """Gate decision with next action."""
    gate: QualityGate
    score: int
    allows_promotion: bool
    next_action: str  # "iterate", "review", "auto_publish", "manual_review"
    reason: str


class QualityGateEnforcer:
    """Hard enforcement of quality gates.

    LOAD-BEARING RULES:
    - Gate thresholds are hardcoded (never configurable)
    - No env var override
    - No skip flag
    - To change gates: update code → review → ADR → merge
    """

    # Hard-coded thresholds (immutable)
    DRAFT_MAX_SCORE = 50
    PRODUCTION_MIN_SCORE = 50
    PRODUCTION_MAX_SCORE = 85
    BROADCAST_MIN_SCORE = 85  # Never lower this threshold

    @staticmethod
    def decide(score: int) -> GateDecision:
        """Determine gate from quality score.

        Args:
            score: Quality score (0-100)

        Returns:
            GateDecision with gate, next_action, reason

        Raises:
            ValueError if score out of range
        """
        if not (0 <= score <= 100):
            raise ValueError(f"Quality score must be 0-100, got {score}")

        if score < QualityGateEnforcer.DRAFT_MAX_SCORE:
            return GateDecision(
                gate=QualityGate.DRAFT,
                score=score,
                allows_promotion=False,
                next_action="iterate",
                reason=f"Score {score} < {QualityGateEnforcer.DRAFT_MAX_SCORE} (DRAFT threshold)"
            )

        elif score < QualityGateEnforcer.PRODUCTION_MAX_SCORE:
            return GateDecision(
                gate=QualityGate.PRODUCTION,
                score=score,
                allows_promotion=True,
                next_action="auto_publish_to_queue",
                reason=f"Score {score} in PRODUCTION range [{QualityGateEnforcer.PRODUCTION_MIN_SCORE}, {QualityGateEnforcer.PRODUCTION_MAX_SCORE})"
            )

        else:
            # score >= BROADCAST_MIN_SCORE
            return GateDecision(
                gate=QualityGate.BROADCAST,
                score=score,
                allows_promotion=True,
                next_action="manual_review",
                reason=f"Score {score} >= {QualityGateEnforcer.BROADCAST_MIN_SCORE} (BROADCAST threshold)"
            )

    @staticmethod
    def can_promote(from_gate: QualityGate, to_gate: QualityGate, score: int) -> bool:
        """Verify promotion is allowed.

        Args:
            from_gate: Current gate
            to_gate: Desired gate
            score: Current quality score

        Returns:
            True if promotion is allowed
        """
        # DRAFT -> PRODUCTION requires score >= 50
        if from_gate == QualityGate.DRAFT and to_gate == QualityGate.PRODUCTION:
            return score >= QualityGateEnforcer.PRODUCTION_MIN_SCORE

        # PRODUCTION -> BROADCAST requires score >= 85
        if from_gate == QualityGate.PRODUCTION and to_gate == QualityGate.BROADCAST:
            return score >= QualityGateEnforcer.BROADCAST_MIN_SCORE

        # No other promotions allowed
        return False

    @staticmethod
    def verify_gate_thresholds():
        """Verify gate thresholds are consistent.

        Raises:
            AssertionError if thresholds are invalid
        """
        assert QualityGateEnforcer.DRAFT_MAX_SCORE == 50, "DRAFT max must be 50"
        assert QualityGateEnforcer.PRODUCTION_MIN_SCORE == 50, "PRODUCTION min must be 50"
        assert QualityGateEnforcer.PRODUCTION_MAX_SCORE == 85, "PRODUCTION max must be 85"
        assert QualityGateEnforcer.BROADCAST_MIN_SCORE == 85, "BROADCAST min must be 85"
        assert QualityGateEnforcer.BROADCAST_MIN_SCORE >= 50, "BROADCAST min must never be < 50"


# Verify thresholds at module load time
QualityGateEnforcer.verify_gate_thresholds()

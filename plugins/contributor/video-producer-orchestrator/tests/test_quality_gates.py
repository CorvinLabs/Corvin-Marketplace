"""Unit tests for quality gates."""

import pytest
from src.quality_gates import QualityGate, QualityGateEnforcer, GateDecision


class TestQualityGateEnforcer:
    """Test quality gate enforcement (HARD RULES)."""

    def test_draft_gate_boundary(self):
        """Test DRAFT gate boundary (score < 50)."""
        # Score 49 = DRAFT
        decision = QualityGateEnforcer.decide(49)
        assert decision.gate == QualityGate.DRAFT
        assert not decision.allows_promotion
        assert decision.next_action == "iterate"

        # Score 50 = PRODUCTION (boundary)
        decision = QualityGateEnforcer.decide(50)
        assert decision.gate == QualityGate.PRODUCTION
        assert decision.allows_promotion

    def test_production_gate_range(self):
        """Test PRODUCTION gate range (50 <= score < 85)."""
        for score in [50, 60, 70, 80, 84]:
            decision = QualityGateEnforcer.decide(score)
            assert decision.gate == QualityGate.PRODUCTION
            assert decision.allows_promotion
            assert decision.score == score

    def test_broadcast_gate_boundary(self):
        """Test BROADCAST gate boundary (score >= 85)."""
        # Score 84 = PRODUCTION
        decision = QualityGateEnforcer.decide(84)
        assert decision.gate == QualityGate.PRODUCTION

        # Score 85 = BROADCAST (boundary)
        decision = QualityGateEnforcer.decide(85)
        assert decision.gate == QualityGate.BROADCAST
        assert decision.allows_promotion
        assert decision.next_action == "manual_review"

    def test_full_score_range(self):
        """Test full score range (0-100)."""
        for score in range(0, 101, 10):
            decision = QualityGateEnforcer.decide(score)
            assert decision.score == score
            assert decision.gate in QualityGate

    def test_invalid_score_too_low(self):
        """Test invalid score < 0."""
        with pytest.raises(ValueError, match="Quality score must be 0-100"):
            QualityGateEnforcer.decide(-1)

    def test_invalid_score_too_high(self):
        """Test invalid score > 100."""
        with pytest.raises(ValueError, match="Quality score must be 0-100"):
            QualityGateEnforcer.decide(101)

    def test_gate_promotion_draft_to_production(self):
        """Test promotion from DRAFT to PRODUCTION."""
        # Score 49 -> can't promote (< 50)
        assert not QualityGateEnforcer.can_promote(
            QualityGate.DRAFT,
            QualityGate.PRODUCTION,
            score=49
        )

        # Score 50 -> can promote (== 50)
        assert QualityGateEnforcer.can_promote(
            QualityGate.DRAFT,
            QualityGate.PRODUCTION,
            score=50
        )

        # Score 100 -> can promote (> 50)
        assert QualityGateEnforcer.can_promote(
            QualityGate.DRAFT,
            QualityGate.PRODUCTION,
            score=100
        )

    def test_gate_promotion_production_to_broadcast(self):
        """Test promotion from PRODUCTION to BROADCAST."""
        # Score 84 -> can't promote (< 85)
        assert not QualityGateEnforcer.can_promote(
            QualityGate.PRODUCTION,
            QualityGate.BROADCAST,
            score=84
        )

        # Score 85 -> can promote (== 85)
        assert QualityGateEnforcer.can_promote(
            QualityGate.PRODUCTION,
            QualityGate.BROADCAST,
            score=85
        )

        # Score 100 -> can promote (> 85)
        assert QualityGateEnforcer.can_promote(
            QualityGate.PRODUCTION,
            QualityGate.BROADCAST,
            score=100
        )

    def test_invalid_promotion_same_gate(self):
        """Test invalid promotion (same gate)."""
        assert not QualityGateEnforcer.can_promote(
            QualityGate.DRAFT,
            QualityGate.DRAFT,
            score=75
        )

    def test_invalid_promotion_backward(self):
        """Test invalid promotion (backward)."""
        # Can't go BROADCAST -> PRODUCTION
        assert not QualityGateEnforcer.can_promote(
            QualityGate.BROADCAST,
            QualityGate.PRODUCTION,
            score=100
        )

    def test_gate_thresholds_immutable(self):
        """Test that gate thresholds are correctly set (immutable)."""
        assert QualityGateEnforcer.DRAFT_MAX_SCORE == 50
        assert QualityGateEnforcer.PRODUCTION_MIN_SCORE == 50
        assert QualityGateEnforcer.PRODUCTION_MAX_SCORE == 85
        assert QualityGateEnforcer.BROADCAST_MIN_SCORE == 85

    def test_broadcast_min_never_below_50(self):
        """LOAD-BEARING TEST: BROADCAST gate never below 50."""
        assert QualityGateEnforcer.BROADCAST_MIN_SCORE >= 50

    def test_verify_thresholds(self):
        """Test threshold verification."""
        # Should not raise
        QualityGateEnforcer.verify_gate_thresholds()


class TestGateDecision:
    """Test GateDecision object."""

    def test_decision_contains_reason(self):
        """Test that decision includes reason."""
        decision = QualityGateEnforcer.decide(42)
        assert decision.reason is not None
        assert len(decision.reason) > 0
        assert "42" in decision.reason  # Score should be in reason

    def test_decision_next_action(self):
        """Test decision next_action field."""
        # DRAFT should have "iterate"
        draft_decision = QualityGateEnforcer.decide(25)
        assert draft_decision.next_action == "iterate"

        # PRODUCTION should have "auto_publish_to_queue"
        prod_decision = QualityGateEnforcer.decide(65)
        assert prod_decision.next_action == "auto_publish_to_queue"

        # BROADCAST should have "manual_review"
        bcast_decision = QualityGateEnforcer.decide(90)
        assert bcast_decision.next_action == "manual_review"

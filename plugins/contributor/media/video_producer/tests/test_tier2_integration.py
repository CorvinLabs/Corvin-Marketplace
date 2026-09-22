"""Integration tests for Tier 1→2 chaining"""

import pytest
from pathlib import Path

from src.verification.orchestrator import VerificationOrchestrator, VerificationTier


class TestTier1To2Chaining:
    """Test that Tier 1→2 chaining works correctly"""

    @pytest.fixture
    def orchestrator(self):
        return VerificationOrchestrator(operator_id="test_op")

    def test_tier1_only_rejection_stops_chain(self, orchestrator):
        """If Tier 1 fails, Tier 2 should not run"""
        # Path to incident file (should fail Tier 1)
        incident_audio = Path("/home/shumway/projects/Corvin-Videos/blender_20260922_001652/steps/narration.wav")

        if not incident_audio.exists():
            pytest.skip("Incident file not available")

        # Request Tier 1+2
        passed, reason = orchestrator.verify_audio_only(
            incident_audio,
            tier=VerificationTier.TIER_1_2
        )

        # Should fail at Tier 1
        assert not passed
        # Reason should indicate Tier 1 failure
        assert "tier_1" in reason.lower() or "single_frequency" in reason.lower()

    def test_tier1_pass_tier2_evaluation(self, orchestrator):
        """If Tier 1 passes, Tier 2 should be evaluated"""
        # Would need real audio that passes Tier 1 to test this
        # For now, this test structure is documented
        pass

    def test_tier1_only_mode_skips_tier2(self, orchestrator):
        """TIER_1_ONLY should not attempt Tier 2 verification"""
        # Path to incident file
        incident_video = Path("/home/shumway/projects/Corvin-Videos/blender_20260922_001652/steps/layers.mp4")

        if not incident_video.exists():
            pytest.skip("Incident file not available")

        # Request Tier 1 only
        passed, reason = orchestrator.verify_video_only(
            incident_video,
            tier=VerificationTier.TIER_1_ONLY
        )

        # Should fail at Tier 1 (solid background)
        assert not passed
        assert "tier_1" in reason.lower() or "solid" in reason.lower()


class TestVerificationAuditLogging:
    """Test that verification events are properly logged"""

    def test_audit_events_are_json_serializable(self):
        """All events must be JSON-serializable for audit trail"""
        from src.verification.audit_integration import emit_audio_verification_event
        from src.verification.models import AudioVerificationResult

        result = AudioVerificationResult(
            passed=False,
            tier=1,
            reason="test_failure"
        )

        event = emit_audio_verification_event(result)

        # Must be JSON-serializable
        import json
        json_str = json.dumps(event)
        assert json_str is not None


class TestLearningSignalEmission:
    """Test that learning signals are emitted correctly"""

    def test_failure_signal_on_rejection(self):
        """Audio rejection should emit learning signal"""
        from src.verification.learning_integration import emit_audio_verification_failure_signal
        from src.verification.models import AudioVerificationResult

        result = AudioVerificationResult(
            passed=False,
            tier=1,
            reason="audio_single_frequency_detected"
        )

        signal = emit_audio_verification_failure_signal(result)

        # Should contain recommendation
        assert "recommendation" in signal
        assert signal["recommendation"] == "regenerate_with_real_audio"

    def test_no_signal_on_success(self):
        """Successful verification should not emit failure signal"""
        from src.verification.learning_integration import emit_audio_verification_failure_signal
        from src.verification.models import AudioVerificationResult

        result = AudioVerificationResult(
            passed=True,
            tier=1,
            reason="passed_all_checks"
        )

        signal = emit_audio_verification_failure_signal(result)

        # Should be empty dict (no signal)
        assert signal == {}

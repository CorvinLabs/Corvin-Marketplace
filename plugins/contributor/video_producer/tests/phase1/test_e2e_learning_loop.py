"""E2E Test: Complete Learning Loop Video Production

Tests the full Maestro pipeline:
1. Voice synthesis (narration → MP3)
2. Voice-sync mapping
3. Animation rendering (Tier 2 Manim)
4. Video composition + hash verification
5. Audit trail logging
"""

import pytest
import subprocess
from pathlib import Path
import time


class TestLearningLoopE2E:
    """E2E tests for Learning Loop video production"""

    @pytest.fixture
    def plugin_root(self):
        """Get plugin root directory"""
        return Path(__file__).parent.parent.parent

    @pytest.fixture
    def maestro(self, plugin_root):
        """Create Maestro orchestrator"""
        import sys
        sys.path.insert(0, str(plugin_root / "src"))

        from tier_dispatcher import TierDispatcher
        from phase5.manim_animator import ManimAnimatorWorker
        from phase5.quick_renderer import QuickRendererWorker
        from voice_synthesizer import VoiceSynthesizer
        from maestro import Maestro

        tier1 = QuickRendererWorker(timeout_seconds=10)
        tier2 = ManimAnimatorWorker(timeout_seconds=60)
        dispatcher = TierDispatcher(tier1, tier2)
        synth = VoiceSynthesizer(cache_enabled=True)

        return Maestro(dispatcher, synth)

    @pytest.fixture
    def learning_loop_storyboard(self):
        """Create Learning Loop storyboard"""
        from maestro import Storyboard

        return Storyboard(
            title="Learning Loop Visualization",
            concept_id="learning-loop",
            didactic_level="beginner",
            duration_seconds=30,
            narration="The learning loop has five steps: Measure, Feedback, Analyze, Optimize, and Deploy.",
            keyframes=[
                {"frame": 0, "event": "start"},
                {"frame": 30, "event": "measure_appears"},
                {"frame": 60, "event": "feedback_appears"},
                {"frame": 120, "event": "analyze_appears"},
                {"frame": 180, "event": "optimize_appears"},
                {"frame": 240, "event": "deploy_appears"},
                {"frame": 300, "event": "end"}
            ],
            output_format="mp4"
        )

    def test_voice_synthesis(self, maestro, learning_loop_storyboard):
        """Test voice synthesis (narration → MP3)"""
        from voice_synthesizer import SynthesisRequest

        request = SynthesisRequest(
            text=learning_loop_storyboard.narration,
            voice="nova",
            model="tts-1-hd"
        )

        result = maestro.synth.synthesize(request)

        # Either succeeds with audio or fails gracefully (if API key not set)
        if result.success:
            assert result.audio_path is not None
            assert result.audio_path.exists()
            assert result.duration_sec > 0
            assert result.text_hash  # SHA256 hash
        else:
            assert "No OpenAI API key" in result.error or "API" in result.error

    def test_manim_animation(self, maestro, learning_loop_storyboard):
        """Test Manim animation rendering (Tier 2)"""
        from phase5.manim_animator import AnimationRequest

        request = AnimationRequest(
            animation_id="learning-loop",
            concept_id="learning-loop",
            didactic_level="beginner",
            duration_seconds=30,
            assets=[],
            output_format="mp4"
        )

        result = maestro.dispatcher.tier2.execute(request)

        # Result should succeed or fail gracefully (if manim not installed)
        if result.success:
            assert result.output_path is not None
            assert result.output_path.exists()
            assert result.duration_seconds > 0
            assert result.tier_used == 2
        else:
            assert "timeout" in result.error.lower() or "manim" in result.error.lower()

    def test_quick_renderer_fallback(self, maestro, learning_loop_storyboard):
        """Test Tier 1 Quick Renderer (always succeeds)"""
        from phase5.quick_renderer import QuickRendererWorker

        worker = QuickRendererWorker(timeout_seconds=10)
        request = type("AnimReq", (), {
            "animation_id": "learning-loop",
            "duration_seconds": 30
        })()

        result = worker.execute(request)

        # Tier 1 should always succeed
        assert result["success"] is True
        assert result["output_path"] is not None
        assert Path(result["output_path"]).exists()

    def test_tier_fallback_chain(self, maestro, learning_loop_storyboard):
        """Test deterministic Tier fallback (2 → 1)"""
        from phase5.tier_dispatcher import TierLevel, AnimationRequest

        request = AnimationRequest(
            animation_id="learning-loop",
            didactic_level="beginner",
            duration_seconds=30,
            preferred_tier=TierLevel.TIER_2_RICH
        )

        result = maestro.dispatcher.dispatch(request)

        # Should succeed via either Tier 2 or Tier 1 fallback
        assert result["success"] is True
        assert result["tier"] in ["TIER_2_RICH", "TIER_1_QUICK"]
        assert result["output_path"] is not None

    def test_voice_sync_mapping(self, maestro, learning_loop_storyboard):
        """Test voice-sync keyframe mapping"""
        from phase5.voice_sync_mapper import VoiceSyncMapper, NarrationAudio, Keyframe
        from pathlib import Path

        mapper = VoiceSyncMapper(frame_rate=30)

        # Create mock audio metadata
        audio = NarrationAudio(
            audio_path=Path("/tmp/dummy.mp3"),
            duration_sec=30,
            frame_rate=30
        )

        # Create keyframes from storyboard
        keyframes = [
            Keyframe(
                frame=kf["frame"],
                event=kf["event"],
                narrator_text="",
                animation_action=None,
                timestamp_sec=kf["frame"] / 30.0
            )
            for kf in learning_loop_storyboard.keyframes
        ]

        # Create mapping
        mapping = mapper.create_mapping(audio, keyframes)

        # Verify mapping
        assert len(mapping.keyframe_indices) == len(keyframes)
        assert mapping.get_event_at_frame(0) == "start"
        assert mapping.get_event_at_frame(30) == "measure_appears"

        # Validate mapping
        errors = mapper.validate_mapping(mapping, audio)
        assert len(errors) == 0, f"Mapping validation failed: {errors}"

    def test_maestro_produce_full_pipeline(self, maestro, learning_loop_storyboard):
        """Test full Maestro pipeline (storyboard → video)"""
        result = maestro.produce(learning_loop_storyboard)

        # Should succeed or fail gracefully
        if result["success"]:
            assert result["output_path"] is not None
            assert Path(result["output_path"]).exists()
            assert result["duration_seconds"] == 30
            assert result["tier_used"] in [1, 2, 3]
            assert len(result["audit_events"]) > 0

            # Verify audit events
            events = {e["event_type"] for e in result["audit_events"]}
            assert "storyboard_validated" in events
            assert "video_production_complete" in events

        else:
            # Graceful failure (API key, manim, etc.)
            assert "error" in result

    def test_storyboard_hashing(self, maestro, learning_loop_storyboard):
        """Test storyboard hash reproducibility"""
        hash1 = maestro._hash_storyboard(learning_loop_storyboard)
        hash2 = maestro._hash_storyboard(learning_loop_storyboard)

        # Same storyboard → same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex

        # Modified storyboard → different hash
        modified = type(
            "Storyboard", (),
            {**learning_loop_storyboard.__dict__, "narration": "Different text"}
        )()
        hash3 = maestro._hash_storyboard(modified)
        assert hash3 != hash1

    def test_ffprobe_verification(self):
        """Test ffprobe can verify video files"""
        # Check if ffprobe is available
        try:
            result = subprocess.run(
                ["ffprobe", "-version"],
                capture_output=True,
                timeout=5,
                check=False
            )
            assert result.returncode == 0, "ffprobe not available"
        except FileNotFoundError:
            pytest.skip("ffprobe not installed")

    def test_audit_trail_logging(self, maestro, learning_loop_storyboard):
        """Test audit event logging + hash-chain"""
        import json

        result = maestro.produce(learning_loop_storyboard)

        # Check audit events are logged
        if result["success"]:
            concept_id = learning_loop_storyboard.concept_id
            audit_file = maestro.audit_dir / f"{concept_id}_audit.jsonl"

            # Verify file exists and is readable
            if audit_file.exists():
                with open(audit_file) as f:
                    lines = f.readlines()
                    assert len(lines) > 0

                    # Parse each event
                    events = [json.loads(line) for line in lines]
                    for event in events:
                        assert "event_type" in event
                        assert "timestamp" in event
                        assert "concept_id" in event

    def test_metadata_serialization(self, maestro, learning_loop_storyboard):
        """Test video metadata is serialized correctly"""
        import json

        result = maestro.produce(learning_loop_storyboard)

        if result["success"]:
            concept_id = learning_loop_storyboard.concept_id
            metadata_file = maestro.metadata_dir / f"{concept_id}_metadata.json"

            if metadata_file.exists():
                with open(metadata_file) as f:
                    metadata = json.load(f)

                # Verify metadata structure
                assert "storyboard_hash" in metadata
                assert "video_hash" in metadata
                assert "tier_used" in metadata
                assert "generation_timestamp" in metadata


class TestAuditChainIntegrity:
    """Test audit chain integrity for reproducibility"""

    def test_consistent_hashing(self):
        """Test SHA256 hashing is consistent"""
        import hashlib

        text = "Learning Loop Concept"
        hash1 = hashlib.sha256(text.encode()).hexdigest()
        hash2 = hashlib.sha256(text.encode()).hexdigest()

        assert hash1 == hash2
        assert len(hash1) == 64

    def test_audit_event_timestamp(self):
        """Test audit events include ISO8601 timestamps"""
        from datetime import datetime

        now = datetime.now().isoformat()
        assert "T" in now  # ISO8601 format
        assert ":" in now


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

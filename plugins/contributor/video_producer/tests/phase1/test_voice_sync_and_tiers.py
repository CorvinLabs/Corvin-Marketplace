"""Phase 1 Tests: Voice Sync Timing + Tier Fallback + Asset Library"""

import pytest
from pathlib import Path
import json
import sys

# Add plugin src to path
plugin_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(plugin_root / "src"))


class TestVoiceSyncTiming:
    """Tests for voice-sync keyframe timing"""

    def test_voice_sync_mapper_creation(self):
        """Test VoiceSyncMapper initialization"""
        from phase5.voice_sync_mapper import VoiceSyncMapper

        mapper = VoiceSyncMapper(frame_rate=30)
        assert mapper.frame_rate == 30

    def test_keyframe_validation(self):
        """Test keyframe validation against audio duration"""
        from phase5.voice_sync_mapper import (
            VoiceSyncMapper, NarrationAudio, Keyframe
        )

        mapper = VoiceSyncMapper(frame_rate=30)
        audio = NarrationAudio(
            audio_path=Path("/tmp/dummy.mp3"),
            duration_sec=30
        )

        # Valid keyframes
        keyframes = [
            Keyframe(frame=0, event="start", narrator_text=""),
            Keyframe(frame=30, event="mid", narrator_text=""),
            Keyframe(frame=60, event="end", narrator_text="")
        ]

        mapping = mapper.create_mapping(audio, keyframes)
        errors = mapper.validate_mapping(mapping, audio)
        assert len(errors) == 0

    def test_keyframe_exceeds_duration(self):
        """Test keyframe validation catches frames beyond audio duration"""
        from phase5.voice_sync_mapper import (
            VoiceSyncMapper, NarrationAudio, Keyframe
        )

        mapper = VoiceSyncMapper(frame_rate=30)
        audio = NarrationAudio(
            audio_path=Path("/tmp/dummy.mp3"),
            duration_sec=10  # 10 sec = 300 frames @ 30 FPS
        )

        # Keyframe beyond duration
        keyframes = [
            Keyframe(frame=0, event="start", narrator_text=""),
            Keyframe(frame=400, event="too_late", narrator_text="")  # > 300 frames
        ]

        with pytest.raises(ValueError):
            mapper.create_mapping(audio, keyframes)

    def test_voice_sync_json_serialization(self):
        """Test voice-sync mapping JSON export/import"""
        from phase5.voice_sync_mapper import (
            VoiceSyncMapper, NarrationAudio, Keyframe
        )

        mapper = VoiceSyncMapper(frame_rate=30)
        audio = NarrationAudio(
            audio_path=Path("/tmp/dummy.mp3"),
            duration_sec=30
        )

        keyframes = [
            Keyframe(frame=0, event="start", narrator_text="Hello"),
            Keyframe(frame=60, event="mid", narrator_text="World")
        ]

        mapping = mapper.create_mapping(audio, keyframes)
        json_str = mapper.export_mapping_json(mapping)

        # Should be valid JSON
        data = json.loads(json_str)
        assert "frame_to_event" in data
        assert "keyframes" in data

        # Re-import
        mapping2 = mapper.import_mapping_json(json_str)
        assert mapping2.get_event_at_frame(0) == "start"
        assert mapping2.get_event_at_frame(60) == "mid"

    def test_silence_detection(self):
        """Test silence range checking"""
        from phase5.voice_sync_mapper import (
            VoiceSyncMapper, NarrationAudio, Keyframe, VoiceSyncMapping
        )

        mapper = VoiceSyncMapper()

        # Create mapping with silence ranges
        mapping = VoiceSyncMapping(
            frame_to_event={0: "start"},
            keyframes=[],
            narrator_silence_ranges=[(10, 20), (40, 50)],
            keyframe_indices=[0]
        )

        # Test silence detection
        assert mapping.is_silence(15) is True
        assert mapping.is_silence(45) is True
        assert mapping.is_silence(25) is False
        assert mapping.is_silence(5) is False


class TestTierFallback:
    """Tests for tier fallback chain"""

    def test_tier_dispatcher_initialization(self):
        """Test TierDispatcher setup"""
        from tier_dispatcher import TierDispatcher
        from phase5.quick_renderer import QuickRendererWorker
        from phase5.manim_animator import ManimAnimatorWorker

        tier1 = QuickRendererWorker()
        tier2 = ManimAnimatorWorker()
        dispatcher = TierDispatcher(tier1, tier2)

        assert dispatcher.tier1 is not None
        assert dispatcher.tier2 is not None
        assert len(dispatcher.tier_metrics) == 3

    def test_fallback_chain_ordering(self):
        """Test fallback chain is deterministic"""
        from tier_dispatcher import TierDispatcher, TierLevel
        from phase5.quick_renderer import QuickRendererWorker
        from phase5.manim_animator import ManimAnimatorWorker

        tier1 = QuickRendererWorker()
        tier2 = ManimAnimatorWorker()
        dispatcher = TierDispatcher(tier1, tier2)

        # Tier 2 → Tier 1
        fallback = dispatcher._get_fallback_chain(TierLevel.TIER_2_RICH)
        assert fallback == [TierLevel.TIER_1_QUICK]

        # Tier 3 → Tier 2 → Tier 1
        fallback = dispatcher._get_fallback_chain(TierLevel.TIER_3_PREMIUM)
        assert fallback == [TierLevel.TIER_2_RICH, TierLevel.TIER_1_QUICK]

        # Tier 1 has no fallback (always succeeds)
        fallback = dispatcher._get_fallback_chain(TierLevel.TIER_1_QUICK)
        assert fallback == []

    def test_tier_metrics_tracking(self):
        """Test tier performance metrics"""
        from tier_dispatcher import TierDispatcher, TierLevel
        from phase5.quick_renderer import QuickRendererWorker
        from phase5.manim_animator import ManimAnimatorWorker

        tier1 = QuickRendererWorker()
        tier2 = ManimAnimatorWorker()
        dispatcher = TierDispatcher(tier1, tier2)

        metrics = dispatcher.get_metrics()

        assert "tier_1_quick" in metrics
        assert "tier_2_rich" in metrics
        assert "tier_3_premium" in metrics

        # Check structure
        for tier_name, tier_metrics in metrics.items():
            if tier_name != "timestamp":
                assert "success_count" in tier_metrics
                assert "fail_count" in tier_metrics


class TestAssetLibrary:
    """Tests for asset versioning and reproducibility"""

    def test_asset_metadata_creation(self):
        """Test AssetMetadata dataclass"""
        from phase5.asset_library import AssetMetadata
        import hashlib

        content = b"test_asset"
        checksum = hashlib.sha256(content).hexdigest()

        asset = AssetMetadata(
            id="learning-loop",
            version="1.0",
            name="Learning Loop",
            description="5-step feedback loop",
            asset_type="manim-scene",
            checksum_sha256=checksum,
            didactic_level=["beginner"],
            duration_seconds=30,
            file_path="assets/learning-loop.py",
            license="MIT",
            created_at="2026-09-14T12:00:00Z",
            created_by="test"
        )

        # Test full_id generation
        full_id = asset.full_id()
        assert "learning-loop#v1.0#" in full_id
        assert len(full_id) > len("learning-loop#v1.0#")

    def test_asset_library_manifest(self, tmp_path):
        """Test AssetLibraryManifest"""
        from phase5.asset_library import AssetLibraryManifest, AssetMetadata
        import hashlib

        manifest_path = tmp_path / "manifest.json"

        # Create manifest
        manifest = AssetLibraryManifest(manifest_path)

        # Add asset
        asset = AssetMetadata(
            id="learning-loop",
            version="1.0",
            name="Learning Loop",
            description="Test",
            asset_type="manim-scene",
            checksum_sha256="abc123",
            didactic_level=["beginner"],
            duration_seconds=30,
            file_path="learning-loop.py",
            license="MIT",
            created_at="2026-09-14",
            created_by="test"
        )

        manifest.add_asset(asset)

        # Save and reload
        manifest.save_manifest()
        manifest2 = AssetLibraryManifest(manifest_path)

        # Verify
        retrieved = manifest2.get_latest_asset("learning-loop")
        assert retrieved is not None
        assert retrieved.version == "1.0"
        assert retrieved.checksum_sha256 == "abc123"

    def test_asset_versioning(self, tmp_path):
        """Test asset version tracking"""
        from phase5.asset_library import AssetLibraryManifest, AssetMetadata

        manifest_path = tmp_path / "manifest.json"
        manifest = AssetLibraryManifest(manifest_path)

        # Add v1.0
        asset_v1 = AssetMetadata(
            id="test-asset",
            version="1.0",
            name="Test",
            description="Test",
            asset_type="manim-scene",
            checksum_sha256="hash_v1",
            didactic_level=[],
            duration_seconds=10,
            file_path="test.py",
            license="MIT",
            created_at="2026-09-14",
            created_by="test"
        )

        # Add v2.0
        asset_v2 = AssetMetadata(
            id="test-asset",
            version="2.0",
            name="Test",
            description="Test",
            asset_type="manim-scene",
            checksum_sha256="hash_v2",
            didactic_level=[],
            duration_seconds=10,
            file_path="test.py",
            license="MIT",
            created_at="2026-09-14",
            created_by="test"
        )

        manifest.add_asset(asset_v1)
        manifest.add_asset(asset_v2)

        # Get latest (should be v2.0)
        latest = manifest.get_latest_asset("test-asset")
        assert latest.version == "2.0"

        # Get specific version
        v1 = manifest.get_asset("test-asset", "1.0")
        assert v1.version == "1.0"

    def test_asset_manifest_json_export(self, tmp_path):
        """Test manifest JSON export"""
        from phase5.asset_library import AssetLibraryManifest, AssetMetadata
        import json

        manifest = AssetLibraryManifest(tmp_path / "manifest.json")

        asset = AssetMetadata(
            id="test",
            version="1.0",
            name="Test",
            description="Test",
            asset_type="manim-scene",
            checksum_sha256="abc",
            didactic_level=[],
            duration_seconds=10,
            file_path="test.py",
            license="MIT",
            created_at="2026-09-14",
            created_by="test"
        )

        manifest.add_asset(asset)
        json_str = manifest.export_json()

        # Should be valid JSON
        data = json.loads(json_str)
        assert "version" in data
        assert "assets" in data
        assert len(data["assets"]) == 1

    def test_asset_reproducibility(self, tmp_path):
        """Test asset hashing ensures reproducibility"""
        from phase5.asset_library import AssetLibraryManifest, AssetMetadata
        import hashlib

        # Create two identical assets
        checksum = hashlib.sha256(b"test content").hexdigest()

        asset1 = AssetMetadata(
            id="test",
            version="1.0",
            name="Test",
            description="Test",
            asset_type="manim-scene",
            checksum_sha256=checksum,
            didactic_level=[],
            duration_seconds=10,
            file_path="test.py",
            license="MIT",
            created_at="2026-09-14",
            created_by="test"
        )

        asset2 = AssetMetadata(
            id="test",
            version="1.0",
            name="Test",
            description="Test",
            asset_type="manim-scene",
            checksum_sha256=checksum,
            didactic_level=[],
            duration_seconds=10,
            file_path="test.py",
            license="MIT",
            created_at="2026-09-14",
            created_by="test"
        )

        # Same content = same hash
        assert asset1.checksum_sha256 == asset2.checksum_sha256


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

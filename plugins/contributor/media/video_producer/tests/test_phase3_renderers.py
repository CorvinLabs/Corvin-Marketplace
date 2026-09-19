"""Phase 3 Tests — Premium Renderers (Three.js + Blender)

Tests for:
- Three.js GPU rendering (Tier 1.5)
- Blender async execution (Tier 3)
- Tier dispatcher with fallback chain
- Auto-downgrade logic
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from threejs_renderer import ThreeJSRenderer, ThreeJSRenderRequest
from blender_async_executor import BlenderAsyncExecutor
from tier_dispatcher import TierDispatcher, TIER_CAPABILITIES
from tier_learning_optimizer import TierLearningOptimizer
from learning_event_store import LearningEventStore


class TestThreeJSRenderer:
    """Test Three.js GPU rendering."""

    def setup_method(self):
        """Create renderer."""
        self.renderer = ThreeJSRenderer(timeout_seconds=15)

    def test_threejs_scenes_exist(self):
        """All required scenes are defined."""
        required_scenes = ["maestro-3d", "learning-loop-3d", "audit-chain-3d"]
        for scene in required_scenes:
            assert scene in self.renderer.scenes
            assert len(self.renderer.scenes[scene]) > 0

    def test_generate_html(self):
        """HTML generation includes scene code."""
        request = ThreeJSRenderRequest(
            scene_name="maestro-3d",
            duration_seconds=10,
        )
        html = self.renderer._generate_html(request)

        assert "three.js" in html.lower()
        assert "maestro" in html.lower()
        assert "10000" in html  # Duration in ms

    def test_puppeteer_script_generation(self):
        """Puppeteer script is generated correctly."""
        request = ThreeJSRenderRequest(
            scene_name="learning-loop-3d",
            duration_seconds=5,
            width=1920,
            height=1080,
        )

        script = self.renderer._puppeteer_script(
            "/tmp/scene.html",
            "/tmp/output.mp4",
            request,
        )

        assert "puppeteer" in script.lower()
        assert "1920" in script
        assert "1080" in script
        assert "5000" in script  # Duration in ms

    def test_render_result_structure(self):
        """Render result has correct structure."""
        request = ThreeJSRenderRequest(
            scene_name="maestro-3d",
            duration_seconds=5,
        )

        # Mock subprocess to avoid actually running Puppeteer
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="Test error")
            result = self.renderer.render(request)

        assert hasattr(result, "success")
        assert hasattr(result, "video_file")
        assert hasattr(result, "duration_seconds")
        assert hasattr(result, "error")
        assert hasattr(result, "elapsed_ms")

    def test_render_failure_handling(self):
        """Render failures are handled gracefully."""
        request = ThreeJSRenderRequest(
            scene_name="maestro-3d",
            duration_seconds=5,
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="Render failed")
            result = self.renderer.render(request)

        assert not result.success
        assert result.error is not None
        assert "Render failed" in result.error

    def test_render_timeout(self):
        """Render timeout is handled."""
        import subprocess
        request = ThreeJSRenderRequest(
            scene_name="maestro-3d",
            duration_seconds=5,
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("node", 15)
            result = self.renderer.render(request)

        assert not result.success
        assert "timeout" in result.error.lower()

    def test_unknown_scene(self):
        """Unknown scene is rejected."""
        request = ThreeJSRenderRequest(
            scene_name="invalid-scene",
            duration_seconds=5,
        )

        result = self.renderer.render(request)
        assert not result.success
        assert "Unknown scene" in result.error


class TestBlenderAsyncExecutor:
    """Test Blender async rendering."""

    def setup_method(self):
        """Create executor with temp directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.executor = BlenderAsyncExecutor(
            blender_path="/usr/bin/blender",
            max_jobs=2,
            job_storage=self.temp_dir,
        )

    def test_blender_health_check(self):
        """Blender health check works."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            is_healthy = self.executor._is_blender_healthy()

        assert is_healthy

    def test_blender_health_check_failure(self):
        """Blender health check handles failures."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="Not found")
            is_healthy = self.executor._is_blender_healthy()

        assert not is_healthy

    def test_submit_job(self):
        """Submit Blender job (non-blocking)."""
        with patch.object(self.executor, "_is_blender_healthy") as mock_health:
            with patch("subprocess.Popen") as mock_popen:
                mock_health.return_value = True
                mock_process = MagicMock()
                mock_process.poll.return_value = None  # Still running
                mock_popen.return_value = mock_process

                job_id = self.executor.submit_job(
                    blend_file="/tmp/scene.blend",
                    output_path="/tmp/output.png",
                    scene_name="my_scene",
                )

        assert job_id is not None
        assert job_id in self.executor.running_jobs

    def test_submit_job_blender_unavailable(self):
        """Submit returns None if Blender unavailable."""
        with patch.object(self.executor, "_is_blender_healthy") as mock_health:
            mock_health.return_value = False
            job_id = self.executor.submit_job(
                blend_file="/tmp/scene.blend",
                output_path="/tmp/output.png",
                scene_name="my_scene",
            )

        assert job_id is None

    def test_submit_job_queue_full(self):
        """Submit returns None if job queue full."""
        # Fill queue
        self.executor.max_jobs = 1
        self.executor.running_jobs["existing_job"] = {
            "process": MagicMock(),
            "start_time": "2026-09-01T00:00:00Z",
        }

        with patch.object(self.executor, "_is_blender_healthy") as mock_health:
            mock_health.return_value = True
            job_id = self.executor.submit_job(
                blend_file="/tmp/scene.blend",
                output_path="/tmp/output.png",
                scene_name="my_scene",
            )

        assert job_id is None

    def test_poll_job_running(self):
        """Poll job while running."""
        from datetime import datetime

        job_id = "test_job_001"
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Still running

        self.executor.running_jobs[job_id] = {
            "process": mock_process,
            "output_path": "/tmp/output.mp4",
            "start_time": datetime.utcnow().isoformat() + "Z",
        }

        result = self.executor.poll_job(job_id)

        assert result["status"] == "running"
        assert "elapsed_seconds" in result
        assert result["output_path"] == "/tmp/output.mp4"

    def test_poll_job_complete(self):
        """Poll job when complete."""
        from datetime import datetime

        job_id = "test_job_001"
        mock_process = MagicMock()
        mock_process.poll.return_value = 0  # Success

        self.executor.running_jobs[job_id] = {
            "process": mock_process,
            "output_path": "/tmp/output.mp4",
            "start_time": datetime.utcnow().isoformat() + "Z",
        }

        result = self.executor.poll_job(job_id)

        assert result["status"] == "complete"
        assert result["output_path"] == "/tmp/output.mp4"
        # Job should be removed from running list
        assert job_id not in self.executor.running_jobs

    def test_poll_job_not_found(self):
        """Poll job that doesn't exist."""
        result = self.executor.poll_job("nonexistent_job")
        assert result["status"] == "not_found"

    def test_auto_downgrade_no_failures(self):
        """Auto-downgrade returns None if healthy."""
        with patch.object(self.executor, "_count_recent_failures") as mock_count:
            mock_count.return_value = 0
            result = self.executor.auto_downgrade()

        assert result is None

    def test_auto_downgrade_threshold_exceeded(self):
        """Auto-downgrade triggers on 3+ failures."""
        with patch.object(self.executor, "_count_recent_failures") as mock_count:
            mock_count.return_value = 3
            result = self.executor.auto_downgrade()

        assert result == "FALLBACK_TO_TIER_2"


class TestTierDispatcher:
    """Test tier selection and dispatch."""

    def setup_method(self):
        """Setup dispatcher."""
        self.temp_dir = tempfile.mkdtemp()
        self.event_store = LearningEventStore(store_path=self.temp_dir)
        self.optimizer = TierLearningOptimizer(
            self.event_store,
            config_path=str(Path(self.temp_dir) / "weights.json"),
        )
        self.threejs = ThreeJSRenderer()
        self.blender = BlenderAsyncExecutor(job_storage=self.temp_dir)

        self.dispatcher = TierDispatcher(
            learning_optimizer=self.optimizer,
            threejs_renderer=self.threejs,
            blender_executor=self.blender,
        )

    def test_tier_capabilities_defined(self):
        """All tiers have defined capabilities."""
        tiers = ["TIER_1_QUICK", "TIER_1_5_THREEJS", "TIER_2_MANIM", "TIER_3_BLENDER"]
        for tier in tiers:
            assert tier in TIER_CAPABILITIES
            caps = TIER_CAPABILITIES[tier]
            assert caps.quality_level > 0
            assert caps.estimated_duration_seconds > 0

    def test_select_tier_no_preference(self):
        """Select tier with default logic."""
        tier = self.dispatcher.select_tier(tenant_id="_default")
        assert tier in ["TIER_1_QUICK", "TIER_1_5_THREEJS", "TIER_2_MANIM", "TIER_3_BLENDER"]

    def test_select_tier_quality_preference(self):
        """Select tier meeting quality preference."""
        # Prefer quality level 3+ (should pick TIER_2_MANIM or TIER_3_BLENDER)
        tier = self.dispatcher.select_tier(tenant_id="_default", preferred_quality=3)
        assert TIER_CAPABILITIES[tier].quality_level >= 3

    def test_select_tier_fallback(self):
        """Fallback to available tier if preferred unavailable."""
        # Disable all renderers except quick
        dispatcher = TierDispatcher(
            learning_optimizer=None,
            threejs_renderer=None,
            blender_executor=None,
        )

        tier = dispatcher.select_tier(tenant_id="_default", preferred_quality=5)
        # Should fallback to TIER_1_QUICK
        assert tier == "TIER_1_QUICK"

    def test_dispatch_tier1_quick(self):
        """Dispatch to Tier 1 (quick)."""
        result = self.dispatcher.dispatch("TIER_1_QUICK", {"duration_seconds": 30})
        assert result is not None
        assert result["tier"] == "TIER_1_QUICK"
        assert result["success"]

    def test_dispatch_tier2_manim(self):
        """Dispatch to Tier 2 (Manim)."""
        result = self.dispatcher.dispatch("TIER_2_MANIM", {"duration_seconds": 60})
        assert result is not None
        assert result["tier"] == "TIER_2_MANIM"
        assert result["success"]

    def test_dispatch_tier1_5_threejs(self):
        """Dispatch to Tier 1.5 (Three.js)."""
        result = self.dispatcher.dispatch(
            "TIER_1_5_THREEJS",
            {"scene_name": "maestro-3d", "duration_seconds": 10},
        )
        assert result is not None
        assert result["tier"] == "TIER_1_5_THREEJS"
        # Success depends on Puppeteer availability

    def test_get_tier_stats(self):
        """Get stats for all tiers."""
        stats = self.dispatcher.get_tier_stats("_default")

        assert "tier_weights" in stats
        assert "tier_capabilities" in stats

        # Verify all tiers present
        for tier in ["TIER_1_QUICK", "TIER_1_5_THREEJS", "TIER_2_MANIM", "TIER_3_BLENDER"]:
            assert tier in stats["tier_capabilities"]


class TestCompletePhase3:
    """Integration test: complete Phase 3."""

    def test_threejs_and_blender_coexist(self):
        """Three.js and Blender can coexist."""
        temp_dir = tempfile.mkdtemp()
        threejs = ThreeJSRenderer()
        blender = BlenderAsyncExecutor(job_storage=temp_dir)

        # Both should be usable
        assert threejs.scenes is not None
        assert len(threejs.scenes) > 0
        assert blender.job_storage.exists()

    def test_tier_dispatcher_full_chain(self):
        """Dispatcher handles all tiers + fallback."""
        temp_dir = tempfile.mkdtemp()
        store = LearningEventStore(store_path=temp_dir)
        optimizer = TierLearningOptimizer(store, config_path=str(Path(temp_dir) / "weights.json"))
        threejs = ThreeJSRenderer()
        blender = BlenderAsyncExecutor(job_storage=temp_dir)

        dispatcher = TierDispatcher(
            learning_optimizer=optimizer,
            threejs_renderer=threejs,
            blender_executor=blender,
        )

        # Test each tier selection
        for quality_level in [1, 2, 3, 5]:
            tier = dispatcher.select_tier("_default", preferred_quality=quality_level)
            assert tier in ["TIER_1_QUICK", "TIER_1_5_THREEJS", "TIER_2_MANIM", "TIER_3_BLENDER"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

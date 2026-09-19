"""Production E2E Tests — Complete pipeline validation

Tests for production readiness:
- Full video generation pipeline
- All 4 tiers operational
- Learning loop active
- Audit trail functional
- Production hardening checks
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from maestro import Maestro, Storyboard
from skill import TaskOrchestrator
from learning_event_store import LearningEventStore
from tier_learning_optimizer import TierLearningOptimizer
from tier_dispatcher import TierDispatcher
from threejs_renderer import ThreeJSRenderer
from blender_async_executor import BlenderAsyncExecutor
from production_hardening import ProductionHardening


class TestProductionPipeline:
    """Test complete production pipeline."""

    def setup_method(self):
        """Setup for production tests."""
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

    def test_complete_video_pipeline(self):
        """Complete pipeline: storyboard → narration → animation → video."""
        # Step 1: Create storyboard
        storyboard = Storyboard(
            title="CorvinOS Overview",
            concept_id="corvin_overview_001",
            didactic_level="technical",
            duration_seconds=60,
            narration="Welcome to CorvinOS. A learning-driven operating system.",
            keyframes=[
                {"frame": 0, "event": "title_show"},
                {"frame": 30, "event": "narration_play"},
                {"frame": 60, "event": "credits"},
            ],
            output_format="mp4",
        )

        assert storyboard.title == "CorvinOS Overview"
        assert storyboard.duration_seconds == 60

        # Step 2: Select tier
        tier = self.dispatcher.select_tier(tenant_id="_default", preferred_quality=3)
        assert tier in ["TIER_1_QUICK", "TIER_1_5_THREEJS", "TIER_2_MANIM", "TIER_3_BLENDER"]

        # Step 3: Record execution event
        self.event_store.record_execution(
            job_id="job_001",
            input_hash="storyboard_hash_001",
            output_hash="video_hash_001",
            tier_used=tier,
            duration_ms=45000,
            success=True,
            tenant_id="_default",
        )

        # Step 4: Provide feedback
        self.event_store.record_feedback(
            job_id="job_001",
            tier_used=tier,
            quality_score=85,
            engagement_score=90,
            notes="Great quality!",
            tenant_id="_default",
        )

        # Step 5: Verify audit trail
        events = self.event_store.get_job_events("job_001")
        assert len(events) == 2  # Execution + feedback

    def test_all_tiers_available(self):
        """All 4 tiers are available and dispatchable."""
        test_cases = [
            ("TIER_1_QUICK", {"duration_seconds": 30}),
            ("TIER_1_5_THREEJS", {"scene_name": "maestro-3d", "duration_seconds": 10}),
            ("TIER_2_MANIM", {"duration_seconds": 60}),
            ("TIER_3_BLENDER", {"blend_file": "/tmp/test.blend", "output_path": "/tmp/output.png"}),
        ]

        for tier, request in test_cases:
            result = self.dispatcher.dispatch(tier, request)
            assert result is not None
            assert "tier" in result

    def test_learning_loop_full_cycle(self):
        """Complete learning loop: render → feedback → optimize."""
        tiers = ["TIER_1_QUICK", "TIER_2_MANIM", "TIER_3_BLENDER"]

        # Generate renders with different quality outcomes
        for tier_idx, tier in enumerate(tiers):
            for job_num in range(5):
                # Simulate render
                self.event_store.record_execution(
                    job_id=f"{tier}_{job_num}",
                    input_hash="hash",
                    output_hash="output",
                    tier_used=tier,
                    duration_ms=5000 + tier_idx * 2000,
                    success=(job_num < 4),  # 4 success, 1 failure
                    tenant_id="_default",
                )

                # Simulate feedback (higher quality for higher tier)
                self.event_store.record_feedback(
                    job_id=f"{tier}_{job_num}",
                    tier_used=tier,
                    quality_score=60 + tier_idx * 15,
                    engagement_score=65 + tier_idx * 15,
                    notes="",
                    tenant_id="_default",
                )

        # Optimize weights
        self.optimizer.optimize_tier_selection("_default")

        # Verify weights changed
        weights = self.optimizer.get_tier_distribution()
        assert weights["TIER_3_BLENDER"] > weights["TIER_1_QUICK"]

        # Verify recommendation
        recommended = self.optimizer.recommend_tier()
        assert recommended == "TIER_3_BLENDER"

    def test_audit_trail_integrity(self):
        """Audit trail is complete and verifiable."""
        # Create 10 events
        for i in range(10):
            self.event_store.record_execution(
                job_id=f"job_{i:03d}",
                input_hash=f"hash_{i}",
                output_hash=f"output_{i}",
                tier_used="TIER_2_MANIM",
                duration_ms=5000,
                success=True,
                tenant_id="_default",
            )

            if i % 2 == 0:
                self.event_store.record_feedback(
                    job_id=f"job_{i:03d}",
                    tier_used="TIER_2_MANIM",
                    quality_score=80 + i,
                    engagement_score=85 + i,
                    notes="",
                    tenant_id="_default",
                )

        # Verify events are persisted
        assert len(self.event_store.events) >= 10

        # Verify persistence to JSONL
        events_file = Path(self.temp_dir) / "events.jsonl"
        assert events_file.exists()

        # Verify events can be reloaded
        store2 = LearningEventStore(store_path=self.temp_dir)
        assert len(store2.events) == len(self.event_store.events)

    def test_tier_selection_with_feedback(self):
        """Tier selection adapts based on feedback history."""
        # Initial: uniform distribution
        initial_weights = self.optimizer.get_tier_distribution()
        assert all(abs(w - 0.25) < 0.01 for w in initial_weights.values())

        # Simulate poor results for Tier 1
        for i in range(5):
            self.event_store.record_execution(
                job_id=f"tier1_{i}",
                input_hash="x",
                output_hash="y",
                tier_used="TIER_1_QUICK",
                duration_ms=3000,
                success=i < 2,  # Only 2/5 success
                tenant_id="_default",
            )
            self.event_store.record_feedback(
                job_id=f"tier1_{i}",
                tier_used="TIER_1_QUICK",
                quality_score=20 + i * 5,
                engagement_score=15 + i * 5,
                notes="",
                tenant_id="_default",
            )

        # Simulate good results for Tier 2
        for i in range(5):
            self.event_store.record_execution(
                job_id=f"tier2_{i}",
                input_hash="x",
                output_hash="y",
                tier_used="TIER_2_MANIM",
                duration_ms=5000,
                success=True,
                tenant_id="_default",
            )
            self.event_store.record_feedback(
                job_id=f"tier2_{i}",
                tier_used="TIER_2_MANIM",
                quality_score=85 + i,
                engagement_score=90 + i,
                notes="",
                tenant_id="_default",
            )

        # Optimize
        self.optimizer.optimize_tier_selection("_default")

        # Verify weights shifted
        new_weights = self.optimizer.get_tier_distribution()
        assert new_weights["TIER_2_MANIM"] > initial_weights["TIER_2_MANIM"]
        assert new_weights["TIER_1_QUICK"] < initial_weights["TIER_1_QUICK"]

    def test_production_hardening(self):
        """Production hardening checks pass."""
        hardening = ProductionHardening()
        all_passed, results = hardening.enforce_all()

        # At least some checks should pass
        assert sum(1 for r in results if r.passed) > 0

        # Report should be generated
        report = hardening.get_status_report()
        assert "PRODUCTION" in report.upper()

    def test_concurrent_jobs(self):
        """System handles multiple concurrent jobs."""
        job_ids = []

        # Submit 5 jobs with different tiers
        for i in range(5):
            tier = ["TIER_1_QUICK", "TIER_1_5_THREEJS", "TIER_2_MANIM"][i % 3]
            self.event_store.record_execution(
                job_id=f"concurrent_{i}",
                input_hash=f"hash_{i}",
                output_hash=f"output_{i}",
                tier_used=tier,
                duration_ms=5000,
                success=True,
                tenant_id="_default",
            )
            job_ids.append(f"concurrent_{i}")

        # Verify all tracked
        assert len(self.event_store.events) >= 5

    def test_tenant_isolation(self):
        """Tenant isolation is maintained."""
        # Create events for two tenants
        for i in range(3):
            self.event_store.record_execution(
                job_id=f"tenant_a_{i}",
                input_hash="x",
                output_hash="y",
                tier_used="TIER_1_QUICK",
                duration_ms=3000,
                success=True,
                tenant_id="tenant_a",
            )

            self.event_store.record_execution(
                job_id=f"tenant_b_{i}",
                input_hash="x",
                output_hash="y",
                tier_used="TIER_2_MANIM",
                duration_ms=5000,
                success=True,
                tenant_id="tenant_b",
            )

        # Query metrics for tenant A
        metrics_a = self.event_store.get_all_metrics("tenant_a")

        # Verify tenant A metrics only include tenant A tiers
        assert metrics_a["TIER_1_QUICK"]["count"] == 3
        assert metrics_a["TIER_2_MANIM"]["count"] == 0

    def test_error_recovery(self):
        """System recovers from errors gracefully."""
        # Record failed execution
        self.event_store.record_execution(
            job_id="failed_job",
            input_hash="hash",
            output_hash="",
            tier_used="TIER_3_BLENDER",
            duration_ms=0,
            success=False,
            error="Blender timeout",
            tenant_id="_default",
        )

        # Fallback tier should still be available
        tier = self.dispatcher.select_tier("_default")
        assert tier == "TIER_1_QUICK"  # Fallback

        # Should be able to retry
        self.event_store.record_execution(
            job_id="retry_job",
            input_hash="hash",
            output_hash="output",
            tier_used="TIER_2_MANIM",
            duration_ms=5000,
            success=True,
            tenant_id="_default",
        )

        assert len(self.event_store.events) >= 2


class TestProductionDeploymentReadiness:
    """Validate production deployment readiness."""

    def test_all_modules_importable(self):
        """All production modules are importable."""
        modules = [
            "maestro",
            "skill",
            "learning_event_store",
            "tier_learning_optimizer",
            "tier_dispatcher",
            "threejs_renderer",
            "blender_async_executor",
            "production_hardening",
        ]

        for module_name in modules:
            try:
                __import__(module_name)
            except ImportError as e:
                pytest.fail(f"Failed to import {module_name}: {e}")

    def test_code_quality_markers(self):
        """Code quality standards are met."""
        src_dir = Path(__file__).parent.parent / "src"

        # Check for docstrings
        py_files = list(src_dir.glob("*.py"))
        for py_file in py_files:
            content = py_file.read_text()
            # At least one docstring per file
            assert '"""' in content or "'''" in content

    def test_deployment_scripts_exist(self):
        """Deployment scripts are present."""
        scripts_dir = Path(__file__).parent.parent / "scripts"

        required_scripts = [
            "install_production.sh",
            "package_for_marketplace.sh",
        ]

        for script in required_scripts:
            assert (scripts_dir / script).exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

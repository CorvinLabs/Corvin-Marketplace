"""Phase 2 Tests — Learning Loop Infrastructure

Tests for ADR-0314 integration:
- Event store (execution + feedback)
- Tier metrics aggregation
- Learning optimizer
- Tier weight optimization
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime

# Adjust path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from learning_event_store import LearningEventStore, ExecutionEvent, FeedbackEvent
from tier_learning_optimizer import TierLearningOptimizer


class TestLearningEventStore:
    """Test event storage and retrieval."""

    def setup_method(self):
        """Create temp store for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = LearningEventStore(store_path=self.temp_dir)

    def test_record_execution_event(self):
        """Record execution event."""
        event_id = self.store.record_execution(
            job_id="job_001",
            input_hash="abc123",
            output_hash="def456",
            tier_used="TIER_2_MANIM",
            duration_ms=5000,
            success=True,
            tenant_id="_default",
        )

        assert event_id == "exec_evt_job_001"
        assert len(self.store.events) == 1
        assert self.store.events[0]["job_id"] == "job_001"
        assert self.store.events[0]["tier_used"] == "TIER_2_MANIM"

    def test_record_feedback_event(self):
        """Record feedback event."""
        event_id = self.store.record_feedback(
            job_id="job_001",
            tier_used="TIER_2_MANIM",
            quality_score=85,
            engagement_score=90,
            notes="Great quality!",
            tenant_id="_default",
        )

        assert event_id == "fb_evt_job_001"
        assert len(self.store.events) == 1
        assert self.store.events[0]["quality_score"] == 85
        assert self.store.events[0]["engagement_score"] == 90

    def test_get_tier_metrics(self):
        """Aggregate metrics by tier."""
        # Record 5 execution events for TIER_2_MANIM
        for i in range(5):
            self.store.record_execution(
                job_id=f"job_{i:03d}",
                input_hash=f"hash_{i}",
                output_hash=f"output_{i}",
                tier_used="TIER_2_MANIM",
                duration_ms=5000 + i * 1000,
                success=(i < 4),  # 4 success, 1 failure
                tenant_id="_default",
            )

        # Record feedback for 3 of them
        for i in range(3):
            self.store.record_feedback(
                job_id=f"job_{i:03d}",
                tier_used="TIER_2_MANIM",
                quality_score=80 + i * 5,
                engagement_score=85 + i * 3,
                notes="",
                tenant_id="_default",
            )

        metrics = self.store.get_tier_metrics("TIER_2_MANIM", "_default")

        assert metrics["tier"] == "TIER_2_MANIM"
        assert metrics["count"] == 5
        assert metrics["success_rate"] == 0.8  # 4/5
        assert metrics["feedback_count"] == 3
        assert metrics["avg_quality"] == 85  # (80 + 85 + 90) / 3

    def test_get_all_metrics(self):
        """Get metrics for all tiers."""
        tiers = ["TIER_1_QUICK", "TIER_1_5_THREEJS", "TIER_2_MANIM", "TIER_3_BLENDER"]

        # Record 2 events per tier
        for tier in tiers:
            for i in range(2):
                self.store.record_execution(
                    job_id=f"{tier}_{i}",
                    input_hash=f"hash",
                    output_hash=f"output",
                    tier_used=tier,
                    duration_ms=5000,
                    success=True,
                    tenant_id="_default",
                )

        metrics = self.store.get_all_metrics("_default")

        assert len(metrics) == 4
        for tier in tiers:
            assert metrics[tier]["count"] == 2
            assert metrics[tier]["success_rate"] == 1.0

    def test_persistence_to_jsonl(self):
        """Events persist to JSONL file."""
        self.store.record_execution(
            job_id="job_001",
            input_hash="abc",
            output_hash="def",
            tier_used="TIER_1_QUICK",
            duration_ms=3000,
            success=True,
            tenant_id="_default",
        )

        # Verify file was written
        events_file = Path(self.temp_dir) / "events.jsonl"
        assert events_file.exists()

        # Load and verify
        with open(events_file) as f:
            line = f.readline()
            event = json.loads(line)
            assert event["job_id"] == "job_001"

    def test_load_events_from_disk(self):
        """Load events from existing JSONL file."""
        # Create a pre-existing JSONL file
        events_file = Path(self.temp_dir) / "events.jsonl"
        event_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": "skill_executed",
            "job_id": "preexisting",
            "tier_used": "TIER_2_MANIM",
            "success": True,
            "tenant_id": "_default",
        }
        with open(events_file, "w") as f:
            f.write(json.dumps(event_data) + "\n")

        # Create new store pointing to same dir
        store2 = LearningEventStore(store_path=self.temp_dir)
        assert len(store2.events) == 1
        assert store2.events[0]["job_id"] == "preexisting"

    def test_feedback_score_clamping(self):
        """Feedback scores are clamped to [0, 100]."""
        # Try to record with out-of-range scores
        self.store.record_feedback(
            job_id="job_001",
            tier_used="TIER_1_QUICK",
            quality_score=150,  # Out of range
            engagement_score=-10,  # Out of range
            notes="test",
            tenant_id="_default",
        )

        event = self.store.events[0]
        assert event["quality_score"] == 100  # Clamped to max
        assert event["engagement_score"] == 0  # Clamped to min


class TestTierLearningOptimizer:
    """Test tier selection learning."""

    def setup_method(self):
        """Create temp store + optimizer."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = LearningEventStore(store_path=self.temp_dir)
        self.optimizer = TierLearningOptimizer(
            self.store,
            config_path=str(Path(self.temp_dir) / "tier-weights.json"),
        )

    def test_initial_weights_uniform(self):
        """Initial weights are uniform."""
        weights = self.optimizer.get_tier_distribution()
        expected = {
            "TIER_1_QUICK": 0.25,
            "TIER_1_5_THREEJS": 0.25,
            "TIER_2_MANIM": 0.25,
            "TIER_3_BLENDER": 0.25,
        }
        for tier, weight in expected.items():
            assert abs(weights[tier] - weight) < 0.01

    def test_optimize_tier_weights(self):
        """Weights update based on metrics."""
        # Simulate success for TIER_2_MANIM
        for i in range(10):
            self.store.record_execution(
                job_id=f"manim_{i}",
                input_hash="x",
                output_hash="y",
                tier_used="TIER_2_MANIM",
                duration_ms=4000,
                success=True,
                tenant_id="_default",
            )

        # Simulate failures for TIER_3_BLENDER
        for i in range(5):
            self.store.record_execution(
                job_id=f"blender_{i}",
                input_hash="x",
                output_hash="y",
                tier_used="TIER_3_BLENDER",
                duration_ms=10000,
                success=False,
                tenant_id="_default",
            )

        # Optimize
        self.optimizer.optimize_tier_selection("_default")

        weights = self.optimizer.get_tier_distribution()

        # TIER_2_MANIM should have higher weight than TIER_3_BLENDER
        assert weights["TIER_2_MANIM"] > weights["TIER_3_BLENDER"]

    def test_recommend_tier(self):
        """Recommend tier with highest weight."""
        # Manually set weights
        self.optimizer.weights.TIER_2_MANIM = 0.5
        self.optimizer.weights.TIER_1_QUICK = 0.2
        self.optimizer.weights.TIER_1_5_THREEJS = 0.2
        self.optimizer.weights.TIER_3_BLENDER = 0.1

        recommended = self.optimizer.recommend_tier()
        assert recommended == "TIER_2_MANIM"

    def test_weights_normalized(self):
        """Weights always sum to ~1.0 after optimization."""
        # Record mixed results
        tiers = ["TIER_1_QUICK", "TIER_1_5_THREEJS", "TIER_2_MANIM", "TIER_3_BLENDER"]
        for i, tier in enumerate(tiers):
            for j in range(i + 1):  # Different counts per tier
                self.store.record_execution(
                    job_id=f"{tier}_{j}",
                    input_hash="x",
                    output_hash="y",
                    tier_used=tier,
                    duration_ms=5000,
                    success=True,
                    tenant_id="_default",
                )

        self.optimizer.optimize_tier_selection("_default")
        weights = self.optimizer.get_tier_distribution()

        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01  # Within rounding error

    def test_persistence(self):
        """Weights persist to disk and reload."""
        # Set custom weights
        self.optimizer.weights.TIER_2_MANIM = 0.6
        self.optimizer.weights.TIER_1_QUICK = 0.4
        self.optimizer._save_weights()

        # Load in new optimizer
        optimizer2 = TierLearningOptimizer(
            self.store,
            config_path=str(Path(self.temp_dir) / "tier-weights.json"),
        )

        weights = optimizer2.get_tier_distribution()
        assert abs(weights["TIER_2_MANIM"] - 0.6) < 0.01


class TestCompletePhase2Learning:
    """Integration test: complete learning loop."""

    def setup_method(self):
        """Setup for complete test."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = LearningEventStore(store_path=self.temp_dir)
        self.optimizer = TierLearningOptimizer(
            self.store,
            config_path=str(Path(self.temp_dir) / "tier-weights.json"),
        )

    def test_learning_loop_full_cycle(self):
        """Complete learning cycle: render → feedback → optimize."""
        # Phase 1: Initial renders (mixed quality)
        for tier_idx, tier in enumerate(["TIER_1_QUICK", "TIER_2_MANIM", "TIER_3_BLENDER"]):
            for job_num in range(3):
                # Execute
                event_id = self.store.record_execution(
                    job_id=f"{tier}_{job_num}",
                    input_hash="hash",
                    output_hash="output",
                    tier_used=tier,
                    duration_ms=5000 + tier_idx * 2000,
                    success=(job_num < 2),  # 2 success, 1 failure per tier
                    tenant_id="_default",
                )

                # Provide feedback
                self.store.record_feedback(
                    job_id=f"{tier}_{job_num}",
                    tier_used=tier,
                    quality_score=70 + tier_idx * 10,  # Higher tier = higher quality
                    engagement_score=75 + tier_idx * 10,
                    notes="",
                    tenant_id="_default",
                )

        # Phase 2: Optimize weights
        self.optimizer.optimize_tier_selection("_default")

        weights = self.optimizer.get_tier_distribution()

        # TIER_3_BLENDER should get highest weight (highest quality feedback)
        assert weights["TIER_3_BLENDER"] > weights["TIER_1_QUICK"]

        # Phase 3: Recommend and verify
        recommended = self.optimizer.recommend_tier()
        assert recommended == "TIER_3_BLENDER"

    def test_feedback_accumulation(self):
        """Feedback accumulates and drives optimization."""
        # Render with TIER_1_QUICK
        for i in range(5):
            self.store.record_execution(
                job_id=f"quick_{i}",
                input_hash="x",
                output_hash="y",
                tier_used="TIER_1_QUICK",
                duration_ms=3000,
                success=True,
                tenant_id="_default",
            )
            # Poor feedback
            self.store.record_feedback(
                job_id=f"quick_{i}",
                tier_used="TIER_1_QUICK",
                quality_score=30,  # Low quality
                engagement_score=20,
                notes="",
                tenant_id="_default",
            )

        # Render with TIER_2_MANIM
        for i in range(5):
            self.store.record_execution(
                job_id=f"manim_{i}",
                input_hash="x",
                output_hash="y",
                tier_used="TIER_2_MANIM",
                duration_ms=5000,
                success=True,
                tenant_id="_default",
            )
            # Good feedback
            self.store.record_feedback(
                job_id=f"manim_{i}",
                tier_used="TIER_2_MANIM",
                quality_score=90,  # High quality
                engagement_score=95,
                notes="",
                tenant_id="_default",
            )

        self.optimizer.optimize_tier_selection("_default")

        weights = self.optimizer.get_tier_distribution()
        assert weights["TIER_2_MANIM"] > weights["TIER_1_QUICK"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

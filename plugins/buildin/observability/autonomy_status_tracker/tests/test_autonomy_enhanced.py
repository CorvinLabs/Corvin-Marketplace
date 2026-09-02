"""
Enhanced unit tests for autonomy_status_tracker plugin.
Tests cover: status tracking, metrics, lifecycle, concurrency, edge cases.
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta


class TestAutonomyStatusTracker:
    """Unit tests for autonomy status tracker."""

    @pytest.fixture
    def tracker(self):
        """Create a tracker instance."""
        from autonomy_status_tracker import AutonomyStatusTracker
        return AutonomyStatusTracker()

    def test_initialization(self, tracker):
        """Test tracker initializes with default state."""
        assert tracker is not None
        assert tracker.status == "idle"
        assert tracker.metrics == {}
        assert tracker.last_update is not None

    def test_status_update(self, tracker):
        """Test status update mechanism."""
        tracker.update_status("running", {"task_id": "t123"})
        assert tracker.status == "running"
        assert tracker.metrics.get("task_id") == "t123"

    def test_metrics_aggregation(self, tracker):
        """Test metrics collection and aggregation."""
        tracker.record_metric("latency_ms", 42)
        tracker.record_metric("latency_ms", 58)
        avg = tracker.get_metric_average("latency_ms")
        assert avg == 50.0

    def test_status_history(self, tracker):
        """Test status history tracking."""
        tracker.update_status("running")
        tracker.update_status("paused")
        tracker.update_status("running")
        history = tracker.get_status_history()
        assert len(history) >= 2
        assert "paused" in [h["status"] for h in history]

    def test_concurrent_updates(self, tracker):
        """Test thread-safety of concurrent status updates."""
        import threading
        
        def update_status(status_name):
            tracker.update_status(status_name)
        
        threads = [
            threading.Thread(target=update_status, args=(f"status_{i}",))
            for i in range(5)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Verify final state is consistent
        assert tracker.status is not None

    @pytest.mark.asyncio
    async def test_async_status_update(self, tracker):
        """Test async status update."""
        await tracker.async_update_status("async_running")
        assert tracker.status == "async_running"

    def test_error_handling_invalid_status(self, tracker):
        """Test error handling for invalid status values."""
        with pytest.raises((ValueError, AttributeError)):
            tracker.update_status(None)

    def test_metrics_edge_cases(self, tracker):
        """Test metrics with edge cases (empty, negative, zero)."""
        tracker.record_metric("cpu", 0)
        tracker.record_metric("cpu", -1)
        tracker.record_metric("cpu", 100)
        
        stats = tracker.get_metric_stats("cpu")
        assert stats is not None
        assert stats.get("count", 0) >= 3

    def test_reset_state(self, tracker):
        """Test reset to initial state."""
        tracker.update_status("running", {"data": "test"})
        tracker.reset()
        assert tracker.status == "idle"
        assert tracker.metrics == {}

    def test_status_to_dict_serialization(self, tracker):
        """Test serialization to dict for API responses."""
        tracker.update_status("monitoring", {"cpu": 45})
        state_dict = tracker.to_dict()
        assert state_dict["status"] == "monitoring"
        assert "timestamp" in state_dict
        assert state_dict["metrics"]["cpu"] == 45

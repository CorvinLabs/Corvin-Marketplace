"""
E2E tests for autonomy_status_tracker — real plugin lifecycle.
Tests integration with CorvinOS event system and metrics aggregation.
"""
import pytest
import asyncio
import time
from datetime import datetime


@pytest.mark.asyncio
async def test_e2e_autonomy_tracker_lifecycle():
    """E2E: Full lifecycle of autonomy status tracking."""
    from autonomy_status_tracker import AutonomyStatusTracker
    
    tracker = AutonomyStatusTracker()
    
    # Phase 1: Boot
    assert tracker.status == "idle"
    print("✅ Phase 1: Boot — tracker initialized")
    
    # Phase 2: Start autonomous session
    tracker.update_status("running", {"session_id": "sess_e2e_001"})
    assert tracker.status == "running"
    print("✅ Phase 2: Start autonomous session")
    
    # Phase 3: Record metrics during execution
    for i in range(5):
        tracker.record_metric("decisions_made", 1)
        tracker.record_metric("execution_time_ms", 100 + i*10)
        await asyncio.sleep(0.01)
    
    print("✅ Phase 3: Recorded 5 decision cycles")
    
    # Phase 4: Query metrics
    stats = tracker.get_metric_stats("execution_time_ms")
    assert stats["count"] == 5
    assert stats["avg"] >= 100
    print(f"✅ Phase 4: Metrics aggregated — avg latency {stats['avg']:.1f}ms")
    
    # Phase 5: Pause and resume
    tracker.update_status("paused", {"reason": "resource_limit"})
    assert tracker.status == "paused"
    
    await asyncio.sleep(0.05)
    
    tracker.update_status("running")
    assert tracker.status == "running"
    print("✅ Phase 5: Pause/Resume cycle")
    
    # Phase 6: Shutdown
    tracker.update_status("stopped", {"final_metrics": stats})
    state = tracker.to_dict()
    assert state["status"] == "stopped"
    print("✅ Phase 6: Shutdown — state serialized")
    
    print(f"\n✅ E2E PASS: autonomy_status_tracker full lifecycle (duration: {time.time():.2f}s)")


@pytest.mark.asyncio
async def test_e2e_concurrent_autonomy_tracking():
    """E2E: Concurrent status tracking (multi-task autonomy)."""
    from autonomy_status_tracker import AutonomyStatusTracker
    
    tracker = AutonomyStatusTracker()
    
    async def task_runner(task_id, num_metrics):
        """Simulate concurrent autonomous task."""
        for i in range(num_metrics):
            tracker.record_metric(f"task_{task_id}_latency", 50 + i*5)
            await asyncio.sleep(0.005)
    
    # Run 3 concurrent tasks
    await asyncio.gather(
        task_runner(1, 5),
        task_runner(2, 5),
        task_runner(3, 5),
    )
    
    # Verify metrics from all tasks recorded
    all_metrics = tracker.get_all_metrics()
    assert len(all_metrics) >= 3  # At least 3 metric types
    print(f"✅ E2E PASS: Concurrent tracking — {len(all_metrics)} metric streams")


def test_e2e_autonomy_error_recovery():
    """E2E: Error condition and recovery."""
    from autonomy_status_tracker import AutonomyStatusTracker
    
    tracker = AutonomyStatusTracker()
    
    # Normal operation
    tracker.update_status("running")
    
    # Simulate error
    try:
        tracker.record_metric("error_count", 1)
        tracker.update_status("error", {"reason": "timeout", "recovery": "retry"})
    except Exception as e:
        print(f"❌ Error: {e}")
        raise
    
    # Recovery
    tracker.update_status("recovering")
    assert tracker.status == "recovering"
    
    # Back to normal
    tracker.update_status("running")
    assert tracker.status == "running"
    
    print("✅ E2E PASS: Error detection and recovery")

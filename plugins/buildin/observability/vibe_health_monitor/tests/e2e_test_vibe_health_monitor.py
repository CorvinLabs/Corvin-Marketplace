"""
End-to-end test for VibeHealthMonitor plugin.

Verifies:
- Real plugin lifecycle (init → health recording → health checks → shutdown)
- Concurrent session health tracking
- Health status contract validation
- Overall health aggregation and state transitions
- Session health data integrity
- Performance SLA compliance (<1ms per operation)
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock
import sys

# Mock plugin base
mock_plugin_base = MagicMock()
mock_plugin_base.DeterministicPlugin = object
mock_plugin_base.PluginTier = MagicMock()
mock_plugin_base.PluginTier.GENERAL = "general"
mock_protocol = MagicMock()
mock_protocol.HealthStatus = MagicMock(return_value=MagicMock(ok=True, message="OK"))

sys.modules['corvin_plugins'] = MagicMock()
sys.modules['corvin_plugins.plugin_base'] = mock_plugin_base
sys.modules['corvin_plugins.protocol'] = mock_protocol

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/vibe_health_monitor/src')


@pytest.fixture
async def monitor():
    """Fixture providing initialized health monitor plugin."""
    from vibe_health_monitor import VibeHealthMonitor
    mon = VibeHealthMonitor()
    ctx = MagicMock()
    ctx.tenant_id = "default"
    await mon.initialize(ctx)
    yield mon
    await mon.shutdown()


@pytest.mark.asyncio
async def test_e2e_plugin_lifecycle(monitor):
    """Test complete plugin lifecycle."""
    assert monitor is not None
    assert monitor.get_tier() == "general"
    assert monitor.get_max_latency_ms() == 1
    await monitor.shutdown()


@pytest.mark.asyncio
async def test_e2e_record_single_session(monitor):
    """Test recording and retrieving a single session health end-to-end."""
    start = datetime.utcnow()
    await monitor.record_session_health("session_1", health_score=95.0, state="active", memory_mb=256)
    elapsed_ms = (datetime.utcnow() - start).total_seconds() * 1000

    assert elapsed_ms < 1.0  # <1ms SLA

    session_health = await monitor.get_session_health("session_1")
    assert session_health is not None
    assert session_health["health_score"] == 95.0
    assert session_health["state"] == "active"
    assert session_health["memory_mb"] == 256


@pytest.mark.asyncio
async def test_e2e_concurrent_session_recording(monitor):
    """Test concurrent session health recording."""
    tasks = []
    for i in range(20):
        task = monitor.record_session_health(
            f"session_{i}",
            health_score=80.0 + (i * 1.0),
            state="running",
            memory_mb=256 + (i * 10)
        )
        tasks.append(task)

    await asyncio.gather(*tasks)

    overall = await monitor.get_overall_health()
    assert overall["total_sessions"] == 20


@pytest.mark.asyncio
async def test_e2e_health_status_contract(monitor):
    """Test HealthStatus contract."""
    await monitor.record_session_health(
        "session_1",
        health_score=95.0,
        state="healthy",
        memory_mb=256
    )

    health = await monitor.on_health_check()
    assert health is not None
    assert hasattr(health, 'ok')
    assert hasattr(health, 'message')
    assert health.ok is True


@pytest.mark.asyncio
async def test_e2e_state_persistence_across_operations(monitor):
    """Test state persistence across multiple operations."""
    # First batch
    await monitor.record_session_health("session_1", 95.0, "active", 256)
    report1 = await monitor.get_overall_health()
    count1 = report1["total_sessions"]

    # Second batch
    for i in range(2, 6):
        await monitor.record_session_health(f"session_{i}", 90.0, "running", 256)

    report2 = await monitor.get_overall_health()
    count2 = report2["total_sessions"]

    assert count2 == 5
    assert count2 > count1


@pytest.mark.asyncio
async def test_e2e_healthy_overall_state(monitor):
    """Test overall health aggregation in healthy state."""
    sessions_data = [
        ("session_1", 95.0),
        ("session_2", 90.0),
        ("session_3", 88.0),
        ("session_4", 92.0),
    ]

    for session_id, health_score in sessions_data:
        await monitor.record_session_health(session_id, health_score, "running", 256)

    overall = await monitor.get_overall_health()
    assert overall["status"] == "healthy"
    assert overall["total_sessions"] == 4
    assert overall["healthy_sessions"] == 4
    assert overall["avg_health_score"] > 85.0


@pytest.mark.asyncio
async def test_e2e_degraded_health_state(monitor):
    """Test overall health in degraded state."""
    sessions_data = [
        ("session_1", 65.0),
        ("session_2", 70.0),
        ("session_3", 75.0),
    ]

    for session_id, health_score in sessions_data:
        await monitor.record_session_health(session_id, health_score, "running", 256)

    overall = await monitor.get_overall_health()
    assert overall["status"] == "degraded"
    assert 50.0 <= overall["avg_health_score"] < 80.0


@pytest.mark.asyncio
async def test_e2e_unhealthy_state(monitor):
    """Test overall health in unhealthy state."""
    sessions_data = [
        ("session_1", 25.0),
        ("session_2", 35.0),
    ]

    for session_id, health_score in sessions_data:
        await monitor.record_session_health(session_id, health_score, "running", 256)

    overall = await monitor.get_overall_health()
    assert overall["status"] == "unhealthy"
    assert overall["avg_health_score"] < 50.0


@pytest.mark.asyncio
async def test_e2e_memory_aggregation(monitor):
    """Test total memory aggregation across sessions."""
    sessions_data = [
        ("session_1", 90.0, 256),
        ("session_2", 85.0, 512),
        ("session_3", 88.0, 768),
    ]

    for session_id, health_score, memory_mb in sessions_data:
        await monitor.record_session_health(session_id, health_score, "running", memory_mb)

    overall = await monitor.get_overall_health()
    assert overall["total_memory_mb"] == pytest.approx(1536.0, abs=0.1)


@pytest.mark.asyncio
async def test_e2e_performance_sla(monitor):
    """Test performance against SLA (<1ms per operation)."""
    import time

    start = time.perf_counter()
    for i in range(100):
        await monitor.record_session_health(
            f"session_{i}",
            health_score=85.0 + (i * 0.1),
            state="running",
            memory_mb=256
        )
    total_ms = (time.perf_counter() - start) * 1000
    avg_per_op_ms = total_ms / 100

    assert avg_per_op_ms < 1.0  # <1ms SLA


@pytest.mark.asyncio
async def test_e2e_health_snapshot(monitor):
    """Test complete health snapshot retrieval."""
    for i in range(15):
        await monitor.record_session_health(
            f"session_{i}",
            health_score=85.0 + (i * 0.5),
            state="running",
            memory_mb=256 + (i * 5)
        )

    snapshot = await monitor.get_diagnostics()
    assert "status" in snapshot
    assert "avg_health_score" in snapshot
    assert "healthy_sessions" in snapshot
    assert snapshot["total_sessions"] == 15


@pytest.mark.asyncio
async def test_e2e_error_recovery(monitor):
    """Test error handling and recovery."""
    # Record normal health
    await monitor.record_session_health("session_1", 95.0, "running", 256)

    # Try edge case values (health score clamping)
    await monitor.record_session_health("session_2", 150.0, "running", 256)  # Should clamp to 100

    # Retrieve to verify clamping
    health = await monitor.get_session_health("session_2")
    assert health["health_score"] == 100.0  # Clamped upper bound

    # Record negative health (should clamp to 0)
    await monitor.record_session_health("session_3", -50.0, "running", 256)
    health = await monitor.get_session_health("session_3")
    assert health["health_score"] == 0.0  # Clamped lower bound

    # Should recover gracefully
    overall = await monitor.get_overall_health()
    assert overall["total_sessions"] >= 3


@pytest.mark.asyncio
async def test_e2e_session_health_update(monitor):
    """Test session health updates overwrite previous records."""
    # Initial record
    await monitor.record_session_health("session_1", 50.0, "running", 256)
    health1 = await monitor.get_session_health("session_1")
    assert health1["health_score"] == 50.0

    # Update same session
    await monitor.record_session_health("session_1", 90.0, "running", 512)
    health2 = await monitor.get_session_health("session_1")
    assert health2["health_score"] == 90.0
    assert health2["memory_mb"] == 512


@pytest.mark.asyncio
async def test_e2e_health_history_buffering(monitor):
    """Test health history buffer respects capacity."""
    for i in range(1500):
        await monitor.record_session_health(
            f"session_{i % 10}",
            health_score=85.0,
            state="running",
            memory_mb=256
        )

    # History should be bounded (maxlen=1000)
    assert len(monitor.health_history) <= 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

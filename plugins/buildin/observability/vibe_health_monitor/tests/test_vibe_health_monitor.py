"""
Comprehensive unit tests for VibeHealthMonitor plugin.

Tests session health recording, health score calculation, memory tracking,
error monitoring, and overall system health assessment.
"""

import pytest
import asyncio
from unittest.mock import MagicMock
import sys



from vibe_health_monitor import VibeHealthMonitor, SessionHealth


@pytest.fixture
async def monitor():
    """Fixture providing initialized monitor."""
    monitor = VibeHealthMonitor()
    await monitor.initialize(MagicMock())
    yield monitor
    await monitor.shutdown()


@pytest.mark.asyncio
async def test_initialization():
    """Test plugin initializes correctly."""
    monitor = VibeHealthMonitor()
    assert monitor.sessions == {}
    assert monitor.health_history.__class__.__name__ == "deque"
    await monitor.initialize(MagicMock())
    assert monitor.start_time is not None


@pytest.mark.asyncio
async def test_record_single_session_health(monitor):
    """Test recording health for a single session."""
    await monitor.record_session_health("session_1", health_score=95.0, state="active", memory_mb=256)

    assert "session_1" in monitor.sessions
    assert len(monitor.health_history) == 1

    session_health = monitor.sessions["session_1"]
    assert session_health.health_score == 95.0
    assert session_health.state == "active"
    assert session_health.memory_mb == 256


@pytest.mark.asyncio
async def test_record_session_health_with_errors(monitor):
    """Test recording session health with error count."""
    await monitor.record_session_health("session_1", health_score=85.0, state="running", memory_mb=512, errors=5)

    session_health = monitor.sessions["session_1"]
    assert session_health.error_count == 5


@pytest.mark.asyncio
async def test_health_score_clamping_upper(monitor):
    """Test health score clamping at upper bound."""
    await monitor.record_session_health("session_1", health_score=150.0, state="running", memory_mb=256)

    health = await monitor.get_session_health("session_1")
    assert health["health_score"] == 100.0


@pytest.mark.asyncio
async def test_health_score_clamping_lower(monitor):
    """Test health score clamping at lower bound."""
    await monitor.record_session_health("session_1", health_score=-50.0, state="running", memory_mb=256)

    health = await monitor.get_session_health("session_1")
    assert health["health_score"] == 0.0


@pytest.mark.asyncio
async def test_get_session_health(monitor):
    """Test retrieving session health."""
    await monitor.record_session_health("session_1", 85.0, "running", 512, errors=2)

    health = await monitor.get_session_health("session_1")

    assert health is not None
    assert health["session_id"] == "session_1"
    assert health["health_score"] == 85.0
    assert health["state"] == "running"
    assert health["memory_mb"] == 512
    assert health["errors"] == 2
    assert "timestamp" in health


@pytest.mark.asyncio
async def test_get_nonexistent_session_health(monitor):
    """Test retrieving health for nonexistent session."""
    health = await monitor.get_session_health("nonexistent")
    assert health is None


@pytest.mark.asyncio
async def test_multiple_sessions(monitor):
    """Test tracking multiple sessions."""
    for i in range(1, 4):
        await monitor.record_session_health(f"session_{i}", 80.0 + (i * 5), "running", 256 * i)

    assert len(monitor.sessions) == 3
    assert "session_1" in monitor.sessions
    assert "session_2" in monitor.sessions
    assert "session_3" in monitor.sessions


@pytest.mark.asyncio
async def test_get_overall_health_empty(monitor):
    """Test overall health when no sessions recorded."""
    overall = await monitor.get_overall_health()

    assert overall["status"] == "unknown"
    assert overall["avg_health_score"] == 0.0
    assert overall["healthy_sessions"] == 0


@pytest.mark.asyncio
async def test_get_overall_health_healthy_all(monitor):
    """Test overall health when all sessions are healthy."""
    await monitor.record_session_health("session_1", 95.0, "running", 256)
    await monitor.record_session_health("session_2", 90.0, "running", 256)
    await monitor.record_session_health("session_3", 85.0, "running", 256)

    overall = await monitor.get_overall_health()

    assert overall["status"] == "healthy"
    assert overall["healthy_sessions"] == 3
    assert overall["total_sessions"] == 3
    assert overall["avg_health_score"] > 85.0


@pytest.mark.asyncio
async def test_get_overall_health_degraded(monitor):
    """Test overall health in degraded state."""
    await monitor.record_session_health("session_1", 60.0, "running", 256)
    await monitor.record_session_health("session_2", 70.0, "running", 256)

    overall = await monitor.get_overall_health()

    assert overall["status"] == "degraded"
    assert 50.0 <= overall["avg_health_score"] < 80.0


@pytest.mark.asyncio
async def test_get_overall_health_unhealthy(monitor):
    """Test overall health in unhealthy state."""
    await monitor.record_session_health("session_1", 30.0, "running", 256)
    await monitor.record_session_health("session_2", 40.0, "running", 256)

    overall = await monitor.get_overall_health()

    assert overall["status"] == "unhealthy"
    assert overall["avg_health_score"] < 50.0


@pytest.mark.asyncio
async def test_total_memory_calculation(monitor):
    """Test total memory aggregation."""
    await monitor.record_session_health("session_1", 90.0, "running", 256)
    await monitor.record_session_health("session_2", 85.0, "running", 512)
    await monitor.record_session_health("session_3", 80.0, "running", 768)

    overall = await monitor.get_overall_health()

    assert overall["total_memory_mb"] == pytest.approx(1536.0, abs=0.1)


@pytest.mark.asyncio
async def test_healthy_sessions_count(monitor):
    """Test counting healthy sessions (score >= 80)."""
    await monitor.record_session_health("session_1", 90.0, "running", 256)
    await monitor.record_session_health("session_2", 85.0, "running", 256)
    await monitor.record_session_health("session_3", 70.0, "running", 256)
    await monitor.record_session_health("session_4", 75.0, "running", 256)

    overall = await monitor.get_overall_health()

    assert overall["healthy_sessions"] == 2


@pytest.mark.asyncio
async def test_health_history_capacity(monitor):
    """Test health history buffer capacity (maxlen=1000)."""
    for i in range(1500):
        await monitor.record_session_health(f"session_{i % 10}", 90.0, "running", 256)

    assert len(monitor.health_history) <= 1000


@pytest.mark.asyncio
async def test_get_diagnostics(monitor):
    """Test unified diagnostics interface."""
    await monitor.record_session_health("session_1", 90.0, "running", 256)

    diagnostics = await monitor.get_diagnostics()

    assert "status" in diagnostics
    assert "avg_health_score" in diagnostics
    assert "healthy_sessions" in diagnostics


@pytest.mark.asyncio
async def test_session_health_update_overwrites(monitor):
    """Test that updating a session overwrites previous record."""
    await monitor.record_session_health("session_1", 50.0, "running", 256)
    assert monitor.sessions["session_1"].health_score == 50.0

    await monitor.record_session_health("session_1", 90.0, "running", 512)
    assert monitor.sessions["session_1"].health_score == 90.0
    assert monitor.sessions["session_1"].memory_mb == 512


@pytest.mark.asyncio
async def test_health_check_healthy_state(monitor):
    """Test health check when system is healthy."""
    await monitor.record_session_health("session_1", 95.0, "running", 256)
    await monitor.record_session_health("session_2", 90.0, "running", 256)

    health = await monitor.on_health_check()
    assert health.ok is True
    assert "healthy" in health.message.lower()


@pytest.mark.asyncio
async def test_health_check_unhealthy_state(monitor):
    """Test health check when system is unhealthy."""
    await monitor.record_session_health("session_1", 30.0, "running", 256)

    health = await monitor.on_health_check()
    assert health.ok is False


@pytest.mark.asyncio
async def test_concurrent_session_recording(monitor):
    """Test concurrent session health recording."""
    async def record_health(session_id, count):
        for i in range(count):
            await monitor.record_session_health(session_id, 80.0 + i, "running", 256)

    await asyncio.gather(
        record_health("session_1", 5),
        record_health("session_2", 5),
        record_health("session_3", 5),
    )

    assert len(monitor.sessions) == 3
    assert len(monitor.health_history) >= 15


@pytest.mark.asyncio
async def test_tier_property():
    """Test tier classification."""
    monitor = VibeHealthMonitor()
    assert monitor.get_tier() == "general"


@pytest.mark.asyncio
async def test_max_latency_requirement():
    """Test latency constraint."""
    monitor = VibeHealthMonitor()
    assert monitor.get_max_latency_ms() == 1


@pytest.mark.asyncio
async def test_shutdown_graceful(monitor):
    """Test graceful shutdown."""
    await monitor.shutdown()
    # No exception should be raised


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Comprehensive unit tests for HeartbeatMonitor plugin.

Tests heartbeat recording, stale detection, responsiveness scoring, and
health checking.
"""

import pytest
import asyncio
from unittest.mock import MagicMock
from datetime import datetime, timedelta
import sys



from heartbeat_monitor import HeartbeatMonitor


@pytest.fixture
async def monitor():
    """Fixture providing initialized monitor."""
    monitor = HeartbeatMonitor()
    await monitor.initialize(MagicMock())
    yield monitor
    await monitor.shutdown()


@pytest.mark.asyncio
async def test_initialization():
    """Test plugin initializes correctly."""
    monitor = HeartbeatMonitor()
    assert monitor.last_heartbeat is None
    assert monitor.heartbeat_history == []  # list, trimmed to the last 1000 records
    assert monitor.missed_beats == 0
    await monitor.initialize(MagicMock())
    assert monitor.start_time is not None


@pytest.mark.asyncio
async def test_record_single_heartbeat(monitor):
    """Test recording a single heartbeat."""
    await monitor.record_heartbeat("instance_1", latency_ms=1.5, healthy=True)

    assert monitor.last_heartbeat is not None
    assert len(monitor.heartbeat_history) == 1
    assert monitor.instance_id == "instance_1"


@pytest.mark.asyncio
async def test_record_heartbeat_healthy(monitor):
    """Test recording healthy heartbeat."""
    await monitor.record_heartbeat("instance_1", latency_ms=1.0, healthy=True)

    heartbeat = monitor.heartbeat_history[0]
    assert heartbeat.instance_id == "instance_1"
    assert heartbeat.healthy is True
    assert heartbeat.latency_ms == 1.0


@pytest.mark.asyncio
async def test_record_heartbeat_unhealthy(monitor):
    """Test recording unhealthy heartbeat."""
    await monitor.record_heartbeat("instance_1", latency_ms=2.0, healthy=False)

    heartbeat = monitor.heartbeat_history[0]
    assert heartbeat.healthy is False
    assert monitor.missed_beats == 1


@pytest.mark.asyncio
async def test_multiple_heartbeats_same_instance(monitor):
    """Test recording multiple heartbeats for same instance."""
    for i in range(5):
        await monitor.record_heartbeat("instance_1", latency_ms=1.0 + i, healthy=True)

    assert len(monitor.heartbeat_history) == 5
    assert monitor.missed_beats == 0


@pytest.mark.asyncio
async def test_mixed_healthy_unhealthy(monitor):
    """Test recording mix of healthy and unhealthy heartbeats."""
    heartbeats = [True, False, True, False, True]

    for healthy in heartbeats:
        await monitor.record_heartbeat("instance_1", latency_ms=1.0, healthy=healthy)

    assert len(monitor.heartbeat_history) == 5
    # missed_beats counts CONSECUTIVE misses (stale detection = 3 in a row);
    # the last pulse was healthy, so the streak is back to 0.
    assert monitor.missed_beats == 0


@pytest.mark.asyncio
async def test_missed_beats_tracking(monitor):
    """Test missed heartbeat counting."""
    await monitor.record_heartbeat("instance_1", latency_ms=1.0, healthy=False)
    await monitor.record_heartbeat("instance_1", latency_ms=1.0, healthy=False)
    await monitor.record_heartbeat("instance_1", latency_ms=1.0, healthy=False)

    assert monitor.missed_beats == 3


@pytest.mark.asyncio
async def test_is_instance_alive_fresh_heartbeat(monitor):
    """Test instance alive detection with fresh heartbeat."""
    await monitor.record_heartbeat("instance_1", latency_ms=1.0, healthy=True)
    alive = await monitor.is_instance_alive()
    assert alive is True


@pytest.mark.asyncio
async def test_is_instance_alive_no_heartbeat(monitor):
    """Test instance alive detection without heartbeat."""
    alive = await monitor.is_instance_alive()
    assert alive is False


@pytest.mark.asyncio
async def test_get_heartbeat_status(monitor):
    """Test retrieving heartbeat status."""
    await monitor.record_heartbeat("instance_1", latency_ms=2.0, healthy=True)
    status = await monitor.get_heartbeat_status()

    assert status is not None
    assert status["status"] == "alive"
    assert status["instance_id"] == "instance_1"
    assert "timestamp" in status


@pytest.mark.asyncio
async def test_heartbeat_history_capacity(monitor):
    """Test heartbeat history buffer capacity (maxlen=1000)."""
    for i in range(1500):
        await monitor.record_heartbeat("instance", latency_ms=1.0)

    # Buffer should not exceed max capacity
    assert len(monitor.heartbeat_history) <= 1000


@pytest.mark.asyncio
async def test_multiple_instances(monitor):
    """Test tracking multiple instances."""
    await monitor.record_heartbeat("instance_1", latency_ms=1.0)
    await monitor.record_heartbeat("instance_2", latency_ms=1.5)
    await monitor.record_heartbeat("instance_3", latency_ms=2.0)

    # Last recorded instance
    assert monitor.instance_id == "instance_3"
    assert len(monitor.heartbeat_history) == 3


@pytest.mark.asyncio
async def test_last_heartbeat_updated(monitor):
    """Test that last_heartbeat is updated."""
    await monitor.record_heartbeat("instance_1", latency_ms=1.0)
    first_time = monitor.last_heartbeat

    await asyncio.sleep(0.01)  # Small delay

    await monitor.record_heartbeat("instance_1", latency_ms=1.0)
    second_time = monitor.last_heartbeat

    assert second_time >= first_time


@pytest.mark.asyncio
async def test_high_latency_heartbeat(monitor):
    """Test recording heartbeat with high latency."""
    await monitor.record_heartbeat("instance_1", latency_ms=50.0, healthy=True)

    heartbeat = monitor.heartbeat_history[0]
    assert heartbeat.latency_ms == 50.0


@pytest.mark.asyncio
async def test_get_diagnostics(monitor):
    """Test unified diagnostics interface."""
    await monitor.record_heartbeat("instance_1", latency_ms=1.0)

    diagnostics = await monitor.get_diagnostics()

    assert "status" in diagnostics or "instance_id" in diagnostics


@pytest.mark.asyncio
async def test_health_check_alive(monitor):
    """Test health check when instance is alive."""
    await monitor.record_heartbeat("instance_1", latency_ms=1.0, healthy=True)

    health = await monitor.on_health_check()
    assert health.ok is True
    assert "instance" in health.message.lower() or "heartbeat" in health.message.lower()


@pytest.mark.asyncio
async def test_health_check_dead(monitor):
    """Test health check when no recent heartbeat."""
    health = await monitor.on_health_check()
    assert health.ok is False


@pytest.mark.asyncio
async def test_health_check_unhealthy_instance(monitor):
    """Test health check when instance reports unhealthy."""
    await monitor.record_heartbeat("instance_1", latency_ms=1.0, healthy=False)

    health = await monitor.on_health_check()
    assert health.ok is False


@pytest.mark.asyncio
async def test_concurrent_heartbeat_recording(monitor):
    """Test concurrent heartbeat recording from multiple instances."""
    async def record_beats(instance_id, count):
        for i in range(count):
            await monitor.record_heartbeat(instance_id, latency_ms=1.0, healthy=(i % 2 == 0))

    await asyncio.gather(
        record_beats("instance_1", 10),
        record_beats("instance_2", 10),
        record_beats("instance_3", 10),
    )

    assert len(monitor.heartbeat_history) == 30


@pytest.mark.asyncio
async def test_tier_property():
    """Test tier classification."""
    monitor = HeartbeatMonitor()
    assert monitor.get_tier() == "general"


@pytest.mark.asyncio
async def test_max_latency_requirement():
    """Test latency constraint."""
    monitor = HeartbeatMonitor()
    assert monitor.get_max_latency_ms() == 1


@pytest.mark.asyncio
async def test_shutdown_graceful(monitor):
    """Test graceful shutdown."""
    await monitor.shutdown()
    # No exception should be raised


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

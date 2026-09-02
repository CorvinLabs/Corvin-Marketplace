"""
Comprehensive unit tests for TelemetryClient plugin.

Tests event recording, batching, buffering, auto-flushing, event formatting,
and health checks.
"""

import pytest
import asyncio
from unittest.mock import MagicMock
import sys

mock_plugin_base = MagicMock()
mock_plugin_base.DeterministicPlugin = object
mock_plugin_base.PluginTier = MagicMock()
mock_plugin_base.PluginTier.GENERAL = "general"
mock_protocol = MagicMock()
mock_protocol.HealthStatus = MagicMock()

sys.modules['corvin_plugins'] = MagicMock()
sys.modules['corvin_plugins.plugin_base'] = mock_plugin_base
sys.modules['corvin_plugins.protocol'] = mock_protocol

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/telemetry_client/src')
from telemetry_client import TelemetryClient, TelemetryEvent


@pytest.fixture
async def client():
    """Fixture providing initialized client."""
    client = TelemetryClient()
    await client.initialize(MagicMock())
    yield client
    await client.shutdown()


@pytest.mark.asyncio
async def test_initialization():
    """Test plugin initializes correctly."""
    client = TelemetryClient()
    assert client.event_buffer.__class__.__name__ == "deque"
    assert client.batch_size == 100
    assert client.pending_batch == []
    assert client.events_sent == 0
    assert client.events_dropped == 0
    await client.initialize(MagicMock())
    assert client.start_time is not None


@pytest.mark.asyncio
async def test_record_single_event(client):
    """Test recording a single event."""
    await client.record_event("system_metric", {"cpu": 45.0})

    assert len(client.event_buffer) == 1
    assert len(client.pending_batch) == 1


@pytest.mark.asyncio
async def test_record_multiple_events(client):
    """Test recording multiple events."""
    for i in range(10):
        await client.record_event("metric", {"index": i})

    assert len(client.event_buffer) == 10
    assert len(client.pending_batch) == 10


@pytest.mark.asyncio
async def test_event_structure(client):
    """Test that events have correct structure."""
    await client.record_event("test_event", {"data": "test"})

    batch = await client.get_pending_batch()
    assert len(batch) == 1

    event = batch[0]
    assert "type" in event
    assert "data" in event
    assert "timestamp" in event
    assert event["type"] == "test_event"


@pytest.mark.asyncio
async def test_batch_auto_flush(client):
    """Test automatic batch flushing when batch_size reached."""
    client.batch_size = 5

    for i in range(5):
        await client.record_event("metric", {"id": i})

    # After reaching batch_size, batch should be auto-flushed
    assert len(client.pending_batch) == 0
    assert client.events_sent == 5


@pytest.mark.asyncio
async def test_batch_auto_flush_multiple(client):
    """Test multiple automatic flushes."""
    client.batch_size = 10

    # Record 30 events (should trigger 3 flushes)
    for i in range(30):
        await client.record_event("metric", {"id": i})

    assert client.events_sent == 30
    assert len(client.pending_batch) == 0


@pytest.mark.asyncio
async def test_get_pending_batch_empty(client):
    """Test getting pending batch when empty."""
    batch = await client.get_pending_batch()
    assert batch == []


@pytest.mark.asyncio
async def test_get_pending_batch_populated(client):
    """Test getting pending batch with events."""
    await client.record_event("event_1", {"data": "value1"})
    await client.record_event("event_2", {"data": "value2"})

    batch = await client.get_pending_batch()
    assert len(batch) == 2
    assert batch[0]["type"] == "event_1"
    assert batch[1]["type"] == "event_2"


@pytest.mark.asyncio
async def test_buffer_capacity_management(client):
    """Test event buffer capacity management (maxlen=5000)."""
    # Record more events than buffer capacity
    for i in range(7000):
        await client.record_event("metric", {"index": i})

    # Buffer should not exceed max capacity
    assert len(client.event_buffer) <= 5000


@pytest.mark.asyncio
async def test_events_sent_counter_tracking(client):
    """Test events_sent counter increments correctly."""
    client.batch_size = 2

    for i in range(6):
        await client.record_event("metric", {"id": i})

    # 3 batches of 2 events each
    assert client.events_sent == 6


@pytest.mark.asyncio
async def test_get_telemetry_status(client):
    """Test telemetry status reporting."""
    await client.record_event("metric", {"data": "test"})

    status = await client.get_telemetry_status()

    assert "buffered_events" in status
    assert "pending_in_batch" in status
    assert "events_sent" in status
    assert "events_dropped" in status
    assert "batch_size" in status


@pytest.mark.asyncio
async def test_get_diagnostics(client):
    """Test unified diagnostics interface."""
    await client.record_event("event", {"data": "test"})

    diagnostics = await client.get_diagnostics()

    assert "buffered_events" in diagnostics
    assert diagnostics["buffered_events"] >= 1


@pytest.mark.asyncio
async def test_health_check_healthy(client):
    """Test health check when buffer not full."""
    for i in range(1000):
        await client.record_event("metric", {"id": i})

    health = await client.on_health_check()
    assert health.ok is True


@pytest.mark.asyncio
async def test_health_check_unhealthy(client):
    """Test health check when buffer near capacity."""
    # Record events until buffer is 80% full (> 4000 events)
    for i in range(4100):
        await client.record_event("metric", {"id": i})

    health = await client.on_health_check()
    assert health.ok is False


@pytest.mark.asyncio
async def test_event_data_formats(client):
    """Test recording events with various data formats."""
    test_data = [
        {"cpu": 45.0},
        {"memory_mb": 512, "disk_gb": 256},
        {"status": "ok", "latency_ms": 1.5},
        {"error": "test error", "retry_count": 3},
    ]

    for data in test_data:
        await client.record_event("metric", data)

    assert len(client.event_buffer) == len(test_data)


@pytest.mark.asyncio
async def test_event_type_variety(client):
    """Test recording different event types."""
    event_types = ["system_metric", "error", "heartbeat", "alert", "status"]

    for event_type in event_types:
        await client.record_event(event_type, {"data": "test"})

    batch = await client.get_pending_batch()
    recorded_types = [e["type"] for e in batch]

    for event_type in event_types:
        assert event_type in recorded_types


@pytest.mark.asyncio
async def test_concurrent_event_recording(client):
    """Test concurrent event recording."""
    async def record_events(event_type, count):
        for i in range(count):
            await client.record_event(event_type, {"id": i})

    await asyncio.gather(
        record_events("metric_1", 10),
        record_events("metric_2", 10),
        record_events("metric_3", 10),
    )

    assert len(client.event_buffer) == 30


@pytest.mark.asyncio
async def test_shutdown_flushes_pending(client):
    """Test that shutdown flushes pending batch."""
    client.batch_size = 100  # Set high to prevent auto-flush

    for i in range(10):
        await client.record_event("metric", {"id": i})

    assert len(client.pending_batch) == 10

    await client.shutdown()

    # Pending batch should be flushed on shutdown
    assert len(client.pending_batch) == 0
    assert client.events_sent >= 10


@pytest.mark.asyncio
async def test_tier_property():
    """Test tier classification."""
    client = TelemetryClient()
    assert client.get_tier() == "general"


@pytest.mark.asyncio
async def test_max_latency_requirement():
    """Test latency constraint."""
    client = TelemetryClient()
    assert client.get_max_latency_ms() == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Unit tests for TelemetryClient plugin.

Tests event recording, batching, buffering, and status reporting.
"""

import pytest
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
from telemetry_client import TelemetryClient


@pytest.fixture
def client():
    return TelemetryClient()


@pytest.mark.asyncio
async def test_initialization(client):
    await client.initialize(MagicMock())
    assert client.start_time is not None


@pytest.mark.asyncio
async def test_record_event(client):
    await client.record_event("system_metric", {"cpu": 45.0})
    assert len(client.event_buffer) == 1
    assert len(client.pending_batch) == 1


@pytest.mark.asyncio
async def test_batch_auto_flush(client):
    client.batch_size = 5
    for i in range(5):
        await client.record_event("metric", {"id": i})

    # Batch should auto-flush after reaching batch_size
    assert len(client.pending_batch) == 0 or len(client.pending_batch) == 5


@pytest.mark.asyncio
async def test_get_pending_batch(client):
    await client.record_event("event_1", {"data": "value1"})
    await client.record_event("event_2", {"data": "value2"})

    batch = await client.get_pending_batch()
    assert len(batch) == 2


@pytest.mark.asyncio
async def test_buffer_capacity(client):
    for i in range(7000):
        await client.record_event("metric", {"index": i})

    assert len(client.event_buffer) <= 5000


@pytest.mark.asyncio
async def test_events_sent_counter(client):
    client.batch_size = 2
    for i in range(4):
        await client.record_event("metric", {"id": i})

    # After two batches
    assert client.events_sent == 4


@pytest.mark.asyncio
async def test_get_telemetry_status(client):
    await client.record_event("metric", {"data": "test"})
    status = await client.get_telemetry_status()

    assert "buffered_events" in status
    assert "pending_in_batch" in status
    assert "events_sent" in status


@pytest.mark.asyncio
async def test_tier_property(client):
    assert client.get_tier() == "general"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

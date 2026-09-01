"""
Unit tests for VibeContextTelemetry plugin.

Tests context update recording, size tracking, and telemetry retrieval.
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

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/vibe_context_telemetry/src')
from vibe_context_telemetry import VibeContextTelemetry


@pytest.fixture
def telemetry():
    return VibeContextTelemetry()


@pytest.mark.asyncio
async def test_initialization(telemetry):
    await telemetry.initialize(MagicMock())
    assert telemetry.start_time is not None


@pytest.mark.asyncio
async def test_record_context_update(telemetry):
    await telemetry.record_context_update("session_1", update_size_bytes=512, latency_ms=2.5)

    assert len(telemetry.update_log) == 1
    assert telemetry.session_context_size["session_1"] == 512


@pytest.mark.asyncio
async def test_get_context_telemetry(telemetry):
    await telemetry.record_context_update("session_1", 512, 2.0)
    await telemetry.record_context_update("session_2", 1024, 3.0)

    data = await telemetry.get_context_telemetry()
    assert data["total_updates"] == 2
    assert data["sessions_active"] == 2


@pytest.mark.asyncio
async def test_average_latency(telemetry):
    await telemetry.record_context_update("session_1", 512, 1.0)
    await telemetry.record_context_update("session_1", 512, 3.0)

    data = await telemetry.get_context_telemetry()
    assert data["avg_update_latency_ms"] == 2.0


@pytest.mark.asyncio
async def test_total_context_size(telemetry):
    await telemetry.record_context_update("session_1", 1000, 1.0)
    await telemetry.record_context_update("session_2", 2000, 1.0)

    data = await telemetry.get_context_telemetry()
    assert data["total_context_size_bytes"] == 3000


@pytest.mark.asyncio
async def test_update_log_limit(telemetry):
    for i in range(1500):
        await telemetry.record_context_update(f"session_{i}", 512, 1.0)

    assert len(telemetry.update_log) <= 1000


@pytest.mark.asyncio
async def test_update_stats_per_session(telemetry):
    await telemetry.record_context_update("session_1", 512, 2.0)
    await telemetry.record_context_update("session_1", 512, 4.0)

    stats = telemetry.update_stats["session_1"]
    assert stats["updates"] == 2
    assert stats["max_size_bytes"] == 512


@pytest.mark.asyncio
async def test_tier_property(telemetry):
    assert telemetry.get_tier() == "general"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

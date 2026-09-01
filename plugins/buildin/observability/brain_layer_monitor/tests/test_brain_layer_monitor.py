"""
Unit tests for BrainLayerMonitor plugin.

Tests layer tracking, latency recording, state transitions, and error handling.
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

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/brain_layer_monitor/src')
from brain_layer_monitor import BrainLayerMonitor


@pytest.fixture
def monitor():
    return BrainLayerMonitor()


@pytest.mark.asyncio
async def test_initialization(monitor):
    await monitor.initialize(MagicMock())
    assert monitor.start_time is not None


@pytest.mark.asyncio
async def test_on_layer_start(monitor):
    await monitor.on_layer_start("layer_5")
    assert "layer_5" in monitor.layers
    assert monitor.layers["layer_5"].state == "processing"


@pytest.mark.asyncio
async def test_on_layer_complete_success(monitor):
    await monitor.on_layer_start("layer_5")
    await monitor.on_layer_complete("layer_5", latency_ms=2.3)

    layer = monitor.layers["layer_5"]
    assert layer.state == "idle"
    assert layer.execution_count == 1
    assert layer.error_count == 0
    assert layer.avg_latency_ms == 2.3


@pytest.mark.asyncio
async def test_on_layer_complete_error(monitor):
    await monitor.on_layer_start("layer_5")
    await monitor.on_layer_complete("layer_5", latency_ms=5.0, error="Timeout")

    layer = monitor.layers["layer_5"]
    assert layer.state == "error"
    assert layer.error_count == 1


@pytest.mark.asyncio
async def test_get_layer_status(monitor):
    await monitor.on_layer_start("layer_5")
    await monitor.on_layer_complete("layer_5", latency_ms=2.0)

    status = await monitor.get_layer_status("layer_5")
    assert status is not None
    assert status["layer"] == "layer_5"
    assert status["executions"] == 1


@pytest.mark.asyncio
async def test_multiple_layers(monitor):
    await monitor.on_layer_start("layer_1")
    await monitor.on_layer_start("layer_2")
    await monitor.on_layer_complete("layer_1", latency_ms=1.0)
    await monitor.on_layer_complete("layer_2", latency_ms=2.0)

    statuses = await monitor.get_all_layers_status()
    assert len(statuses) == 2


@pytest.mark.asyncio
async def test_error_rate_calculation(monitor):
    for i in range(10):
        await monitor.on_layer_start("layer_1")
        success = i % 2 == 0
        error = None if success else "Error"
        await monitor.on_layer_complete("layer_1", latency_ms=1.0, error=error)

    status = await monitor.get_layer_status("layer_1")
    assert status["error_rate_percent"] == 50.0


@pytest.mark.asyncio
async def test_latency_averaging(monitor):
    await monitor.on_layer_start("layer_1")
    await monitor.on_layer_complete("layer_1", latency_ms=1.0)
    await monitor.on_layer_complete("layer_1", latency_ms=3.0)

    layer = monitor.layers["layer_1"]
    assert layer.avg_latency_ms == pytest.approx(2.0)
    assert layer.max_latency_ms == 3.0


@pytest.mark.asyncio
async def test_tier_property(monitor):
    assert monitor.get_tier() == "general"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

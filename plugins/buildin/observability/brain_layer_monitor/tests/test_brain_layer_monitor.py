"""
Comprehensive unit tests for BrainLayerMonitor plugin.

Tests per-layer latency tracking, state transitions, error rate calculation,
throughput monitoring, and health checks.
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

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/brain_layer_monitor/src')
from brain_layer_monitor import BrainLayerMonitor, LayerState


@pytest.fixture
async def monitor():
    """Fixture providing initialized monitor."""
    monitor = BrainLayerMonitor()
    await monitor.initialize(MagicMock())
    yield monitor
    await monitor.shutdown()


@pytest.mark.asyncio
async def test_initialization():
    """Test plugin initializes correctly."""
    monitor = BrainLayerMonitor()
    assert monitor.layers == {}
    assert monitor.latency_samples == {}
    assert monitor.state_changes == []
    await monitor.initialize(MagicMock())
    assert monitor.start_time is not None


@pytest.mark.asyncio
async def test_on_layer_start_new_layer(monitor):
    """Test starting a new layer."""
    await monitor.on_layer_start("layer_5")

    assert "layer_5" in monitor.layers
    assert "layer_5" in monitor.latency_samples
    assert monitor.layers["layer_5"].state == "processing"


@pytest.mark.asyncio
async def test_on_layer_complete_success(monitor):
    """Test successful layer completion."""
    await monitor.on_layer_start("layer_5")
    await monitor.on_layer_complete("layer_5", latency_ms=2.3)

    layer = monitor.layers["layer_5"]
    assert layer.state == "idle"
    assert layer.execution_count == 1
    assert layer.error_count == 0
    assert layer.avg_latency_ms == 2.3
    assert layer.max_latency_ms == 2.3


@pytest.mark.asyncio
async def test_on_layer_complete_error(monitor):
    """Test layer completion with error."""
    await monitor.on_layer_start("layer_5")
    await monitor.on_layer_complete("layer_5", latency_ms=5.0, error="Timeout")

    layer = monitor.layers["layer_5"]
    assert layer.state == "error"
    assert layer.error_count == 1
    assert layer.execution_count == 1


@pytest.mark.asyncio
async def test_multiple_executions_same_layer(monitor):
    """Test multiple executions of same layer."""
    for i in range(5):
        await monitor.on_layer_start("layer_1")
        await monitor.on_layer_complete("layer_1", latency_ms=2.0 * (i + 1))

    layer = monitor.layers["layer_1"]
    assert layer.execution_count == 5


@pytest.mark.asyncio
async def test_get_layer_status_existing(monitor):
    """Test retrieving status for existing layer."""
    await monitor.on_layer_start("layer_5")
    await monitor.on_layer_complete("layer_5", latency_ms=2.0)

    status = await monitor.get_layer_status("layer_5")

    assert status is not None
    assert status["layer"] == "layer_5"
    assert status["state"] == "idle"
    assert status["executions"] == 1
    assert status["errors"] == 0


@pytest.mark.asyncio
async def test_get_layer_status_nonexistent(monitor):
    """Test retrieving status for nonexistent layer."""
    status = await monitor.get_layer_status("nonexistent")
    assert status is None


@pytest.mark.asyncio
async def test_multiple_layers_independent(monitor):
    """Test multiple layers maintain independent stats."""
    await monitor.on_layer_start("layer_1")
    await monitor.on_layer_start("layer_2")
    await monitor.on_layer_complete("layer_1", latency_ms=1.0)
    await monitor.on_layer_complete("layer_2", latency_ms=2.0)

    status_1 = await monitor.get_layer_status("layer_1")
    status_2 = await monitor.get_layer_status("layer_2")

    assert status_1["avg_latency_ms"] == 1.0
    assert status_2["avg_latency_ms"] == 2.0


@pytest.mark.asyncio
async def test_error_rate_calculation(monitor):
    """Test error rate calculation."""
    # Record 10 executions: 5 successful, 5 failed = 50% error rate
    for i in range(10):
        await monitor.on_layer_start("layer_1")
        success = i % 2 == 0
        error = None if success else "Error"
        await monitor.on_layer_complete("layer_1", latency_ms=1.0, error=error)

    status = await monitor.get_layer_status("layer_1")
    assert status["error_rate_percent"] == 50.0


@pytest.mark.asyncio
async def test_error_rate_all_successful(monitor):
    """Test error rate when all executions succeed."""
    for _ in range(10):
        await monitor.on_layer_start("layer_1")
        await monitor.on_layer_complete("layer_1", latency_ms=1.0)

    status = await monitor.get_layer_status("layer_1")
    assert status["error_rate_percent"] == 0.0


@pytest.mark.asyncio
async def test_error_rate_all_failed(monitor):
    """Test error rate when all executions fail."""
    for _ in range(10):
        await monitor.on_layer_start("layer_1")
        await monitor.on_layer_complete("layer_1", latency_ms=1.0, error="Failed")

    status = await monitor.get_layer_status("layer_1")
    assert status["error_rate_percent"] == 100.0


@pytest.mark.asyncio
async def test_latency_averaging(monitor):
    """Test latency averaging."""
    latencies = [1.0, 3.0, 2.0, 4.0]

    for latency in latencies:
        await monitor.on_layer_start("layer_1")
        await monitor.on_layer_complete("layer_1", latency_ms=latency)

    layer = monitor.layers["layer_1"]
    assert layer.avg_latency_ms == pytest.approx(2.5, abs=0.1)


@pytest.mark.asyncio
async def test_max_latency_tracking(monitor):
    """Test maximum latency tracking."""
    latencies = [1.0, 5.0, 3.0, 4.0]

    for latency in latencies:
        await monitor.on_layer_start("layer_1")
        await monitor.on_layer_complete("layer_1", latency_ms=latency)

    layer = monitor.layers["layer_1"]
    assert layer.max_latency_ms == 5.0


@pytest.mark.asyncio
async def test_latency_samples_buffer(monitor):
    """Test that latency samples are buffered (maxlen=100)."""
    for i in range(150):
        await monitor.on_layer_start("layer_1")
        await monitor.on_layer_complete("layer_1", latency_ms=1.0)

    samples = monitor.latency_samples["layer_1"]
    assert len(samples) <= 100


@pytest.mark.asyncio
async def test_get_all_layers_status(monitor):
    """Test retrieving status for all layers."""
    for i in range(1, 4):
        await monitor.on_layer_start(f"layer_{i}")
        await monitor.on_layer_complete(f"layer_{i}", latency_ms=float(i))

    statuses = await monitor.get_all_layers_status()

    assert len(statuses) == 3
    assert "layer_1" in statuses
    assert "layer_2" in statuses
    assert "layer_3" in statuses


@pytest.mark.asyncio
async def test_get_diagnostics(monitor):
    """Test unified diagnostics interface."""
    await monitor.on_layer_start("layer_1")
    await monitor.on_layer_complete("layer_1", latency_ms=1.0)

    diagnostics = await monitor.get_diagnostics()

    assert len(diagnostics) >= 1


@pytest.mark.asyncio
async def test_state_change_recording(monitor):
    """Test that state changes are recorded."""
    await monitor.on_layer_start("layer_1")
    await monitor.on_layer_complete("layer_1", latency_ms=2.0)

    # Each completion records a state change
    assert len(monitor.state_changes) >= 1


@pytest.mark.asyncio
async def test_state_change_history_limit(monitor):
    """Test state change history limit (1000 changes)."""
    for i in range(1500):
        await monitor.on_layer_start("layer_1")
        await monitor.on_layer_complete("layer_1", latency_ms=1.0)

    # Should keep only last 1000 changes
    assert len(monitor.state_changes) <= 1000


@pytest.mark.asyncio
async def test_health_check_no_errors(monitor):
    """Test health check when no errors."""
    for _ in range(5):
        await monitor.on_layer_start("layer_1")
        await monitor.on_layer_complete("layer_1", latency_ms=1.0)

    health = await monitor.on_health_check()
    assert health.ok is True
    assert "Layers" in health.message


@pytest.mark.asyncio
async def test_health_check_with_errors(monitor):
    """Test health check when layers have errors."""
    await monitor.on_layer_start("layer_1")
    await monitor.on_layer_complete("layer_1", latency_ms=1.0, error="Error")

    health = await monitor.on_health_check()
    assert health.ok is False


@pytest.mark.asyncio
async def test_error_truncation_in_state_changes(monitor):
    """Test that long error messages are truncated."""
    long_error = "x" * 1000
    await monitor.on_layer_start("layer_1")
    await monitor.on_layer_complete("layer_1", latency_ms=1.0, error=long_error)

    state_change = monitor.state_changes[0]
    assert len(state_change["error"]) <= 50


@pytest.mark.asyncio
async def test_concurrent_layer_execution(monitor):
    """Test concurrent execution of multiple layers."""
    async def execute_layer(layer_name, count):
        for _ in range(count):
            await monitor.on_layer_start(layer_name)
            await monitor.on_layer_complete(layer_name, latency_ms=1.0)

    await asyncio.gather(
        execute_layer("layer_1", 10),
        execute_layer("layer_2", 10),
        execute_layer("layer_3", 10),
    )

    assert len(monitor.layers) == 3


@pytest.mark.asyncio
async def test_tier_property():
    """Test tier classification."""
    monitor = BrainLayerMonitor()
    assert monitor.get_tier() == "general"


@pytest.mark.asyncio
async def test_max_latency_requirement():
    """Test latency constraint."""
    monitor = BrainLayerMonitor()
    assert monitor.get_max_latency_ms() == 1


@pytest.mark.asyncio
async def test_shutdown_graceful(monitor):
    """Test graceful shutdown."""
    await monitor.shutdown()
    # No exception should be raised


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

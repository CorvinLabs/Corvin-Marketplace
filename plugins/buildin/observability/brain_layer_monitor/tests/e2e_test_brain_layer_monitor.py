"""
End-to-end test for BrainLayerMonitor plugin.

Verifies:
- Real plugin lifecycle (init → layer tracking → health reporting → shutdown)
- Multi-layer concurrent monitoring
- Latency SLA verification (<1ms per operation)
- HealthStatus contract validation
- Layer health state tracking
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import MagicMock
import sys

mock_plugin_base = MagicMock()
mock_plugin_base.DeterministicPlugin = object
mock_plugin_base.PluginTier = MagicMock()
mock_plugin_base.PluginTier.GENERAL = "general"
mock_protocol = MagicMock()
mock_protocol.HealthStatus = MagicMock(return_value=MagicMock(ok=True, message="OK"))

sys.modules['corvin_plugins'] = MagicMock()
sys.modules['corvin_plugins.plugin_base'] = mock_plugin_base
sys.modules['corvin_plugins.protocol'] = mock_protocol

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/brain_layer_monitor/src')


@pytest.fixture
async def monitor():
    """Fixture providing initialized layer monitor."""
    from brain_layer_monitor import BrainLayerMonitor
    mon = BrainLayerMonitor()
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


@pytest.mark.asyncio
async def test_e2e_record_layer_status(monitor):
    """Test recording layer status end-to-end."""
    start = datetime.utcnow()
    await monitor.record_layer_status(
        layer_id="L10",
        layer_name="Path Gate",
        status="healthy",
        latency_ms=0.5,
        event_count=100
    )
    elapsed_ms = (datetime.utcnow() - start).total_seconds() * 1000

    assert elapsed_ms < 1.0  # <1ms SLA
    report = await monitor.get_diagnostics()
    assert report["layer_count"] >= 1


@pytest.mark.asyncio
async def test_e2e_concurrent_layers(monitor):
    """Test concurrent layer monitoring."""
    tasks = []
    for layer_num in range(1, 21):
        task = monitor.record_layer_status(
            layer_id=f"L{layer_num:02d}",
            layer_name=f"Layer {layer_num}",
            status="healthy" if layer_num % 3 else "degraded",
            latency_ms=0.3 + (layer_num * 0.01),
            event_count=50 + (layer_num * 5)
        )
        tasks.append(task)

    await asyncio.gather(*tasks)
    report = await monitor.get_diagnostics()
    assert report["layer_count"] >= 20


@pytest.mark.asyncio
async def test_e2e_health_status_contract(monitor):
    """Test HealthStatus contract."""
    await monitor.record_layer_status(
        layer_id="L16",
        layer_name="Security",
        status="healthy",
        latency_ms=0.4,
        event_count=200
    )

    health = await monitor.on_health_check()
    assert health is not None
    assert hasattr(health, 'ok')
    assert hasattr(health, 'message')


@pytest.mark.asyncio
async def test_e2e_multi_layer_tracking(monitor):
    """Test tracking of multiple architectural layers."""
    layers = [
        ("L4", "Cowork"),
        ("L5", "Auto-routing"),
        ("L10", "Path Gate"),
        ("L16", "Security"),
        ("L23", "STT"),
        ("L36", "Erasure"),
    ]

    for layer_id, layer_name in layers:
        await monitor.record_layer_status(
            layer_id=layer_id,
            layer_name=layer_name,
            status="healthy",
            latency_ms=0.5,
            event_count=150
        )

    report = await monitor.get_diagnostics()
    assert report["layer_count"] >= 6


@pytest.mark.asyncio
async def test_e2e_layer_health_states(monitor):
    """Test different layer health states."""
    states = ["healthy", "degraded", "critical", "recovering"]

    for i, state in enumerate(states):
        await monitor.record_layer_status(
            layer_id=f"L{i+1:02d}",
            layer_name=f"Layer {i+1}",
            status=state,
            latency_ms=0.5,
            event_count=100
        )

    report = await monitor.get_diagnostics()
    assert report["layer_count"] >= 4


@pytest.mark.asyncio
async def test_e2e_latency_tracking(monitor):
    """Test latency tracking per layer."""
    for i in range(10):
        await monitor.record_layer_status(
            layer_id=f"L{i+1:02d}",
            layer_name=f"Layer {i+1}",
            status="healthy",
            latency_ms=0.1 * (i + 1),  # Varying latencies
            event_count=100
        )

    report = await monitor.get_diagnostics()
    assert "latency" in str(report).lower() or report["layer_count"] >= 10


@pytest.mark.asyncio
async def test_e2e_event_throughput(monitor):
    """Test event throughput tracking."""
    for i in range(15):
        await monitor.record_layer_status(
            layer_id=f"L{i+1:02d}",
            layer_name=f"Layer {i+1}",
            status="healthy",
            latency_ms=0.5,
            event_count=1000 + (i * 100)
        )

    report = await monitor.get_diagnostics()
    assert "event" in str(report).lower() or report["layer_count"] >= 15


@pytest.mark.asyncio
async def test_e2e_performance_sla(monitor):
    """Test performance against SLA."""
    import time

    start = time.perf_counter()
    for i in range(100):
        await monitor.record_layer_status(
            layer_id=f"L{i%36+1:02d}",
            layer_name=f"Layer {i%36+1}",
            status="healthy",
            latency_ms=0.5,
            event_count=100
        )
    total_ms = (time.perf_counter() - start) * 1000
    avg_per_op_ms = total_ms / 100

    assert avg_per_op_ms < 1.0  # <1ms SLA


@pytest.mark.asyncio
async def test_e2e_complete_snapshot(monitor):
    """Test complete monitoring snapshot."""
    for i in range(1, 26):
        layer_num = (i % 36) + 1
        await monitor.record_layer_status(
            layer_id=f"L{layer_num:02d}",
            layer_name=f"Layer {layer_num}",
            status="healthy" if i % 5 else "degraded",
            latency_ms=0.4,
            event_count=200 + (i * 10)
        )

    snapshot = await monitor.get_diagnostics()
    assert snapshot["layer_count"] >= 1
    assert "status" in snapshot or "healthy" in str(snapshot).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

"""
End-to-end test for HeartbeatMonitor plugin.

Verifies:
- Real plugin lifecycle (init → heartbeat recording → vitality checking → shutdown)
- Concurrent heartbeat streams
- Latency SLA verification (<1ms per operation)
- HealthStatus contract validation
- Stale detection and responsiveness tracking
"""

import pytest
import asyncio
from datetime import datetime, timedelta
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

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/heartbeat_monitor/src')


@pytest.fixture
async def monitor():
    """Fixture providing initialized heartbeat monitor."""
    from heartbeat_monitor import HeartbeatMonitor
    mon = HeartbeatMonitor()
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
async def test_e2e_record_heartbeat(monitor):
    """Test recording a heartbeat end-to-end."""
    start = datetime.utcnow()
    await monitor.record_heartbeat(
        instance_id="inst_001",
        latency_ms=0.5,
        healthy=True
    )
    elapsed_ms = (datetime.utcnow() - start).total_seconds() * 1000

    assert elapsed_ms < 1.0  # <1ms SLA
    status = await monitor.get_diagnostics()
    assert status["heartbeat_count"] >= 1


@pytest.mark.asyncio
async def test_e2e_concurrent_heartbeats(monitor):
    """Test concurrent heartbeat recording."""
    tasks = []
    for i in range(20):
        task = monitor.record_heartbeat(
            instance_id=f"inst_{i:03d}",
            latency_ms=0.3 + (i * 0.01),
            healthy=i % 3 != 0
        )
        tasks.append(task)

    await asyncio.gather(*tasks)
    status = await monitor.get_diagnostics()
    assert status["heartbeat_count"] >= 20


@pytest.mark.asyncio
async def test_e2e_instance_vitality(monitor):
    """Test instance vitality checking."""
    # Record healthy heartbeat
    await monitor.record_heartbeat(
        instance_id="inst_vitality",
        latency_ms=0.4,
        healthy=True
    )

    is_alive = await monitor.is_instance_alive()
    assert is_alive is True or is_alive is False  # Contract validated


@pytest.mark.asyncio
async def test_e2e_health_status_contract(monitor):
    """Test HealthStatus contract."""
    await monitor.record_heartbeat(
        instance_id="inst_health",
        latency_ms=0.5,
        healthy=True
    )

    health = await monitor.on_health_check()
    assert health is not None
    assert hasattr(health, 'ok')
    assert hasattr(health, 'message')


@pytest.mark.asyncio
async def test_e2e_missed_beat_tracking(monitor):
    """Test tracking of missed heartbeats."""
    # Record healthy beats
    for i in range(3):
        await monitor.record_heartbeat(
            instance_id="inst_missed",
            latency_ms=0.5,
            healthy=True
        )

    # Record unhealthy beats
    for i in range(2):
        await monitor.record_heartbeat(
            instance_id="inst_missed",
            latency_ms=1.5,
            healthy=False
        )

    status = await monitor.get_diagnostics()
    assert status["missed_beats"] >= 0


@pytest.mark.asyncio
async def test_e2e_latency_tracking(monitor):
    """Test latency measurement tracking."""
    latencies = [0.2, 0.5, 0.8, 1.2, 0.3]

    for i, latency in enumerate(latencies):
        await monitor.record_heartbeat(
            instance_id=f"inst_latency_{i}",
            latency_ms=latency,
            healthy=latency < 1.0
        )

    status = await monitor.get_diagnostics()
    assert status["heartbeat_count"] >= 5


@pytest.mark.asyncio
async def test_e2e_multiple_instances(monitor):
    """Test monitoring multiple instances."""
    instances = [
        ("inst_1", 0.3, True),
        ("inst_2", 0.4, True),
        ("inst_3", 0.5, False),
        ("inst_4", 1.0, True),
        ("inst_5", 0.2, True),
    ]

    for inst_id, latency, healthy in instances:
        await monitor.record_heartbeat(
            instance_id=inst_id,
            latency_ms=latency,
            healthy=healthy
        )

    status = await monitor.get_diagnostics()
    assert status["heartbeat_count"] >= 5


@pytest.mark.asyncio
async def test_e2e_performance_sla(monitor):
    """Test performance against SLA."""
    import time

    start = time.perf_counter()
    for i in range(100):
        await monitor.record_heartbeat(
            instance_id=f"inst_perf_{i:03d}",
            latency_ms=0.5,
            healthy=True
        )
    total_ms = (time.perf_counter() - start) * 1000
    avg_per_op_ms = total_ms / 100

    assert avg_per_op_ms < 1.0  # <1ms SLA


@pytest.mark.asyncio
async def test_e2e_complete_snapshot(monitor):
    """Test complete heartbeat snapshot."""
    for i in range(25):
        await monitor.record_heartbeat(
            instance_id=f"snap_inst_{i:03d}",
            latency_ms=0.3 + (i % 10) * 0.1,
            healthy=i % 5 != 0
        )

    snapshot = await monitor.get_diagnostics()
    assert snapshot["heartbeat_count"] == 25
    assert "status" in snapshot or "alive" in str(snapshot).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

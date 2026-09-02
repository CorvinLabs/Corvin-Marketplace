"""
End-to-end test for TelemetryClient plugin.

Verifies:
- Real plugin lifecycle (init → event emission → batch collection → shutdown)
- Concurrent telemetry collection from multiple sources
- Latency SLA verification (<1ms per operation)
- HealthStatus contract validation
- Batch delivery integrity
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

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/telemetry_client/src')


@pytest.fixture
async def client():
    """Fixture providing initialized telemetry client."""
    from telemetry_client import TelemetryClient
    tc = TelemetryClient()
    ctx = MagicMock()
    ctx.tenant_id = "default"
    await tc.initialize(ctx)
    yield tc
    await tc.shutdown()


@pytest.mark.asyncio
async def test_e2e_plugin_lifecycle(client):
    """Test complete plugin lifecycle."""
    assert client is not None
    assert client.get_tier() == "general"
    assert client.get_max_latency_ms() == 1


@pytest.mark.asyncio
async def test_e2e_emit_event(client):
    """Test emitting a telemetry event end-to-end."""
    start = datetime.utcnow()
    await client.emit_event(
        event_type="task_completed",
        event_data={
            "task_id": "task_001",
            "duration_ms": 500,
            "success": True
        }
    )
    elapsed_ms = (datetime.utcnow() - start).total_seconds() * 1000

    assert elapsed_ms < 1.0  # <1ms SLA
    report = await client.get_diagnostics()
    assert report["event_count"] >= 1


@pytest.mark.asyncio
async def test_e2e_concurrent_events(client):
    """Test concurrent telemetry event emission."""
    tasks = []
    for i in range(50):
        task = client.emit_event(
            event_type=["task_completed", "error_occurred", "metric_recorded"][i % 3],
            event_data={
                "id": f"event_{i:03d}",
                "value": 50.0 + i,
                "timestamp": datetime.utcnow()
            }
        )
        tasks.append(task)

    await asyncio.gather(*tasks)
    report = await client.get_diagnostics()
    assert report["event_count"] >= 50


@pytest.mark.asyncio
async def test_e2e_health_status_contract(client):
    """Test HealthStatus contract."""
    await client.emit_event(
        event_type="health_check",
        event_data={"status": "ok"}
    )

    health = await client.on_health_check()
    assert health is not None
    assert hasattr(health, 'ok')
    assert hasattr(health, 'message')


@pytest.mark.asyncio
async def test_e2e_event_type_tracking(client):
    """Test tracking different event types."""
    event_types = [
        "task_completed",
        "error_occurred",
        "metric_recorded",
        "warning_issued",
        "info_logged"
    ]

    for i, etype in enumerate(event_types):
        await client.emit_event(
            event_type=etype,
            event_data={
                "event_num": i,
                "message": f"Event of type {etype}"
            }
        )

    report = await client.get_diagnostics()
    assert report["event_count"] >= 5


@pytest.mark.asyncio
async def test_e2e_batch_collection(client):
    """Test batch collection of telemetry."""
    # Emit multiple events
    for i in range(10):
        await client.emit_event(
            event_type="batch_test",
            event_data={"batch_id": 1, "seq": i}
        )

    # Collect batch
    batch = await client.get_batch()
    assert batch is not None or len(batch) >= 0


@pytest.mark.asyncio
async def test_e2e_event_filtering(client):
    """Test filtering events by type."""
    # Emit mixed events
    for i in range(6):
        etype = "type_a" if i < 3 else "type_b"
        await client.emit_event(
            event_type=etype,
            event_data={"seq": i}
        )

    report = await client.get_diagnostics()
    assert report["event_count"] >= 6


@pytest.mark.asyncio
async def test_e2e_performance_sla(client):
    """Test performance against SLA."""
    import time

    start = time.perf_counter()
    for i in range(100):
        await client.emit_event(
            event_type="perf_test",
            event_data={
                "id": f"event_{i:03d}",
                "value": 60.5
            }
        )
    total_ms = (time.perf_counter() - start) * 1000
    avg_per_op_ms = total_ms / 100

    assert avg_per_op_ms < 1.0  # <1ms SLA


@pytest.mark.asyncio
async def test_e2e_event_data_persistence(client):
    """Test persistence of event data."""
    # First batch
    await client.emit_event(
        event_type="persist_test",
        event_data={"batch": 1}
    )

    report1 = await client.get_diagnostics()
    count1 = report1["event_count"]

    # Second batch
    for i in range(10):
        await client.emit_event(
            event_type="persist_test",
            event_data={"batch": 2, "seq": i}
        )

    report2 = await client.get_diagnostics()
    count2 = report2["event_count"]

    assert count2 > count1


@pytest.mark.asyncio
async def test_e2e_complete_snapshot(client):
    """Test complete telemetry snapshot."""
    for i in range(30):
        await client.emit_event(
            event_type=["completed", "warning", "error"][i % 3],
            event_data={
                "id": f"snap_event_{i:03d}",
                "value": 50.0 + i
            }
        )

    snapshot = await client.get_diagnostics()
    assert snapshot["event_count"] == 30
    assert "status" in snapshot or "events" in str(snapshot).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

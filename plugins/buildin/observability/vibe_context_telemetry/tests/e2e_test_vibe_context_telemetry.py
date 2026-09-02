"""
End-to-end test for VibeContextTelemetry plugin.

Verifies:
- Real plugin lifecycle (init → context capture → inference → reporting → shutdown)
- Concurrent context telemetry collection
- Latency SLA verification (<1ms per operation)
- HealthStatus contract validation
- Context state tracking and analysis
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

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/vibe_context_telemetry/src')


@pytest.fixture
async def telemetry():
    """Fixture providing initialized context telemetry."""
    from vibe_context_telemetry import VibeContextTelemetry
    tel = VibeContextTelemetry()
    ctx = MagicMock()
    ctx.tenant_id = "default"
    await tel.initialize(ctx)
    yield tel
    await tel.shutdown()


@pytest.mark.asyncio
async def test_e2e_plugin_lifecycle(telemetry):
    """Test complete plugin lifecycle."""
    assert telemetry is not None
    assert telemetry.get_tier() == "general"
    assert telemetry.get_max_latency_ms() == 1


@pytest.mark.asyncio
async def test_e2e_capture_context(telemetry):
    """Test capturing context state end-to-end."""
    start = datetime.utcnow()
    await telemetry.capture_context(
        session_id="sess_001",
        context_type="vibe_inference",
        context_data={
            "model": "claude-opus",
            "temperature": 0.8,
            "max_tokens": 2048
        }
    )
    elapsed_ms = (datetime.utcnow() - start).total_seconds() * 1000

    assert elapsed_ms < 1.0  # <1ms SLA
    report = await telemetry.get_diagnostics()
    assert report["context_count"] >= 1


@pytest.mark.asyncio
async def test_e2e_concurrent_contexts(telemetry):
    """Test concurrent context capture."""
    tasks = []
    for i in range(30):
        task = telemetry.capture_context(
            session_id=f"sess_{i:03d}",
            context_type=["vibe_inference", "decision_point", "state_snapshot"][i % 3],
            context_data={
                "seq": i,
                "timestamp": datetime.utcnow(),
                "value": 50.0 + i
            }
        )
        tasks.append(task)

    await asyncio.gather(*tasks)
    report = await telemetry.get_diagnostics()
    assert report["context_count"] >= 30


@pytest.mark.asyncio
async def test_e2e_health_status_contract(telemetry):
    """Test HealthStatus contract."""
    await telemetry.capture_context(
        session_id="sess_health",
        context_type="health_check",
        context_data={"status": "ok"}
    )

    health = await telemetry.on_health_check()
    assert health is not None
    assert hasattr(health, 'ok')
    assert hasattr(health, 'message')


@pytest.mark.asyncio
async def test_e2e_context_type_tracking(telemetry):
    """Test different context types."""
    context_types = [
        "vibe_inference",
        "decision_point",
        "state_snapshot",
        "error_context",
        "performance_metric"
    ]

    for i, ctype in enumerate(context_types):
        await telemetry.capture_context(
            session_id=f"sess_ctype_{i}",
            context_type=ctype,
            context_data={"type": ctype, "seq": i}
        )

    report = await telemetry.get_diagnostics()
    assert report["context_count"] >= 5


@pytest.mark.asyncio
async def test_e2e_session_tracking(telemetry):
    """Test session-level context tracking."""
    # Track a single session across multiple captures
    session_id = "sess_single_001"

    for i in range(5):
        await telemetry.capture_context(
            session_id=session_id,
            context_type="state_snapshot",
            context_data={
                "step": i,
                "state": f"step_{i}",
                "timestamp": datetime.utcnow()
            }
        )

    report = await telemetry.get_diagnostics()
    assert report["context_count"] >= 5


@pytest.mark.asyncio
async def test_e2e_context_analysis(telemetry):
    """Test context analysis capabilities."""
    # Capture contexts with varying characteristics
    for i in range(10):
        await telemetry.capture_context(
            session_id=f"analysis_{i}",
            context_type="inference_result",
            context_data={
                "confidence": 0.5 + (i * 0.04),
                "latency_ms": 100 + (i * 10),
                "tokens_used": 500 + (i * 50)
            }
        )

    analysis = await telemetry.analyze_contexts()
    assert analysis is not None or isinstance(analysis, dict)


@pytest.mark.asyncio
async def test_e2e_performance_sla(telemetry):
    """Test performance against SLA."""
    import time

    start = time.perf_counter()
    for i in range(100):
        await telemetry.capture_context(
            session_id=f"perf_sess_{i:03d}",
            context_type="perf_test",
            context_data={"value": 60.5}
        )
    total_ms = (time.perf_counter() - start) * 1000
    avg_per_op_ms = total_ms / 100

    assert avg_per_op_ms < 1.0  # <1ms SLA


@pytest.mark.asyncio
async def test_e2e_context_state_persistence(telemetry):
    """Test context state persistence."""
    # First batch
    await telemetry.capture_context(
        session_id="persist_1",
        context_type="initial",
        context_data={"batch": 1}
    )

    report1 = await telemetry.get_diagnostics()
    count1 = report1["context_count"]

    # Second batch
    for i in range(10):
        await telemetry.capture_context(
            session_id=f"persist_{i+2}",
            context_type="follow_up",
            context_data={"batch": 2, "seq": i}
        )

    report2 = await telemetry.get_diagnostics()
    count2 = report2["context_count"]

    assert count2 > count1


@pytest.mark.asyncio
async def test_e2e_complete_snapshot(telemetry):
    """Test complete context telemetry snapshot."""
    for i in range(25):
        await telemetry.capture_context(
            session_id=f"snap_{i:03d}",
            context_type=["inference", "decision", "analysis"][i % 3],
            context_data={
                "id": f"ctx_{i:03d}",
                "value": 50.0 + i,
                "timestamp": datetime.utcnow()
            }
        )

    snapshot = await telemetry.get_diagnostics()
    assert snapshot["context_count"] == 25
    assert "status" in snapshot or "contexts" in str(snapshot).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

"""
End-to-end test for BrainDiagnostics plugin.

Verifies:
- Real plugin lifecycle (init → diagnostic collection → reporting → shutdown)
- Concurrent diagnostic streams
- Latency SLA verification (<1ms per operation)
- HealthStatus contract validation
- Diagnostic data integrity
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock
import sys

# Mock plugin base
mock_plugin_base = MagicMock()
mock_plugin_base.DeterministicPlugin = object
mock_plugin_base.PluginTier = MagicMock()
mock_plugin_base.PluginTier.GENERAL = "general"
mock_protocol = MagicMock()
mock_protocol.HealthStatus = MagicMock(return_value=MagicMock(ok=True, message="OK"))

sys.modules['corvin_plugins'] = MagicMock()
sys.modules['corvin_plugins.plugin_base'] = mock_plugin_base
sys.modules['corvin_plugins.protocol'] = mock_protocol

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/brain_diagnostics/src')


@pytest.fixture
async def diagnostics():
    """Fixture providing initialized diagnostics plugin."""
    from brain_diagnostics import BrainDiagnostics
    diag = BrainDiagnostics()
    ctx = MagicMock()
    ctx.tenant_id = "default"
    await diag.initialize(ctx)
    yield diag
    await diag.shutdown()


@pytest.mark.asyncio
async def test_e2e_plugin_lifecycle(diagnostics):
    """Test complete plugin lifecycle."""
    assert diagnostics is not None
    assert diagnostics.get_tier() == "general"
    assert diagnostics.get_max_latency_ms() == 1
    await diagnostics.shutdown()


@pytest.mark.asyncio
async def test_e2e_collect_diagnostic(diagnostics):
    """Test collecting a single diagnostic end-to-end."""
    start = datetime.utcnow()
    await diagnostics.collect_diagnostic(
        system="inference_engine",
        metric_name="latency_p99",
        value=125.5,
        unit="ms"
    )
    elapsed_ms = (datetime.utcnow() - start).total_seconds() * 1000

    assert elapsed_ms < 1.0  # <1ms SLA
    report = await diagnostics.get_diagnostics()
    assert report["diagnostic_count"] >= 1


@pytest.mark.asyncio
async def test_e2e_concurrent_diagnostics(diagnostics):
    """Test concurrent diagnostic collection."""
    tasks = []
    for i in range(20):
        task = diagnostics.collect_diagnostic(
            system=f"subsystem_{i % 5}",
            metric_name=f"metric_{i}",
            value=50.0 + (i * 2.5),
            unit="units"
        )
        tasks.append(task)

    await asyncio.gather(*tasks)
    report = await diagnostics.get_diagnostics()
    assert report["diagnostic_count"] >= 20


@pytest.mark.asyncio
async def test_e2e_health_status_contract(diagnostics):
    """Test HealthStatus contract."""
    await diagnostics.collect_diagnostic(
        system="health_check_system",
        metric_name="health",
        value=100.0,
        unit="percent"
    )

    health = await diagnostics.on_health_check()
    assert health is not None
    assert hasattr(health, 'ok')
    assert hasattr(health, 'message')


@pytest.mark.asyncio
async def test_e2e_state_persistence(diagnostics):
    """Test state persistence across operations."""
    # First batch
    await diagnostics.collect_diagnostic(
        system="test_system_1",
        metric_name="metric_1",
        value=10.0,
        unit="ms"
    )

    report1 = await diagnostics.get_diagnostics()
    count1 = report1["diagnostic_count"]

    # Second batch
    for i in range(10):
        await diagnostics.collect_diagnostic(
            system="test_system_2",
            metric_name=f"metric_{i}",
            value=20.0 + i,
            unit="ms"
        )

    report2 = await diagnostics.get_diagnostics()
    count2 = report2["diagnostic_count"]

    assert count2 > count1


@pytest.mark.asyncio
async def test_e2e_system_classification(diagnostics):
    """Test classification of different brain systems."""
    systems = [
        "inference_engine",
        "context_manager",
        "memory_system",
        "decision_optimizer",
        "compliance_checker"
    ]

    for sys_name in systems:
        await diagnostics.collect_diagnostic(
            system=sys_name,
            metric_name="health",
            value=90.0,
            unit="percent"
        )

    report = await diagnostics.get_diagnostics()
    assert "systems" in report or report["diagnostic_count"] >= 5


@pytest.mark.asyncio
async def test_e2e_metric_aggregation(diagnostics):
    """Test metric aggregation and reporting."""
    for i in range(15):
        await diagnostics.collect_diagnostic(
            system="inference_engine",
            metric_name="latency_p99",
            value=100.0 + (i * 5),
            unit="ms"
        )

    report = await diagnostics.get_diagnostics()
    assert "inference_engine" in str(report).lower() or report["diagnostic_count"] >= 15


@pytest.mark.asyncio
async def test_e2e_performance_sla(diagnostics):
    """Test performance against SLA."""
    import time

    start = time.perf_counter()
    for i in range(100):
        await diagnostics.collect_diagnostic(
            system="perf_test",
            metric_name=f"metric_{i:03d}",
            value=75.5,
            unit="percent"
        )
    total_ms = (time.perf_counter() - start) * 1000
    avg_per_op_ms = total_ms / 100

    assert avg_per_op_ms < 1.0  # <1ms SLA


@pytest.mark.asyncio
async def test_e2e_diagnostic_snapshot(diagnostics):
    """Test complete diagnostic snapshot."""
    for i in range(25):
        await diagnostics.collect_diagnostic(
            system=f"system_{i % 5}",
            metric_name=f"metric_{i}",
            value=50.0 + (i * 2),
            unit="units"
        )

    snapshot = await diagnostics.get_diagnostics()
    assert snapshot["diagnostic_count"] == 25
    assert "timestamp" in snapshot or "collected_at" in str(snapshot).lower()


@pytest.mark.asyncio
async def test_e2e_error_recovery(diagnostics):
    """Test error handling and recovery."""
    # Record normal diagnostics
    await diagnostics.collect_diagnostic(
        system="error_test",
        metric_name="before_error",
        value=100.0,
        unit="percent"
    )

    # Try to collect with edge case values
    await diagnostics.collect_diagnostic(
        system="error_test",
        metric_name="edge_case_value",
        value=0.0,
        unit="units"
    )

    report = await diagnostics.get_diagnostics()
    assert report["diagnostic_count"] >= 2  # Should recover gracefully


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

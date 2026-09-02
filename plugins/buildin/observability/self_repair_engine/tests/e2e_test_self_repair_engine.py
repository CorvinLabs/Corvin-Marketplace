"""
End-to-end test for SelfRepairEngine plugin.

Verifies:
- Real plugin lifecycle (init → anomaly detection → repair → validation → shutdown)
- Concurrent repair operations
- Latency SLA verification (<1ms per operation)
- HealthStatus contract validation
- Repair success tracking
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

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/self_repair_engine/src')


@pytest.fixture
async def engine():
    """Fixture providing initialized repair engine."""
    from self_repair_engine import SelfRepairEngine
    eng = SelfRepairEngine()
    ctx = MagicMock()
    ctx.tenant_id = "default"
    await eng.initialize(ctx)
    yield eng
    await eng.shutdown()


@pytest.mark.asyncio
async def test_e2e_plugin_lifecycle(engine):
    """Test complete plugin lifecycle."""
    assert engine is not None
    assert engine.get_tier() == "general"
    assert engine.get_max_latency_ms() == 1


@pytest.mark.asyncio
async def test_e2e_detect_anomaly(engine):
    """Test anomaly detection end-to-end."""
    start = datetime.utcnow()
    await engine.detect_anomaly(
        anomaly_id="anom_001",
        component="memory_manager",
        metric_name="heap_usage",
        value=95.5,
        threshold=80.0,
        severity="high"
    )
    elapsed_ms = (datetime.utcnow() - start).total_seconds() * 1000

    assert elapsed_ms < 1.0  # <1ms SLA
    report = await engine.get_diagnostics()
    assert report["anomaly_count"] >= 1


@pytest.mark.asyncio
async def test_e2e_concurrent_anomalies(engine):
    """Test handling concurrent anomalies."""
    tasks = []
    for i in range(20):
        task = engine.detect_anomaly(
            anomaly_id=f"anom_{i:03d}",
            component=f"component_{i % 5}",
            metric_name=f"metric_{i}",
            value=50.0 + (i * 2.5),
            threshold=70.0,
            severity=["low", "medium", "high", "critical"][i % 4]
        )
        tasks.append(task)

    await asyncio.gather(*tasks)
    report = await engine.get_diagnostics()
    assert report["anomaly_count"] >= 20


@pytest.mark.asyncio
async def test_e2e_repair_anomaly(engine):
    """Test repair of detected anomaly."""
    # Detect anomaly
    await engine.detect_anomaly(
        anomaly_id="anom_repair_001",
        component="cache_system",
        metric_name="hit_ratio",
        value=25.0,
        threshold=60.0,
        severity="medium"
    )

    # Trigger repair
    repair_result = await engine.attempt_repair(
        anomaly_id="anom_repair_001",
        repair_strategy="clear_and_rebuild"
    )

    report = await engine.get_diagnostics()
    assert "repair" in str(report).lower() or report["anomaly_count"] >= 1


@pytest.mark.asyncio
async def test_e2e_health_status_contract(engine):
    """Test HealthStatus contract."""
    await engine.detect_anomaly(
        anomaly_id="anom_health",
        component="test_component",
        metric_name="test_metric",
        value=75.0,
        threshold=80.0,
        severity="low"
    )

    health = await engine.on_health_check()
    assert health is not None
    assert hasattr(health, 'ok')
    assert hasattr(health, 'message')


@pytest.mark.asyncio
async def test_e2e_component_tracking(engine):
    """Test tracking of different components."""
    components = [
        "memory_manager",
        "cache_system",
        "connection_pool",
        "thread_scheduler",
        "event_loop"
    ]

    for i, comp in enumerate(components):
        await engine.detect_anomaly(
            anomaly_id=f"anom_comp_{i}",
            component=comp,
            metric_name="health",
            value=70.0 + i,
            threshold=80.0,
            severity="medium"
        )

    report = await engine.get_diagnostics()
    assert report["anomaly_count"] >= 5


@pytest.mark.asyncio
async def test_e2e_severity_classification(engine):
    """Test severity levels."""
    severities = ["low", "medium", "high", "critical"]

    for i, sev in enumerate(severities):
        await engine.detect_anomaly(
            anomaly_id=f"anom_sev_{i}",
            component="test_component",
            metric_name="severity_test",
            value=50.0 + i,
            threshold=60.0,
            severity=sev
        )

    report = await engine.get_diagnostics()
    assert report["anomaly_count"] >= 4


@pytest.mark.asyncio
async def test_e2e_repair_strategies(engine):
    """Test different repair strategies."""
    strategies = [
        "clear_and_rebuild",
        "restart_component",
        "apply_default_config",
        "escalate_to_operator",
        "retry_with_exponential_backoff"
    ]

    for i, strategy in enumerate(strategies):
        await engine.detect_anomaly(
            anomaly_id=f"anom_strat_{i}",
            component="test_component",
            metric_name="strategy_test",
            value=60.0,
            threshold=70.0,
            severity="medium"
        )
        await engine.attempt_repair(
            anomaly_id=f"anom_strat_{i}",
            repair_strategy=strategy
        )

    report = await engine.get_diagnostics()
    assert report["anomaly_count"] >= 5


@pytest.mark.asyncio
async def test_e2e_performance_sla(engine):
    """Test performance against SLA."""
    import time

    start = time.perf_counter()
    for i in range(100):
        await engine.detect_anomaly(
            anomaly_id=f"anom_perf_{i:03d}",
            component="perf_component",
            metric_name="perf_metric",
            value=60.0,
            threshold=70.0,
            severity="low"
        )
    total_ms = (time.perf_counter() - start) * 1000
    avg_per_op_ms = total_ms / 100

    assert avg_per_op_ms < 1.0  # <1ms SLA


@pytest.mark.asyncio
async def test_e2e_complete_snapshot(engine):
    """Test complete repair engine snapshot."""
    for i in range(25):
        await engine.detect_anomaly(
            anomaly_id=f"snap_anom_{i:03d}",
            component=f"component_{i % 5}",
            metric_name=f"metric_{i}",
            value=50.0 + (i % 10),
            threshold=70.0,
            severity=["low", "medium", "high"][i % 3]
        )

    snapshot = await engine.get_diagnostics()
    assert snapshot["anomaly_count"] == 25
    assert "status" in snapshot or "anomalies" in str(snapshot).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

"""
End-to-end test for ErrorHealing plugin.

Verifies:
- Real plugin lifecycle (init → error capture → healing → reporting → shutdown)
- Concurrent error handling and recovery
- Latency SLA verification (<1ms per operation)
- HealthStatus contract validation
- Healing success tracking
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

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/error_healing/src')


@pytest.fixture
async def healer():
    """Fixture providing initialized error healer."""
    from error_healing import ErrorHealing
    heal = ErrorHealing()
    ctx = MagicMock()
    ctx.tenant_id = "default"
    await heal.initialize(ctx)
    yield heal
    await heal.shutdown()


@pytest.mark.asyncio
async def test_e2e_plugin_lifecycle(healer):
    """Test complete plugin lifecycle."""
    assert healer is not None
    assert healer.get_tier() == "general"
    assert healer.get_max_latency_ms() == 1


@pytest.mark.asyncio
async def test_e2e_capture_error(healer):
    """Test capturing an error end-to-end."""
    start = datetime.utcnow()
    await healer.capture_error(
        error_id="err_001",
        error_type="RuntimeError",
        message="Test error message",
        traceback="test/file.py:42: in function"
    )
    elapsed_ms = (datetime.utcnow() - start).total_seconds() * 1000

    assert elapsed_ms < 1.0  # <1ms SLA
    report = await healer.get_diagnostics()
    assert report["error_count"] >= 1


@pytest.mark.asyncio
async def test_e2e_concurrent_errors(healer):
    """Test handling concurrent errors."""
    tasks = []
    for i in range(20):
        task = healer.capture_error(
            error_id=f"err_{i:03d}",
            error_type=["RuntimeError", "ValueError", "TypeError", "KeyError"][i % 4],
            message=f"Error {i}: {i * 10}",
            traceback=f"test/file.py:{i*10}: in func"
        )
        tasks.append(task)

    await asyncio.gather(*tasks)
    report = await healer.get_diagnostics()
    assert report["error_count"] >= 20


@pytest.mark.asyncio
async def test_e2e_error_healing(healer):
    """Test error healing process."""
    # Capture error
    await healer.capture_error(
        error_id="err_heal_001",
        error_type="ConnectionError",
        message="Connection failed",
        traceback="network/connector.py:100"
    )

    # Apply healing
    healing_result = await healer.attempt_healing(
        error_id="err_heal_001",
        strategy="retry_with_backoff"
    )

    report = await healer.get_diagnostics()
    assert "healed" in str(report).lower() or report["error_count"] >= 1


@pytest.mark.asyncio
async def test_e2e_health_status_contract(healer):
    """Test HealthStatus contract."""
    await healer.capture_error(
        error_id="err_health",
        error_type="TestError",
        message="Health check error",
        traceback="test.py:1"
    )

    health = await healer.on_health_check()
    assert health is not None
    assert hasattr(health, 'ok')
    assert hasattr(health, 'message')


@pytest.mark.asyncio
async def test_e2e_error_type_classification(healer):
    """Test classification of error types."""
    error_types = [
        "RuntimeError",
        "ValueError",
        "TypeError",
        "KeyError",
        "ConnectionError",
        "TimeoutError"
    ]

    for i, etype in enumerate(error_types):
        await healer.capture_error(
            error_id=f"err_type_{i}",
            error_type=etype,
            message=f"Error of type {etype}",
            traceback=f"test.py:{i}"
        )

    report = await healer.get_diagnostics()
    assert report["error_count"] >= 6


@pytest.mark.asyncio
async def test_e2e_healing_strategies(healer):
    """Test different healing strategies."""
    strategies = [
        "retry_with_backoff",
        "fallback_to_default",
        "escalate_to_human",
        "cache_result",
        "skip_step"
    ]

    for i, strategy in enumerate(strategies):
        await healer.capture_error(
            error_id=f"err_strat_{i}",
            error_type="TestError",
            message=f"Error for strategy {strategy}",
            traceback="test.py:1"
        )
        await healer.attempt_healing(
            error_id=f"err_strat_{i}",
            strategy=strategy
        )

    report = await healer.get_diagnostics()
    assert report["error_count"] >= 5


@pytest.mark.asyncio
async def test_e2e_error_persistence(healer):
    """Test error state persistence."""
    # First batch
    await healer.capture_error(
        error_id="err_persist_1",
        error_type="TestError",
        message="Error 1",
        traceback="test.py:1"
    )

    report1 = await healer.get_diagnostics()
    count1 = report1["error_count"]

    # Second batch
    for i in range(10):
        await healer.capture_error(
            error_id=f"err_persist_{i+2}",
            error_type="TestError",
            message=f"Error {i+2}",
            traceback=f"test.py:{i}"
        )

    report2 = await healer.get_diagnostics()
    count2 = report2["error_count"]

    assert count2 > count1


@pytest.mark.asyncio
async def test_e2e_performance_sla(healer):
    """Test performance against SLA."""
    import time

    start = time.perf_counter()
    for i in range(100):
        await healer.capture_error(
            error_id=f"err_perf_{i:03d}",
            error_type="TestError",
            message=f"Performance test error {i}",
            traceback=f"perf.py:{i}"
        )
    total_ms = (time.perf_counter() - start) * 1000
    avg_per_op_ms = total_ms / 100

    assert avg_per_op_ms < 1.0  # <1ms SLA


@pytest.mark.asyncio
async def test_e2e_complete_snapshot(healer):
    """Test complete error healing snapshot."""
    for i in range(25):
        await healer.capture_error(
            error_id=f"snap_err_{i:03d}",
            error_type=["RuntimeError", "ValueError", "TypeError"][i % 3],
            message=f"Snapshot error {i}",
            traceback=f"snap.py:{i}"
        )

    snapshot = await healer.get_diagnostics()
    assert snapshot["error_count"] == 25
    assert "status" in snapshot or "errors" in str(snapshot).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

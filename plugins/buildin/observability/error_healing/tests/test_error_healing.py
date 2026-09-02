"""
Comprehensive unit tests for ErrorHealing plugin.

Tests error recording, recovery tracking, error categorization, healing strategy
selection, recovery success metrics, and health checks.
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

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/error_healing/src')
from error_healing import ErrorHealing, ErrorEvent


@pytest.fixture
async def healer():
    """Fixture providing initialized healer."""
    healer = ErrorHealing()
    await healer.initialize(MagicMock())
    yield healer
    await healer.shutdown()


@pytest.mark.asyncio
async def test_initialization():
    """Test plugin initializes correctly."""
    healer = ErrorHealing()
    assert healer.error_log.__class__.__name__ == "deque"
    assert healer.error_types == {}
    assert healer.recovery_success_rate == {}
    await healer.initialize(MagicMock())
    assert healer.start_time is not None


@pytest.mark.asyncio
async def test_record_single_error(healer):
    """Test recording a single error."""
    await healer.record_error("TimeoutError", "layer_5", "Request timed out")

    assert len(healer.error_log) == 1
    assert "TimeoutError" in healer.error_types
    assert healer.error_types["TimeoutError"] == 1

    error = healer.error_log[0]
    assert error.error_type == "TimeoutError"
    assert error.component == "layer_5"
    assert error.message == "Request timed out"


@pytest.mark.asyncio
async def test_record_multiple_errors_same_type(healer):
    """Test recording multiple errors of same type."""
    for i in range(5):
        await healer.record_error("TimeoutError", f"layer_{i}", f"Timeout {i}")

    assert len(healer.error_log) == 5
    assert healer.error_types["TimeoutError"] == 5


@pytest.mark.asyncio
async def test_error_categorization(healer):
    """Test error categorization by type."""
    errors = [
        ("TimeoutError", "layer_5"),
        ("ValueError", "layer_3"),
        ("ConnectionError", "layer_2"),
        ("TimeoutError", "layer_5"),
        ("ValueError", "layer_4"),
    ]

    for error_type, component in errors:
        await healer.record_error(error_type, component, f"{error_type} in {component}")

    assert len(healer.error_types) == 3
    assert healer.error_types["TimeoutError"] == 2
    assert healer.error_types["ValueError"] == 2
    assert healer.error_types["ConnectionError"] == 1


@pytest.mark.asyncio
async def test_recovery_attempt_success(healer):
    """Test recording successful recovery attempt."""
    await healer.record_recovery_attempt("TimeoutError", success=True)

    rate = healer.recovery_success_rate["TimeoutError"]
    assert 0.0 <= rate <= 1.0


@pytest.mark.asyncio
async def test_recovery_attempt_failure(healer):
    """Test recording failed recovery attempt."""
    await healer.record_recovery_attempt("TimeoutError", success=False)

    rate = healer.recovery_success_rate["TimeoutError"]
    assert rate == 0.0


@pytest.mark.asyncio
async def test_recovery_success_rate_averaging(healer):
    """Test recovery success rate with exponential moving average."""
    error_type = "TimeoutError"

    # Record 5 attempts: success, success, fail, success, fail
    outcomes = [True, True, False, True, False]
    for success in outcomes:
        await healer.record_recovery_attempt(error_type, success=success)

    rate = healer.recovery_success_rate[error_type]
    assert 0.0 < rate < 1.0  # Should be between 0 and 1


@pytest.mark.asyncio
async def test_recovery_rate_all_success(healer):
    """Test recovery success rate when all attempts succeed."""
    for _ in range(10):
        await healer.record_recovery_attempt("TimeoutError", success=True)

    rate = healer.recovery_success_rate["TimeoutError"]
    assert rate > 0.9  # Should be close to 1.0


@pytest.mark.asyncio
async def test_recovery_rate_all_failure(healer):
    """Test recovery success rate when all attempts fail."""
    for _ in range(10):
        await healer.record_recovery_attempt("TimeoutError", success=False)

    rate = healer.recovery_success_rate["TimeoutError"]
    assert rate < 0.1  # Should be close to 0.0


@pytest.mark.asyncio
async def test_get_error_summary_empty(healer):
    """Test error summary when no errors recorded."""
    summary = await healer.get_error_summary()

    assert summary["total_errors"] == 0
    assert summary["error_types"] == {}


@pytest.mark.asyncio
async def test_get_error_summary_populated(healer):
    """Test error summary with recorded errors."""
    await healer.record_error("TimeoutError", "layer_5", "Timeout")
    await healer.record_error("ValueError", "layer_3", "Bad value")
    await healer.record_recovery_attempt("TimeoutError", success=True)

    summary = await healer.get_error_summary()

    assert summary["total_errors"] == 2
    assert "TimeoutError" in summary["error_types"]
    assert "ValueError" in summary["error_types"]
    assert "recovery_rates" in summary


@pytest.mark.asyncio
async def test_get_recent_errors(healer):
    """Test that recent errors appear in summary."""
    for i in range(15):
        await healer.record_error("TestError", f"layer_{i}", f"Error {i}")

    summary = await healer.get_error_summary()

    # Should only include last 10 errors
    assert len(summary["recent_errors"]) == 10


@pytest.mark.asyncio
async def test_error_truncation(healer):
    """Test that long error messages are truncated for safety."""
    long_message = "x" * 500
    await healer.record_error("LongError", "layer_0", long_message)

    error = healer.error_log[0]
    assert len(error.message) <= 200


@pytest.mark.asyncio
async def test_error_buffer_capacity(healer):
    """Test error log buffer capacity management."""
    # Record more errors than buffer capacity (500)
    for i in range(600):
        await healer.record_error("TestError", "layer_0", f"Error {i}")

    # Buffer should not exceed max
    assert len(healer.error_log) <= 500


@pytest.mark.asyncio
async def test_health_check_healthy(healer):
    """Test health check when error count is low."""
    for _ in range(10):
        await healer.record_error("TestError", "layer_0", "Error")

    health = await healer.on_health_check()
    assert health.ok is True


@pytest.mark.asyncio
async def test_health_check_unhealthy(healer):
    """Test health check when error count is high."""
    # Record 150 errors (exceeds threshold of 100)
    for i in range(150):
        await healer.record_error("TestError", "layer_0", f"Error {i}")

    health = await healer.on_health_check()
    assert health.ok is False
    assert "Recent errors" in health.message


@pytest.mark.asyncio
async def test_get_diagnostics(healer):
    """Test unified diagnostics interface."""
    await healer.record_error("TimeoutError", "layer_5", "Timeout")
    await healer.record_error("ValueError", "layer_3", "Bad value")

    diagnostics = await healer.get_diagnostics()

    assert "total_errors" in diagnostics
    assert "error_types" in diagnostics
    assert diagnostics["total_errors"] == 2


@pytest.mark.asyncio
async def test_concurrent_error_recording(healer):
    """Test concurrent error recording."""
    async def record_errors(error_type, count):
        for i in range(count):
            await healer.record_error(error_type, f"layer_{i}", f"Error {i}")

    await asyncio.gather(
        record_errors("TimeoutError", 10),
        record_errors("ValueError", 10),
        record_errors("ConnectionError", 10),
    )

    assert len(healer.error_log) == 30
    assert len(healer.error_types) == 3


@pytest.mark.asyncio
async def test_tier_property():
    """Test tier classification."""
    healer = ErrorHealing()
    assert healer.get_tier() == "general"


@pytest.mark.asyncio
async def test_max_latency_requirement():
    """Test latency constraint."""
    healer = ErrorHealing()
    assert healer.get_max_latency_ms() == 1


@pytest.mark.asyncio
async def test_shutdown_graceful(healer):
    """Test graceful shutdown."""
    await healer.shutdown()
    # No exception should be raised


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

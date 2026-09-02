"""
Comprehensive unit tests for SelfRepairEngine plugin.

Tests repair attempt tracking, success/failure rates, repair strategy statistics,
MTBF calculation, and health checks.
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

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/self_repair_engine/src')
from self_repair_engine import SelfRepairEngine, RepairAttempt


@pytest.fixture
async def engine():
    """Fixture providing initialized engine."""
    engine = SelfRepairEngine()
    await engine.initialize(MagicMock())
    yield engine
    await engine.shutdown()


@pytest.mark.asyncio
async def test_initialization():
    """Test plugin initializes correctly."""
    engine = SelfRepairEngine()
    assert engine.repair_log.__class__.__name__ == "deque"
    assert engine.repair_stats == {}
    assert engine.mtbf_by_component == {}
    await engine.initialize(MagicMock())
    assert engine.start_time is not None


@pytest.mark.asyncio
async def test_record_repair_attempt_success(engine):
    """Test recording successful repair attempt."""
    await engine.record_repair_attempt("layer_5", "retry", success=True, duration_ms=50.0)

    assert len(engine.repair_log) == 1
    attempt = engine.repair_log[0]
    assert attempt.component == "layer_5"
    assert attempt.repair_type == "retry"
    assert attempt.success is True
    assert attempt.duration_ms == 50.0


@pytest.mark.asyncio
async def test_record_repair_attempt_failure(engine):
    """Test recording failed repair attempt."""
    await engine.record_repair_attempt("layer_3", "escalate", success=False, duration_ms=100.0)

    assert len(engine.repair_log) == 1
    attempt = engine.repair_log[0]
    assert attempt.success is False


@pytest.mark.asyncio
async def test_multiple_repair_attempts(engine):
    """Test recording multiple repair attempts."""
    for i in range(5):
        await engine.record_repair_attempt("layer_1", "retry", success=(i % 2 == 0), duration_ms=25.0 * (i + 1))

    assert len(engine.repair_log) == 5


@pytest.mark.asyncio
async def test_repair_type_categorization(engine):
    """Test repair attempt categorization by type."""
    repair_types = ["retry", "restart", "escalate", "failover"]

    for repair_type in repair_types:
        await engine.record_repair_attempt("layer_0", repair_type, success=True, duration_ms=50.0)

    assert len(engine.repair_stats) == 4
    for repair_type in repair_types:
        assert repair_type in engine.repair_stats


@pytest.mark.asyncio
async def test_success_rate_calculation(engine):
    """Test success rate calculation."""
    # 5 successful, 5 failed = 50% success rate
    for i in range(10):
        success = i % 2 == 0
        await engine.record_repair_attempt("layer_1", "retry", success=success, duration_ms=50.0)

    summary = await engine.get_repair_summary()
    assert summary["total_repairs"] == 10
    assert summary["successful"] == 5
    assert summary["success_rate_percent"] == 50.0


@pytest.mark.asyncio
async def test_success_rate_all_successful(engine):
    """Test success rate when all repairs succeed."""
    for _ in range(10):
        await engine.record_repair_attempt("layer_1", "retry", success=True, duration_ms=50.0)

    summary = await engine.get_repair_summary()
    assert summary["success_rate_percent"] == 100.0


@pytest.mark.asyncio
async def test_success_rate_all_failed(engine):
    """Test success rate when all repairs fail."""
    for _ in range(10):
        await engine.record_repair_attempt("layer_1", "retry", success=False, duration_ms=50.0)

    summary = await engine.get_repair_summary()
    assert summary["successful"] == 0
    assert summary["success_rate_percent"] == 0.0


@pytest.mark.asyncio
async def test_repair_type_statistics(engine):
    """Test statistics aggregation per repair type."""
    await engine.record_repair_attempt("comp_1", "retry", success=True, duration_ms=30.0)
    await engine.record_repair_attempt("comp_1", "retry", success=True, duration_ms=40.0)
    await engine.record_repair_attempt("comp_1", "escalate", success=False, duration_ms=200.0)

    stats = engine.repair_stats["retry"]
    assert stats["attempts"] == 2
    assert stats["successes"] == 2
    assert stats["avg_duration_ms"] == 35.0

    stats_escalate = engine.repair_stats["escalate"]
    assert stats_escalate["attempts"] == 1
    assert stats_escalate["successes"] == 0


@pytest.mark.asyncio
async def test_average_duration_tracking(engine):
    """Test average duration tracking for repair type."""
    durations = [100.0, 200.0, 150.0]
    for duration in durations:
        await engine.record_repair_attempt("layer_1", "retry", success=True, duration_ms=duration)

    stats = engine.repair_stats["retry"]
    assert stats["avg_duration_ms"] == pytest.approx(150.0, abs=0.1)


@pytest.mark.asyncio
async def test_get_repair_summary_empty(engine):
    """Test repair summary when no repairs recorded."""
    summary = await engine.get_repair_summary()

    assert summary["total_repairs"] == 0
    assert summary["repair_types"] == {}


@pytest.mark.asyncio
async def test_get_repair_summary_populated(engine):
    """Test repair summary with recorded repairs."""
    await engine.record_repair_attempt("layer_5", "restart", success=True, duration_ms=100.0)
    await engine.record_repair_attempt("layer_5", "restart", success=False, duration_ms=150.0)

    summary = await engine.get_repair_summary()

    assert "total_repairs" in summary
    assert "successful" in summary
    assert "success_rate_percent" in summary
    assert "repair_stats" in summary
    assert summary["total_repairs"] == 2
    assert summary["successful"] == 1


@pytest.mark.asyncio
async def test_get_diagnostics(engine):
    """Test unified diagnostics interface."""
    await engine.record_repair_attempt("layer_1", "retry", success=True, duration_ms=50.0)

    diagnostics = await engine.get_diagnostics()

    assert "total_repairs" in diagnostics
    assert "successful" in diagnostics
    assert "success_rate_percent" in diagnostics


@pytest.mark.asyncio
async def test_repair_log_capacity(engine):
    """Test repair log buffer capacity management."""
    # Record more repairs than buffer capacity (500)
    for i in range(600):
        await engine.record_repair_attempt("layer_1", "retry", success=True, duration_ms=50.0)

    # Buffer should not exceed max
    assert len(engine.repair_log) <= 500


@pytest.mark.asyncio
async def test_health_check_healthy(engine):
    """Test health check when success rate is high."""
    for _ in range(10):
        await engine.record_repair_attempt("layer_0", "retry", success=True, duration_ms=50.0)

    health = await engine.on_health_check()
    assert health.ok is True
    assert "success rate" in health.message.lower()


@pytest.mark.asyncio
async def test_health_check_unhealthy(engine):
    """Test health check when success rate is low."""
    # Record mostly failed repairs (20% success rate)
    for i in range(10):
        success = i == 0  # Only 1 out of 10 succeeds
        await engine.record_repair_attempt("layer_0", "retry", success=success, duration_ms=50.0)

    health = await engine.on_health_check()
    assert health.ok is False


@pytest.mark.asyncio
async def test_concurrent_repair_recording(engine):
    """Test concurrent repair attempt recording."""
    async def record_repairs(component, repair_type, count):
        for i in range(count):
            await engine.record_repair_attempt(component, repair_type, success=(i % 2 == 0), duration_ms=50.0)

    await asyncio.gather(
        record_repairs("layer_1", "retry", 10),
        record_repairs("layer_2", "escalate", 10),
        record_repairs("layer_3", "failover", 10),
    )

    assert len(engine.repair_log) == 30


@pytest.mark.asyncio
async def test_multiple_repair_types(engine):
    """Test handling of multiple repair types."""
    repair_types = ["retry", "restart", "escalate", "failover"]

    for repair_type in repair_types:
        for i in range(5):
            await engine.record_repair_attempt("layer_0", repair_type, success=(i % 2 == 0), duration_ms=50.0)

    summary = await engine.get_repair_summary()
    assert len(summary["repair_stats"]) == 4
    assert summary["total_repairs"] == 20


@pytest.mark.asyncio
async def test_tier_property():
    """Test tier classification."""
    engine = SelfRepairEngine()
    assert engine.get_tier() == "general"


@pytest.mark.asyncio
async def test_max_latency_requirement():
    """Test latency constraint."""
    engine = SelfRepairEngine()
    assert engine.get_max_latency_ms() == 1


@pytest.mark.asyncio
async def test_shutdown_graceful(engine):
    """Test graceful shutdown."""
    await engine.shutdown()
    # No exception should be raised


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

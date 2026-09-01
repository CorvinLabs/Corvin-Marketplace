"""
Unit tests for SelfRepairEngine plugin.

Tests repair attempt recording, success rates, and repair statistics.
"""

import pytest
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
from self_repair_engine import SelfRepairEngine


@pytest.fixture
def engine():
    return SelfRepairEngine()


@pytest.mark.asyncio
async def test_initialization(engine):
    await engine.initialize(MagicMock())
    assert engine.start_time is not None


@pytest.mark.asyncio
async def test_record_repair_attempt_success(engine):
    await engine.record_repair_attempt("layer_5", "retry", success=True, duration_ms=50.0)
    assert len(engine.repair_log) == 1


@pytest.mark.asyncio
async def test_get_repair_summary(engine):
    await engine.record_repair_attempt("layer_5", "restart", success=True, duration_ms=100.0)
    await engine.record_repair_attempt("layer_5", "restart", success=False, duration_ms=150.0)

    summary = await engine.get_repair_summary()
    assert summary["total_repairs"] == 2
    assert summary["successful"] == 1


@pytest.mark.asyncio
async def test_success_rate_calculation(engine):
    for i in range(10):
        success = i % 2 == 0
        await engine.record_repair_attempt("layer_1", "retry", success=success, duration_ms=50.0)

    summary = await engine.get_repair_summary()
    assert summary["success_rate_percent"] == 50.0


@pytest.mark.asyncio
async def test_repair_type_stats(engine):
    await engine.record_repair_attempt("comp_1", "retry", success=True, duration_ms=30.0)
    await engine.record_repair_attempt("comp_1", "escalate", success=False, duration_ms=200.0)

    summary = await engine.get_repair_summary()
    assert "retry" in summary["repair_stats"]
    assert "escalate" in summary["repair_stats"]


@pytest.mark.asyncio
async def test_repair_log_limit(engine):
    for i in range(600):
        await engine.record_repair_attempt("layer_1", "retry", success=True, duration_ms=50.0)

    assert len(engine.repair_log) <= 500


@pytest.mark.asyncio
async def test_average_duration_tracking(engine):
    await engine.record_repair_attempt("layer_1", "retry", success=True, duration_ms=100.0)
    await engine.record_repair_attempt("layer_1", "retry", success=True, duration_ms=200.0)

    stats = engine.repair_stats["retry"]
    assert stats["avg_duration_ms"] == 150.0


@pytest.mark.asyncio
async def test_tier_property(engine):
    assert engine.get_tier() == "general"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Unit tests for ErrorHealing plugin.

Tests error recording, recovery tracking, and error summaries.
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

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/error_healing/src')
from error_healing import ErrorHealing


@pytest.fixture
def healer():
    return ErrorHealing()


@pytest.mark.asyncio
async def test_initialization(healer):
    await healer.initialize(MagicMock())
    assert healer.start_time is not None


@pytest.mark.asyncio
async def test_record_error(healer):
    await healer.record_error("TimeoutError", "layer_5", "Request timed out")
    assert len(healer.error_log) == 1
    assert "TimeoutError" in healer.error_types


@pytest.mark.asyncio
async def test_record_recovery_success(healer):
    await healer.record_recovery_attempt("TimeoutError", success=True)
    rate = healer.recovery_success_rate["TimeoutError"]
    assert rate > 0.0


@pytest.mark.asyncio
async def test_get_error_summary(healer):
    await healer.record_error("TimeoutError", "layer_5", "Timeout")
    await healer.record_recovery_attempt("TimeoutError", True)

    summary = await healer.get_error_summary()
    assert summary["total_errors"] == 1
    assert "TimeoutError" in summary["error_types"]


@pytest.mark.asyncio
async def test_multiple_error_types(healer):
    await healer.record_error("TimeoutError", "layer_5", "Timeout")
    await healer.record_error("ValueError", "layer_3", "Bad value")

    assert len(healer.error_types) == 2


@pytest.mark.asyncio
async def test_recovery_rate_averaging(healer):
    for i in range(5):
        await healer.record_recovery_attempt("TimeoutError", success=(i % 2 == 0))

    rate = healer.recovery_success_rate["TimeoutError"]
    assert 0.0 <= rate <= 1.0


@pytest.mark.asyncio
async def test_error_truncation(healer):
    long_error = "x" * 500
    await healer.record_error("TestError", "layer_0", long_error)

    error = healer.error_log[0]
    assert len(error.message) <= 200


@pytest.mark.asyncio
async def test_tier_property(healer):
    assert healer.get_tier() == "general"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

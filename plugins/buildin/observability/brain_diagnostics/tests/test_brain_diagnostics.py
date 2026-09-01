"""
Unit tests for BrainDiagnostics plugin.

Tests metric recording, component statistics, health checks,
and error rate tracking.
"""

import pytest
from unittest.mock import MagicMock
import sys

# Mock corvin_plugins
mock_plugin_base = MagicMock()
mock_plugin_base.DeterministicPlugin = object
mock_plugin_base.PluginTier = MagicMock()
mock_plugin_base.PluginTier.GENERAL = "general"
mock_protocol = MagicMock()
mock_protocol.HealthStatus = MagicMock()

sys.modules['corvin_plugins'] = MagicMock()
sys.modules['corvin_plugins.plugin_base'] = mock_plugin_base
sys.modules['corvin_plugins.protocol'] = mock_protocol

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/brain_diagnostics/src')
from brain_diagnostics import BrainDiagnostics, BrainMetric


@pytest.fixture
def diagnostics():
    """Create a diagnostics instance for testing."""
    return BrainDiagnostics()


@pytest.mark.asyncio
async def test_initialization(diagnostics):
    """Test plugin initialization."""
    context = MagicMock()
    await diagnostics.initialize(context)

    assert diagnostics.context == context
    assert diagnostics.start_time is not None


@pytest.mark.asyncio
async def test_record_metric(diagnostics):
    """Test recording a single metric."""
    metric = BrainMetric(
        component="layer_5",
        latency_ms=2.5,
        error_count=0,
        success_count=1,
    )
    await diagnostics.record_metric(metric)

    assert len(diagnostics.metrics_buffer) == 1
    assert "layer_5" in diagnostics.component_stats


@pytest.mark.asyncio
async def test_record_layer_latency_success(diagnostics):
    """Test recording successful layer latency."""
    await diagnostics.record_layer_latency("5", 2.3, success=True)

    assert len(diagnostics.metrics_buffer) == 1
    metric = diagnostics.metrics_buffer[0]
    assert metric.latency_ms == 2.3
    assert metric.success_count == 1
    assert metric.error_count == 0


@pytest.mark.asyncio
async def test_record_layer_latency_failure(diagnostics):
    """Test recording failed layer latency."""
    await diagnostics.record_layer_latency("5", 5.0, success=False)

    metric = diagnostics.metrics_buffer[0]
    assert metric.success_count == 0
    assert metric.error_count == 1


@pytest.mark.asyncio
async def test_record_cache_hit(diagnostics):
    """Test recording cache hit."""
    await diagnostics.record_cache_hit("session_memory", hit=True)

    metric = diagnostics.metrics_buffer[0]
    assert "cache_session_memory" in metric.component
    assert metric.latency_ms == 0.1
    assert metric.cache_hit_rate == 100.0


@pytest.mark.asyncio
async def test_record_cache_miss(diagnostics):
    """Test recording cache miss."""
    await diagnostics.record_cache_hit("session_memory", hit=False)

    metric = diagnostics.metrics_buffer[0]
    assert metric.latency_ms == 0.5
    assert metric.cache_hit_rate == 0.0


@pytest.mark.asyncio
async def test_record_memory_usage(diagnostics):
    """Test recording memory usage."""
    await diagnostics.record_memory_usage("brain_context", 256.5)

    metric = diagnostics.metrics_buffer[0]
    assert metric.memory_mb == 256.5
    assert metric.component == "memory_brain_context"


@pytest.mark.asyncio
async def test_component_statistics_calculation(diagnostics):
    """Test rolling statistics computation."""
    # Record multiple metrics for same component
    await diagnostics.record_layer_latency("5", 1.0, success=True)
    await diagnostics.record_layer_latency("5", 2.0, success=True)
    await diagnostics.record_layer_latency("5", 3.0, success=False)

    stats = diagnostics.component_stats["layer_5"]

    assert stats["count"] == 3
    assert stats["success_count"] == 2
    assert stats["error_count"] == 1
    assert stats["max_latency"] == 3.0
    assert stats["error_rate"] == pytest.approx(33.33, abs=0.1)


@pytest.mark.asyncio
async def test_get_component_diagnostics(diagnostics):
    """Test retrieving component diagnostics."""
    await diagnostics.record_layer_latency("5", 2.5, success=True)
    await diagnostics.record_layer_latency("5", 3.5, success=False)

    diag = await diagnostics.get_component_diagnostics("layer_5")

    assert diag is not None
    assert diag["component"] == "layer_5"
    assert diag["sample_count"] == 2
    assert diag["error_rate"] > 0


@pytest.mark.asyncio
async def test_get_nonexistent_component_diagnostics(diagnostics):
    """Test retrieving nonexistent component diagnostics."""
    diag = await diagnostics.get_component_diagnostics("nonexistent")
    assert diag is None


@pytest.mark.asyncio
async def test_get_overall_diagnostics_no_data(diagnostics):
    """Test diagnostics when no metrics collected."""
    diag = await diagnostics.get_overall_diagnostics()

    assert diag["status"] == "no_data"
    assert diag["component_count"] == 0


@pytest.mark.asyncio
async def test_get_overall_diagnostics_operational(diagnostics):
    """Test overall diagnostics in operational state."""
    for i in range(10):
        await diagnostics.record_layer_latency(f"layer_{i}", 1.0, success=True)

    diag = await diagnostics.get_overall_diagnostics()

    assert diag["status"] == "operational"
    assert diag["error_rate_percent"] == 0.0
    assert diag["total_operations"] == 10


@pytest.mark.asyncio
async def test_get_overall_diagnostics_degraded(diagnostics):
    """Test overall diagnostics when error rate is elevated."""
    for i in range(100):
        success = (i % 20) != 0  # 5% error rate
        await diagnostics.record_layer_latency("layer_0", 1.0, success=success)

    diag = await diagnostics.get_overall_diagnostics()

    assert diag["status"] == "degraded"
    assert 4.0 < diag["error_rate_percent"] < 6.0


@pytest.mark.asyncio
async def test_get_overall_diagnostics_slow(diagnostics):
    """Test overall diagnostics when latency is high."""
    for i in range(10):
        await diagnostics.record_layer_latency("layer_0", 75.0, success=True)

    diag = await diagnostics.get_overall_diagnostics()

    assert diag["status"] == "slow"


@pytest.mark.asyncio
async def test_metrics_buffer_capacity(diagnostics):
    """Test that metrics buffer respects maxlen."""
    for i in range(2000):
        await diagnostics.record_metric(BrainMetric(
            component=f"layer_{i % 10}",
            latency_ms=1.0,
        ))

    assert len(diagnostics.metrics_buffer) == 1000


@pytest.mark.asyncio
async def test_error_rate_calculation(diagnostics):
    """Test error rate calculation is accurate."""
    # 80% success, 20% error
    for i in range(100):
        success = (i % 5) != 0
        await diagnostics.record_layer_latency("layer_0", 1.0, success=success)

    stats = diagnostics.component_stats["layer_0"]
    assert stats["error_rate"] == 20.0


@pytest.mark.asyncio
async def test_multiple_components_independent(diagnostics):
    """Test that multiple components maintain independent stats."""
    await diagnostics.record_layer_latency("layer_1", 1.0, success=True)
    await diagnostics.record_layer_latency("layer_2", 2.0, success=False)

    stats_1 = diagnostics.component_stats["layer_1"]
    stats_2 = diagnostics.component_stats["layer_2"]

    assert stats_1["avg_latency"] == 1.0
    assert stats_2["avg_latency"] == 2.0
    assert stats_1["error_count"] == 0
    assert stats_2["error_count"] == 1


@pytest.mark.asyncio
async def test_tier_property(diagnostics):
    """Test that plugin declares correct tier."""
    tier = diagnostics.get_tier()
    assert tier == "general"


@pytest.mark.asyncio
async def test_max_latency_property(diagnostics):
    """Test sub-millisecond latency requirement."""
    latency = diagnostics.get_max_latency_ms()
    assert latency <= 1


@pytest.mark.asyncio
async def test_shutdown(diagnostics):
    """Test graceful shutdown."""
    await diagnostics.initialize(MagicMock())
    await diagnostics.shutdown()

    assert diagnostics.context is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

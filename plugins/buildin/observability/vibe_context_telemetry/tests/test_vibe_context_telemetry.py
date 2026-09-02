"""
Comprehensive unit tests for VibeContextTelemetry plugin.

Tests context update recording, latency tracking, size metrics, session
statistics, and health checks.
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

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/vibe_context_telemetry/src')
from vibe_context_telemetry import VibeContextTelemetry, ContextUpdate


@pytest.fixture
async def telemetry():
    """Fixture providing initialized telemetry."""
    telemetry = VibeContextTelemetry()
    await telemetry.initialize(MagicMock())
    yield telemetry
    await telemetry.shutdown()


@pytest.mark.asyncio
async def test_initialization():
    """Test plugin initializes correctly."""
    telemetry = VibeContextTelemetry()
    assert telemetry.update_log.__class__.__name__ == "deque"
    assert telemetry.session_context_size == {}
    assert telemetry.update_stats == {}
    await telemetry.initialize(MagicMock())
    assert telemetry.start_time is not None


@pytest.mark.asyncio
async def test_record_single_context_update(telemetry):
    """Test recording a single context update."""
    await telemetry.record_context_update("session_1", update_size_bytes=512, latency_ms=2.5, success=True)

    assert len(telemetry.update_log) == 1
    assert telemetry.session_context_size["session_1"] == 512

    update = telemetry.update_log[0]
    assert update.session_id == "session_1"
    assert update.update_size_bytes == 512
    assert update.latency_ms == 2.5
    assert update.success is True


@pytest.mark.asyncio
async def test_record_context_update_failure(telemetry):
    """Test recording failed context update."""
    await telemetry.record_context_update("session_1", 512, 5.0, success=False)

    update = telemetry.update_log[0]
    assert update.success is False


@pytest.mark.asyncio
async def test_record_multiple_updates_same_session(telemetry):
    """Test recording multiple updates for same session."""
    for i in range(5):
        await telemetry.record_context_update("session_1", 512 * (i + 1), 2.0 + i)

    assert len(telemetry.update_log) == 5
    assert telemetry.session_context_size["session_1"] == 512 * 5


@pytest.mark.asyncio
async def test_multiple_sessions(telemetry):
    """Test tracking multiple sessions independently."""
    for i in range(1, 4):
        await telemetry.record_context_update(f"session_{i}", 512 * i, 2.0)

    assert len(telemetry.session_context_size) == 3
    assert telemetry.session_context_size["session_1"] == 512
    assert telemetry.session_context_size["session_2"] == 1024
    assert telemetry.session_context_size["session_3"] == 1536


@pytest.mark.asyncio
async def test_get_context_telemetry_empty(telemetry):
    """Test context telemetry when no updates recorded."""
    data = await telemetry.get_context_telemetry()

    assert data["total_updates"] == 0
    assert data["sessions_active"] == 0
    assert data["total_context_size_bytes"] == 0


@pytest.mark.asyncio
async def test_get_context_telemetry_populated(telemetry):
    """Test context telemetry with recorded updates."""
    await telemetry.record_context_update("session_1", 512, 2.0)
    await telemetry.record_context_update("session_2", 1024, 3.0)

    data = await telemetry.get_context_telemetry()

    assert data["total_updates"] == 2
    assert data["sessions_active"] == 2
    assert "avg_update_latency_ms" in data
    assert "update_stats" in data


@pytest.mark.asyncio
async def test_average_latency_calculation(telemetry):
    """Test average latency calculation."""
    latencies = [1.0, 3.0, 5.0]
    for latency in latencies:
        await telemetry.record_context_update("session_1", 512, latency)

    data = await telemetry.get_context_telemetry()
    assert data["avg_update_latency_ms"] == pytest.approx(3.0, abs=0.1)


@pytest.mark.asyncio
async def test_total_context_size_aggregation(telemetry):
    """Test total context size aggregation."""
    await telemetry.record_context_update("session_1", 1000, 1.0)
    await telemetry.record_context_update("session_2", 2000, 1.0)
    await telemetry.record_context_update("session_3", 3000, 1.0)

    data = await telemetry.get_context_telemetry()
    assert data["total_context_size_bytes"] == 6000


@pytest.mark.asyncio
async def test_update_stats_per_session(telemetry):
    """Test per-session statistics tracking."""
    await telemetry.record_context_update("session_1", 512, 2.0)
    await telemetry.record_context_update("session_1", 1024, 4.0)

    stats = telemetry.update_stats["session_1"]
    assert stats["updates"] == 2
    assert stats["max_size_bytes"] == 1024
    assert stats["avg_latency_ms"] == pytest.approx(3.0, abs=0.1)


@pytest.mark.asyncio
async def test_update_log_capacity_management(telemetry):
    """Test update log buffer capacity (maxlen=1000)."""
    for i in range(1500):
        await telemetry.record_context_update(f"session_{i % 10}", 512, 1.0)

    assert len(telemetry.update_log) <= 1000


@pytest.mark.asyncio
async def test_session_context_size_update(telemetry):
    """Test that session context size is updated on each recording."""
    await telemetry.record_context_update("session_1", 512, 1.0)
    assert telemetry.session_context_size["session_1"] == 512

    await telemetry.record_context_update("session_1", 1024, 1.0)
    assert telemetry.session_context_size["session_1"] == 1024


@pytest.mark.asyncio
async def test_large_context_updates(telemetry):
    """Test handling of large context sizes."""
    large_size = 1024 * 1024  # 1MB
    await telemetry.record_context_update("session_1", large_size, 10.0)

    data = await telemetry.get_context_telemetry()
    assert data["total_context_size_bytes"] == large_size


@pytest.mark.asyncio
async def test_high_latency_updates(telemetry):
    """Test handling of high latency updates."""
    await telemetry.record_context_update("session_1", 512, 50.0)
    await telemetry.record_context_update("session_1", 512, 60.0)

    data = await telemetry.get_context_telemetry()
    assert data["avg_update_latency_ms"] > 50.0


@pytest.mark.asyncio
async def test_get_diagnostics(telemetry):
    """Test unified diagnostics interface."""
    await telemetry.record_context_update("session_1", 512, 2.0)

    diagnostics = await telemetry.get_diagnostics()

    assert "total_updates" in diagnostics
    assert "sessions_active" in diagnostics


@pytest.mark.asyncio
async def test_health_check_healthy(telemetry):
    """Test health check when latency is acceptable."""
    for _ in range(10):
        await telemetry.record_context_update("session_1", 512, 10.0)

    health = await telemetry.on_health_check()
    assert health.ok is True
    assert "latency" in health.message.lower()


@pytest.mark.asyncio
async def test_health_check_degraded(telemetry):
    """Test health check when latency is high."""
    # Record updates with high latency
    for _ in range(10):
        await telemetry.record_context_update("session_1", 512, 100.0)

    health = await telemetry.on_health_check()
    assert health.ok is False


@pytest.mark.asyncio
async def test_concurrent_context_updates(telemetry):
    """Test concurrent context update recording."""
    async def record_updates(session_id, count):
        for i in range(count):
            await telemetry.record_context_update(session_id, 512, 2.0)

    await asyncio.gather(
        record_updates("session_1", 10),
        record_updates("session_2", 10),
        record_updates("session_3", 10),
    )

    assert len(telemetry.update_log) == 30
    assert len(telemetry.session_context_size) == 3


@pytest.mark.asyncio
async def test_tier_property():
    """Test tier classification."""
    telemetry = VibeContextTelemetry()
    assert telemetry.get_tier() == "general"


@pytest.mark.asyncio
async def test_max_latency_requirement():
    """Test latency constraint."""
    telemetry = VibeContextTelemetry()
    assert telemetry.get_max_latency_ms() == 1


@pytest.mark.asyncio
async def test_shutdown_graceful(telemetry):
    """Test graceful shutdown."""
    await telemetry.shutdown()
    # No exception should be raised


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Unit tests for VibeHealthMonitor plugin.

Tests session health recording, scoring, and overall health calculation.
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

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/vibe_health_monitor/src')
from vibe_health_monitor import VibeHealthMonitor


@pytest.fixture
def monitor():
    return VibeHealthMonitor()


@pytest.mark.asyncio
async def test_initialization(monitor):
    await monitor.initialize(MagicMock())
    assert monitor.start_time is not None


@pytest.mark.asyncio
async def test_record_session_health(monitor):
    await monitor.record_session_health("session_1", health_score=95.0, state="active", memory_mb=256)

    assert "session_1" in monitor.sessions
    assert len(monitor.health_history) == 1


@pytest.mark.asyncio
async def test_get_session_health(monitor):
    await monitor.record_session_health("session_1", 85.0, "running", 512, errors=2)

    health = await monitor.get_session_health("session_1")
    assert health["health_score"] == 85.0
    assert health["memory_mb"] == 512
    assert health["errors"] == 2


@pytest.mark.asyncio
async def test_get_overall_health_healthy(monitor):
    await monitor.record_session_health("session_1", 95.0, "running", 256)
    await monitor.record_session_health("session_2", 90.0, "running", 256)

    overall = await monitor.get_overall_health()
    assert overall["status"] == "healthy"
    assert overall["healthy_sessions"] == 2


@pytest.mark.asyncio
async def test_get_overall_health_degraded(monitor):
    await monitor.record_session_health("session_1", 60.0, "running", 256)
    await monitor.record_session_health("session_2", 70.0, "running", 256)

    overall = await monitor.get_overall_health()
    assert overall["status"] == "degraded"


@pytest.mark.asyncio
async def test_health_score_clamping(monitor):
    await monitor.record_session_health("session_1", 150.0, "running", 256)
    await monitor.record_session_health("session_2", -50.0, "running", 256)

    health1 = await monitor.get_session_health("session_1")
    health2 = await monitor.get_session_health("session_2")

    assert health1["health_score"] == 100.0
    assert health2["health_score"] == 0.0


@pytest.mark.asyncio
async def test_total_memory_calculation(monitor):
    await monitor.record_session_health("session_1", 90.0, "running", 256)
    await monitor.record_session_health("session_2", 85.0, "running", 512)

    overall = await monitor.get_overall_health()
    assert overall["total_memory_mb"] == 768


@pytest.mark.asyncio
async def test_health_history_limit(monitor):
    for i in range(1500):
        await monitor.record_session_health(f"session_{i}", 90.0, "running", 256)

    assert len(monitor.health_history) <= 1000


@pytest.mark.asyncio
async def test_tier_property(monitor):
    assert monitor.get_tier() == "general"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

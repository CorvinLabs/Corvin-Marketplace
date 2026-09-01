"""
Unit tests for HeartbeatMonitor plugin.

Tests heartbeat recording, stale detection, and health checking.
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta
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

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/heartbeat_monitor/src')
from heartbeat_monitor import HeartbeatMonitor


@pytest.fixture
def monitor():
    return HeartbeatMonitor()


@pytest.mark.asyncio
async def test_initialization(monitor):
    await monitor.initialize(MagicMock())
    assert monitor.start_time is not None


@pytest.mark.asyncio
async def test_record_heartbeat(monitor):
    await monitor.record_heartbeat("instance_1", latency_ms=1.5, healthy=True)
    assert monitor.last_heartbeat is not None
    assert len(monitor.heartbeat_history) == 1


@pytest.mark.asyncio
async def test_is_instance_alive_fresh(monitor):
    await monitor.record_heartbeat("instance_1", latency_ms=1.0, healthy=True)
    alive = await monitor.is_instance_alive()
    assert alive is True


@pytest.mark.asyncio
async def test_get_heartbeat_status(monitor):
    await monitor.record_heartbeat("instance_1", latency_ms=2.0, healthy=True)
    status = await monitor.get_heartbeat_status()

    assert status["status"] == "alive"
    assert status["instance_id"] == "instance_1"


@pytest.mark.asyncio
async def test_missed_beats_tracking(monitor):
    await monitor.record_heartbeat("instance_1", latency_ms=1.0, healthy=False)
    await monitor.record_heartbeat("instance_1", latency_ms=1.0, healthy=False)

    assert monitor.missed_beats == 2


@pytest.mark.asyncio
async def test_heartbeat_history_limit(monitor):
    for i in range(1500):
        await monitor.record_heartbeat(f"instance", latency_ms=1.0)

    assert len(monitor.heartbeat_history) <= 1000


@pytest.mark.asyncio
async def test_multiple_instances(monitor):
    await monitor.record_heartbeat("instance_1", latency_ms=1.0)
    await monitor.record_heartbeat("instance_2", latency_ms=1.5)

    # Last recorded is instance_2
    assert monitor.instance_id == "instance_2"


@pytest.mark.asyncio
async def test_tier_property(monitor):
    assert monitor.get_tier() == "general"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

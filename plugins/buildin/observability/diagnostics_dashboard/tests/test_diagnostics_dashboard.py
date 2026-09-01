"""
Unit tests for DiagnosticsDashboard plugin.

Tests snapshots, metrics recording, alerts, and dashboard state.
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

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/diagnostics_dashboard/src')
from diagnostics_dashboard import DiagnosticsDashboard


@pytest.fixture
def dashboard():
    return DiagnosticsDashboard()


@pytest.mark.asyncio
async def test_initialization(dashboard):
    await dashboard.initialize(MagicMock())
    assert dashboard.start_time is not None


@pytest.mark.asyncio
async def test_record_component_metric(dashboard):
    await dashboard.record_component_metric("cpu", "usage_percent", 45.5)
    assert "cpu" in dashboard.components
    assert dashboard.components["cpu"]["usage_percent"]["value"] == 45.5


@pytest.mark.asyncio
async def test_add_alert(dashboard):
    await dashboard.add_alert("critical", "CPU usage high", "cpu")
    assert len(dashboard.alerts) == 1
    assert dashboard.alerts[0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_capture_snapshot(dashboard):
    await dashboard.capture_snapshot("operational", 2.5, 10.0)
    assert len(dashboard.snapshots) == 1
    snapshot = dashboard.snapshots[0]
    assert snapshot.overall_health == "operational"
    assert snapshot.error_rate == 2.5


@pytest.mark.asyncio
async def test_get_current_dashboard(dashboard):
    await dashboard.record_component_metric("memory", "used_mb", 512)
    await dashboard.add_alert("warning", "Memory usage moderate")
    await dashboard.capture_snapshot("operational", 1.0, 5.0)

    dashboard_state = await dashboard.get_current_dashboard()
    assert dashboard_state["snapshot"] is not None
    assert "components" in dashboard_state


@pytest.mark.asyncio
async def test_alert_limit(dashboard):
    for i in range(150):
        await dashboard.add_alert("info", f"Alert {i}")

    assert len(dashboard.alerts) <= dashboard.max_alerts


@pytest.mark.asyncio
async def test_multiple_components(dashboard):
    await dashboard.record_component_metric("cpu", "usage", 50.0)
    await dashboard.record_component_metric("memory", "usage", 75.0)

    assert len(dashboard.components) == 2


@pytest.mark.asyncio
async def test_tier_property(dashboard):
    assert dashboard.get_tier() == "general"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

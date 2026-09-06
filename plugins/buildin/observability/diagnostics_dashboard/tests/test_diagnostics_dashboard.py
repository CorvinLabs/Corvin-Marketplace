"""
Comprehensive unit tests for DiagnosticsDashboard plugin.

Tests component metrics, snapshot capture, alert management, dashboard state,
and health checks.
"""

import pytest
import asyncio
from unittest.mock import MagicMock
import sys



from diagnostics_dashboard import DiagnosticsDashboard, DashboardSnapshot


@pytest.fixture
async def dashboard():
    """Fixture providing initialized dashboard."""
    dashboard = DiagnosticsDashboard()
    await dashboard.initialize(MagicMock())
    yield dashboard
    await dashboard.shutdown()


@pytest.mark.asyncio
async def test_initialization():
    """Test plugin initializes correctly."""
    dashboard = DiagnosticsDashboard()
    assert dashboard.snapshots.__class__.__name__ == "deque"
    assert dashboard.components == {}
    assert dashboard.alerts == []
    assert dashboard.max_alerts == 100
    await dashboard.initialize(MagicMock())
    assert dashboard.start_time is not None


@pytest.mark.asyncio
async def test_record_single_component_metric(dashboard):
    """Test recording a single component metric."""
    await dashboard.record_component_metric("cpu", "usage_percent", 45.5)

    assert "cpu" in dashboard.components
    assert "usage_percent" in dashboard.components["cpu"]
    assert dashboard.components["cpu"]["usage_percent"]["value"] == 45.5
    assert "timestamp" in dashboard.components["cpu"]["usage_percent"]


@pytest.mark.asyncio
async def test_record_multiple_metrics_same_component(dashboard):
    """Test recording multiple metrics for same component."""
    await dashboard.record_component_metric("cpu", "usage_percent", 45.5)
    await dashboard.record_component_metric("cpu", "temp_celsius", 65.0)

    assert len(dashboard.components["cpu"]) == 2


@pytest.mark.asyncio
async def test_multiple_components(dashboard):
    """Test tracking multiple components."""
    await dashboard.record_component_metric("cpu", "usage", 50.0)
    await dashboard.record_component_metric("memory", "used_mb", 512)
    await dashboard.record_component_metric("disk", "used_percent", 75.0)

    assert len(dashboard.components) == 3
    assert "cpu" in dashboard.components
    assert "memory" in dashboard.components
    assert "disk" in dashboard.components


@pytest.mark.asyncio
async def test_add_critical_alert(dashboard):
    """Test adding a critical alert."""
    await dashboard.add_alert("critical", "CPU usage high", "cpu")

    assert len(dashboard.alerts) == 1
    alert = dashboard.alerts[0]
    assert alert["severity"] == "critical"
    assert alert["message"] == "CPU usage high"
    assert alert["component"] == "cpu"
    assert "timestamp" in alert


@pytest.mark.asyncio
async def test_add_alert_without_component(dashboard):
    """Test adding alert without specifying component."""
    await dashboard.add_alert("warning", "System performance degraded")

    assert len(dashboard.alerts) == 1
    alert = dashboard.alerts[0]
    assert alert["component"] is None


@pytest.mark.asyncio
async def test_add_multiple_alerts(dashboard):
    """Test adding multiple alerts."""
    severities = ["critical", "warning", "info"]

    for severity in severities:
        await dashboard.add_alert(severity, f"{severity.upper()} alert")

    assert len(dashboard.alerts) == 3


@pytest.mark.asyncio
async def test_alert_management_limit(dashboard):
    """Test alert limit enforcement (max_alerts=100)."""
    for i in range(150):
        await dashboard.add_alert("info", f"Alert {i}")

    # Should keep only recent 100 alerts
    assert len(dashboard.alerts) <= dashboard.max_alerts


@pytest.mark.asyncio
async def test_capture_snapshot(dashboard):
    """Test capturing a system snapshot."""
    await dashboard.capture_snapshot("operational", error_rate=2.5, avg_latency_ms=10.0)

    assert len(dashboard.snapshots) == 1
    snapshot = dashboard.snapshots[0]
    assert snapshot.overall_health == "operational"
    assert snapshot.error_rate == 2.5
    assert snapshot.avg_latency_ms == 10.0


@pytest.mark.asyncio
async def test_multiple_snapshots(dashboard):
    """Test capturing multiple snapshots."""
    for i in range(5):
        await dashboard.capture_snapshot("operational", error_rate=i * 1.0, avg_latency_ms=5.0 + i)

    assert len(dashboard.snapshots) == 5


@pytest.mark.asyncio
async def test_snapshot_includes_alert_count(dashboard):
    """Test that snapshot includes active alert count."""
    await dashboard.add_alert("warning", "Test alert")
    await dashboard.add_alert("critical", "Test alert")

    await dashboard.capture_snapshot("degraded", 3.0, 15.0)

    snapshot = dashboard.snapshots[0]
    assert snapshot.active_alerts == 2


@pytest.mark.asyncio
async def test_snapshot_capacity(dashboard):
    """Test snapshot buffer capacity (maxlen=1440)."""
    # Capture more snapshots than max
    for i in range(2000):
        await dashboard.capture_snapshot("operational", 1.0, 5.0)

    # Should keep only recent 1440 snapshots
    assert len(dashboard.snapshots) <= 1440


@pytest.mark.asyncio
async def test_get_current_dashboard_empty(dashboard):
    """Test dashboard when no data recorded."""
    state = await dashboard.get_current_dashboard()

    assert state["snapshot"] is None
    assert state["components"] == {}
    assert state["recent_alerts"] == []
    assert state["snapshot_history_size"] == 0


@pytest.mark.asyncio
async def test_get_current_dashboard_populated(dashboard):
    """Test dashboard with recorded data."""
    await dashboard.record_component_metric("cpu", "usage", 50.0)
    await dashboard.record_component_metric("memory", "used_mb", 512)
    await dashboard.add_alert("warning", "Test alert")
    await dashboard.capture_snapshot("operational", 1.0, 5.0)

    state = await dashboard.get_current_dashboard()

    assert state["snapshot"] is not None
    assert len(state["components"]) == 2
    assert len(state["recent_alerts"]) == 1
    assert state["snapshot_history_size"] == 1


@pytest.mark.asyncio
async def test_recent_alerts_limit(dashboard):
    """Test that only recent alerts are shown in dashboard."""
    for i in range(20):
        await dashboard.add_alert("info", f"Alert {i}")

    state = await dashboard.get_current_dashboard()

    # Should only show last 10 alerts
    assert len(state["recent_alerts"]) <= 10


@pytest.mark.asyncio
async def test_get_diagnostics(dashboard):
    """Test unified diagnostics interface."""
    await dashboard.record_component_metric("cpu", "usage", 50.0)
    await dashboard.add_alert("warning", "Test alert")

    diagnostics = await dashboard.get_diagnostics()

    assert "snapshot" in diagnostics
    assert "components" in diagnostics
    assert "recent_alerts" in diagnostics


@pytest.mark.asyncio
async def test_health_check_with_snapshots(dashboard):
    """Test health check when snapshots exist."""
    await dashboard.capture_snapshot("operational", 1.0, 5.0)

    health = await dashboard.on_health_check()
    assert health.ok is True
    assert "Snapshots" in health.message


@pytest.mark.asyncio
async def test_health_check_no_snapshots(dashboard):
    """Test health check when no snapshots captured."""
    health = await dashboard.on_health_check()
    assert health.ok is False


@pytest.mark.asyncio
async def test_concurrent_metric_recording(dashboard):
    """Test concurrent component metric recording."""
    async def record_metrics(component, count):
        for i in range(count):
            await dashboard.record_component_metric(component, f"metric_{i}", float(i))

    await asyncio.gather(
        record_metrics("cpu", 5),
        record_metrics("memory", 5),
        record_metrics("disk", 5),
    )

    assert len(dashboard.components) == 3
    assert len(dashboard.components["cpu"]) == 5


@pytest.mark.asyncio
async def test_alert_variety(dashboard):
    """Test handling different alert severities."""
    severities = ["critical", "warning", "info", "debug"]

    for severity in severities:
        await dashboard.add_alert(severity, f"Test {severity} alert")

    assert len(dashboard.alerts) == 4
    alert_types = [a["severity"] for a in dashboard.alerts]
    for severity in severities:
        assert severity in alert_types


@pytest.mark.asyncio
async def test_metric_value_updates(dashboard):
    """Test that metric values are updated when re-recorded."""
    await dashboard.record_component_metric("cpu", "usage", 50.0)
    assert dashboard.components["cpu"]["usage"]["value"] == 50.0

    await dashboard.record_component_metric("cpu", "usage", 75.0)
    assert dashboard.components["cpu"]["usage"]["value"] == 75.0


@pytest.mark.asyncio
async def test_tier_property():
    """Test tier classification."""
    dashboard = DiagnosticsDashboard()
    assert dashboard.get_tier() == "general"


@pytest.mark.asyncio
async def test_max_latency_requirement():
    """Test latency constraint."""
    dashboard = DiagnosticsDashboard()
    assert dashboard.get_max_latency_ms() == 1


@pytest.mark.asyncio
async def test_shutdown_graceful(dashboard):
    """Test graceful shutdown."""
    await dashboard.shutdown()
    # No exception should be raised


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

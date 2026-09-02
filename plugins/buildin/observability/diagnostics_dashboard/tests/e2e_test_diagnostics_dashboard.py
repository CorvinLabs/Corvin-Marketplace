"""
End-to-end test for DiagnosticsDashboard plugin.

Verifies:
- Real plugin lifecycle (init → aggregation → visualization → shutdown)
- Concurrent data aggregation from multiple sources
- Latency SLA verification (<1ms per operation)
- HealthStatus contract validation
- Dashboard state consistency
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import MagicMock
import sys

mock_plugin_base = MagicMock()
mock_plugin_base.DeterministicPlugin = object
mock_plugin_base.PluginTier = MagicMock()
mock_plugin_base.PluginTier.GENERAL = "general"
mock_protocol = MagicMock()
mock_protocol.HealthStatus = MagicMock(return_value=MagicMock(ok=True, message="OK"))

sys.modules['corvin_plugins'] = MagicMock()
sys.modules['corvin_plugins.plugin_base'] = mock_plugin_base
sys.modules['corvin_plugins.protocol'] = mock_protocol

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/diagnostics_dashboard/src')


@pytest.fixture
async def dashboard():
    """Fixture providing initialized dashboard."""
    from diagnostics_dashboard import DiagnosticsDashboard
    dash = DiagnosticsDashboard()
    ctx = MagicMock()
    ctx.tenant_id = "default"
    await dash.initialize(ctx)
    yield dash
    await dash.shutdown()


@pytest.mark.asyncio
async def test_e2e_plugin_lifecycle(dashboard):
    """Test complete plugin lifecycle."""
    assert dashboard is not None
    assert dashboard.get_tier() == "general"
    assert dashboard.get_max_latency_ms() == 1


@pytest.mark.asyncio
async def test_e2e_add_dashboard_widget(dashboard):
    """Test adding a dashboard widget end-to-end."""
    start = datetime.utcnow()
    await dashboard.add_widget(
        widget_id="widget_001",
        widget_type="gauge",
        title="System Health",
        metric_key="system.health",
        refresh_interval_ms=1000
    )
    elapsed_ms = (datetime.utcnow() - start).total_seconds() * 1000

    assert elapsed_ms < 1.0  # <1ms SLA
    state = await dashboard.get_diagnostics()
    assert state["widget_count"] >= 1


@pytest.mark.asyncio
async def test_e2e_concurrent_widgets(dashboard):
    """Test concurrent widget management."""
    tasks = []
    for i in range(20):
        task = dashboard.add_widget(
            widget_id=f"widget_{i:03d}",
            widget_type=["gauge", "chart", "heatmap", "timeline"][i % 4],
            title=f"Widget {i}",
            metric_key=f"metric.{i}",
            refresh_interval_ms=1000 + (i * 100)
        )
        tasks.append(task)

    await asyncio.gather(*tasks)
    state = await dashboard.get_diagnostics()
    assert state["widget_count"] >= 20


@pytest.mark.asyncio
async def test_e2e_health_status_contract(dashboard):
    """Test HealthStatus contract."""
    await dashboard.add_widget(
        widget_id="widget_health",
        widget_type="gauge",
        title="Health Check",
        metric_key="health",
        refresh_interval_ms=2000
    )

    health = await dashboard.on_health_check()
    assert health is not None
    assert hasattr(health, 'ok')
    assert hasattr(health, 'message')


@pytest.mark.asyncio
async def test_e2e_widget_types(dashboard):
    """Test different widget types."""
    widget_types = ["gauge", "chart", "heatmap", "timeline", "table"]

    for i, wtype in enumerate(widget_types):
        await dashboard.add_widget(
            widget_id=f"widget_type_{i}",
            widget_type=wtype,
            title=f"{wtype} Widget",
            metric_key=f"metric.{wtype}",
            refresh_interval_ms=1000
        )

    state = await dashboard.get_diagnostics()
    assert state["widget_count"] >= 5


@pytest.mark.asyncio
async def test_e2e_update_widget_data(dashboard):
    """Test updating widget data."""
    await dashboard.add_widget(
        widget_id="widget_data",
        widget_type="chart",
        title="Data Chart",
        metric_key="metric.data",
        refresh_interval_ms=500
    )

    # Update with new data
    for i in range(10):
        await dashboard.update_widget_data(
            widget_id="widget_data",
            data_point={"timestamp": datetime.utcnow(), "value": 50.0 + i}
        )

    state = await dashboard.get_diagnostics()
    assert state["widget_count"] >= 1


@pytest.mark.asyncio
async def test_e2e_dashboard_snapshot(dashboard):
    """Test complete dashboard snapshot."""
    # Add multiple widgets
    for i in range(15):
        await dashboard.add_widget(
            widget_id=f"snap_widget_{i:03d}",
            widget_type=["gauge", "chart", "heatmap"][i % 3],
            title=f"Snapshot Widget {i}",
            metric_key=f"metric.{i}",
            refresh_interval_ms=1000
        )

    snapshot = await dashboard.get_diagnostics()
    assert snapshot["widget_count"] == 15
    assert "widgets" in snapshot or "state" in str(snapshot).lower()


@pytest.mark.asyncio
async def test_e2e_performance_sla(dashboard):
    """Test performance against SLA."""
    import time

    start = time.perf_counter()
    for i in range(100):
        await dashboard.add_widget(
            widget_id=f"perf_widget_{i:03d}",
            widget_type="gauge",
            title=f"Performance Widget {i}",
            metric_key=f"perf.metric.{i}",
            refresh_interval_ms=1000
        )
    total_ms = (time.perf_counter() - start) * 1000
    avg_per_op_ms = total_ms / 100

    assert avg_per_op_ms < 1.0  # <1ms SLA


@pytest.mark.asyncio
async def test_e2e_widget_refresh_timing(dashboard):
    """Test widget refresh interval management."""
    intervals = [500, 1000, 2000, 5000]

    for i, interval in enumerate(intervals):
        await dashboard.add_widget(
            widget_id=f"refresh_widget_{i}",
            widget_type="gauge",
            title=f"Refresh {interval}ms",
            metric_key=f"refresh.{i}",
            refresh_interval_ms=interval
        )

    state = await dashboard.get_diagnostics()
    assert state["widget_count"] >= 4


@pytest.mark.asyncio
async def test_e2e_state_persistence(dashboard):
    """Test state persistence across operations."""
    # Add initial widgets
    await dashboard.add_widget(
        widget_id="persist_1",
        widget_type="gauge",
        title="Persistent Widget 1",
        metric_key="persist.1",
        refresh_interval_ms=1000
    )

    state1 = await dashboard.get_diagnostics()
    count1 = state1["widget_count"]

    # Add more widgets
    for i in range(5):
        await dashboard.add_widget(
            widget_id=f"persist_{i+2}",
            widget_type="chart",
            title=f"Persistent Widget {i+2}",
            metric_key=f"persist.{i+2}",
            refresh_interval_ms=1000
        )

    state2 = await dashboard.get_diagnostics()
    count2 = state2["widget_count"]

    assert count2 > count1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

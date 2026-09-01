"""
Aggregated diagnostics dashboard.

Compiles:
- System-wide health snapshot
- Per-component statistics
- Historical trends
- Alerting thresholds

ADR-0532: OS-Skills Architecture — Deterministic observability layer.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime
from collections import deque

from corvin_plugins.plugin_base import DeterministicPlugin, PluginTier


@dataclass
class DashboardSnapshot:
    """Point-in-time system snapshot."""
    timestamp: datetime
    overall_health: str
    component_count: int
    error_rate: float
    avg_latency_ms: float
    active_alerts: int


class DiagnosticsDashboard(DeterministicPlugin):
    """
    Unified diagnostics dashboard.

    Exposes:
    - Real-time system health
    - Per-component metrics
    - Alert summaries
    - <1ms aggregation latency
    """

    def __init__(self):
        """Initialize the dashboard."""
        self.snapshots: deque = deque(maxlen=1440)  # ~24h at 1-min intervals
        self.components: Dict[str, Dict] = {}
        self.alerts: List[Dict] = []
        self.max_alerts = 100

    def get_tier(self) -> PluginTier:
        return PluginTier.GENERAL

    def get_max_latency_ms(self) -> int:
        return 1

    async def initialize(self, context):
        """Initialize dashboard."""
        self.context = context
        self.start_time = datetime.utcnow()

    async def record_component_metric(self, component: str, metric_name: str, value: float):
        """Record a component metric."""
        if component not in self.components:
            self.components[component] = {}

        self.components[component][metric_name] = {
            "value": value,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def add_alert(self, severity: str, message: str, component: Optional[str] = None):
        """Add an alert to the dashboard."""
        alert = {
            "severity": severity,
            "message": message,
            "component": component,
            "timestamp": datetime.utcnow().isoformat(),
        }

        self.alerts.append(alert)

        # Keep only recent alerts
        if len(self.alerts) > self.max_alerts:
            self.alerts = self.alerts[-self.max_alerts:]

    async def capture_snapshot(self, overall_health: str, error_rate: float, avg_latency_ms: float):
        """Capture a system snapshot."""
        snapshot = DashboardSnapshot(
            timestamp=datetime.utcnow(),
            overall_health=overall_health,
            component_count=len(self.components),
            error_rate=error_rate,
            avg_latency_ms=avg_latency_ms,
            active_alerts=len(self.alerts),
        )

        self.snapshots.append(snapshot)

    async def get_diagnostics(self) -> Dict:
        """Return current dashboard snapshot (unified interface)."""
        return await self.get_current_dashboard()

    async def get_current_dashboard(self) -> Dict:
        """Get current dashboard state."""
        latest_snapshot = None
        if self.snapshots:
            latest = self.snapshots[-1]
            latest_snapshot = {
                "timestamp": latest.timestamp.isoformat(),
                "overall_health": latest.overall_health,
                "component_count": latest.component_count,
                "error_rate": latest.error_rate,
                "avg_latency_ms": latest.avg_latency_ms,
                "active_alerts": latest.active_alerts,
            }

        return {
            "snapshot": latest_snapshot,
            "components": self.components,
            "recent_alerts": self.alerts[-10:],
            "snapshot_history_size": len(self.snapshots),
        }

    async def on_health_check(self):
        """Report dashboard health."""
        from corvin_plugins.protocol import HealthStatus

        ok = len(self.snapshots) > 0
        message = f"Snapshots: {len(self.snapshots)}, Alerts: {len(self.alerts)}"

        return HealthStatus(ok=ok, message=message)

    async def shutdown(self):
        """Graceful shutdown."""
        pass

"""
Example: Deterministic Plugin

Fast, predictable, <1ms execution.
Perfect for real-time critical functions.
"""

from corvin_plugins.plugin_base import DeterministicPlugin, PluginTier
from dataclasses import dataclass


@dataclass
class HealthMetric:
    component: str
    latency_ms: float
    status: str


class VibePerformanceMonitor(DeterministicPlugin):
    """
    Ultra-fast Vibe session performance monitor.

    Runs on every Brain metric, must complete in <1ms.
    """

    def __init__(self):
        self.latency_threshold = 50  # ms
        self.error_count = 0
        self.metrics = []

    def get_tier(self) -> PluginTier:
        return PluginTier.CRITICAL

    def get_max_latency_ms(self) -> int:
        return 1  # Must be sub-millisecond

    async def initialize(self, context):
        """Setup monitor."""
        self.context = context
        print(f"✅ {self.__class__.__name__} initialized (deterministic, <1ms)")

    async def on_brain_metric(self, metric: HealthMetric):
        """
        Called on every Brain subsystem metric.
        MUST complete in <1ms, no I/O, no LLM.
        """
        # Pure Python, in-memory only
        self.metrics.append(metric)

        # Check for latency anomaly
        if metric.latency_ms > self.latency_threshold:
            self.error_count += 1

            # Alert (also in-memory)
            if self.error_count > 5:
                alert_msg = f"Vibe latency spike: {metric.latency_ms}ms"
                await self._queue_alert(alert_msg)

    async def on_health_check(self):
        """Report health status."""
        from corvin_plugins.protocol import HealthStatus

        avg_latency = sum(m.latency_ms for m in self.metrics) / len(self.metrics) if self.metrics else 0

        return HealthStatus(
            ok=avg_latency < self.latency_threshold,
            message=f"Avg latency: {avg_latency:.1f}ms (threshold: {self.latency_threshold}ms)",
        )

    async def _queue_alert(self, message: str):
        """Queue alert (synchronous, no I/O)."""
        # Just record; real alerting happens asynchronously elsewhere
        print(f"⚠️  Alert: {message}")

    async def shutdown(self):
        """Cleanup."""
        print(f"ℹ️ {self.__class__.__name__} shut down")


# Usage in marketplace plugin.json:
"""
{
  "id": "plugin:buildin-observability-vibe_performance_monitor",
  "type": "plugin",
  "name": "Vibe Performance Monitor (Deterministic)",
  "version": "1.0.0",

  "plugin_type": "deterministic",
  "plugin_tier": "critical",
  "plugin_capabilities": {
    "max_latency_ms": 1,
    "requires_llm": false,
    "can_call_other_plugins": false,
    "learnable": false
  },

  "category": "observability",
  "description": "Ultra-fast, <1ms Vibe performance monitoring"
}
"""

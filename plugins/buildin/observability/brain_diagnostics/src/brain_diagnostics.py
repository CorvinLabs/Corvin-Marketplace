"""
Brain subsystem diagnostics monitor.

Monitors aggregate health metrics for the Brain system:
- Memory usage & cache hit rates
- Layer latencies & error rates
- Concurrent task capacity
- Overall system throughput

ADR-0532: OS-Skills Architecture — Deterministic observability layer.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from collections import deque

from corvin_plugins.plugin_base import DeterministicPlugin, PluginTier


@dataclass
class BrainMetric:
    """A single brain subsystem metric."""
    component: str
    latency_ms: float
    error_count: int = 0
    success_count: int = 0
    memory_mb: Optional[float] = None
    cache_hit_rate: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


class BrainDiagnostics(DeterministicPlugin):
    """
    Fast aggregated Brain health monitor.

    Tracks:
    - Per-layer latency histograms
    - Cache performance
    - Error/success rates
    - Memory footprint
    - Sub-millisecond latency (<1ms)
    """

    def __init__(self):
        """Initialize the monitor."""
        self.metrics_buffer = deque(maxlen=1000)  # Keep last 1000 metrics
        self.component_stats: Dict[str, Dict] = {}
        self.overall_health = "operational"

    def get_tier(self) -> PluginTier:
        """This is general observability, not critical."""
        return PluginTier.GENERAL

    def get_max_latency_ms(self) -> int:
        """Must complete in <1ms (pure in-memory operations)."""
        return 1

    async def initialize(self, context):
        """Initialize with Brain context."""
        self.context = context
        self.start_time = datetime.utcnow()

    async def record_metric(self, metric: BrainMetric):
        """Record a Brain subsystem metric."""
        self.metrics_buffer.append(metric)
        self._update_component_stats(metric)

    async def record_layer_latency(self, layer_name: str, latency_ms: float, success: bool):
        """Record latency for a specific layer."""
        metric = BrainMetric(
            component=f"layer_{layer_name}",
            latency_ms=latency_ms,
            success_count=1 if success else 0,
            error_count=0 if success else 1,
        )
        await self.record_metric(metric)

    async def record_cache_hit(self, component: str, hit: bool, evict_rate: Optional[float] = None):
        """Record cache hit/miss event."""
        metric = BrainMetric(
            component=f"cache_{component}",
            latency_ms=0.1 if hit else 0.5,
            success_count=1 if hit else 0,
            error_count=0,
            cache_hit_rate=100.0 if hit else 0.0,
        )
        await self.record_metric(metric)

    async def record_memory_usage(self, component: str, memory_mb: float):
        """Record component memory footprint."""
        metric = BrainMetric(
            component=f"memory_{component}",
            latency_ms=0.0,
            memory_mb=memory_mb,
        )
        await self.record_metric(metric)

    async def get_component_diagnostics(self, component: str) -> Optional[Dict]:
        """Get diagnostics for a specific component."""
        if component not in self.component_stats:
            return None

        stats = self.component_stats[component]
        return {
            "component": component,
            "avg_latency_ms": stats.get("avg_latency", 0.0),
            "max_latency_ms": stats.get("max_latency", 0.0),
            "error_rate": stats.get("error_rate", 0.0),
            "sample_count": stats.get("count", 0),
            "cache_hit_rate": stats.get("cache_hit_rate"),
            "memory_mb": stats.get("memory_mb"),
        }

    async def get_diagnostics(self) -> Dict:
        """Return overall diagnostic snapshot (unified interface)."""
        return await self.get_overall_diagnostics()

    async def get_overall_diagnostics(self) -> Dict:
        """Return aggregated diagnostics snapshot."""
        if not self.metrics_buffer:
            return {
                "status": "no_data",
                "message": "No metrics collected yet",
                "component_count": 0,
            }

        # Calculate averages
        all_latencies = [m.latency_ms for m in self.metrics_buffer if m.latency_ms > 0]
        total_errors = sum(m.error_count for m in self.metrics_buffer)
        total_success = sum(m.success_count for m in self.metrics_buffer)
        total_ops = total_errors + total_success

        error_rate = (total_errors / total_ops * 100) if total_ops > 0 else 0.0
        avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0.0
        max_latency = max(all_latencies) if all_latencies else 0.0

        # Determine overall health
        if error_rate > 10:
            health = "unhealthy"
        elif error_rate > 5:
            health = "degraded"
        elif avg_latency > 50:
            health = "slow"
        else:
            health = "operational"

        return {
            "status": health,
            "avg_latency_ms": round(avg_latency, 2),
            "max_latency_ms": round(max_latency, 2),
            "error_rate_percent": round(error_rate, 2),
            "total_operations": total_ops,
            "component_count": len(self.component_stats),
            "buffer_usage": len(self.metrics_buffer),
        }

    async def on_health_check(self):
        """Report health status."""
        from corvin_plugins.protocol import HealthStatus

        diagnostics = await self.get_overall_diagnostics()
        status = diagnostics["status"] == "operational"
        message = f"Brain Health: {diagnostics['status']}, " \
                  f"Latency: {diagnostics['avg_latency_ms']}ms, " \
                  f"Errors: {diagnostics['error_rate_percent']}%"

        return HealthStatus(ok=status, message=message)

    def _update_component_stats(self, metric: BrainMetric):
        """Update rolling statistics for a component."""
        component = metric.component

        if component not in self.component_stats:
            self.component_stats[component] = {
                "count": 0,
                "avg_latency": 0.0,
                "max_latency": 0.0,
                "error_count": 0,
                "success_count": 0,
            }

        stats = self.component_stats[component]
        stats["count"] += 1
        stats["error_count"] += metric.error_count
        stats["success_count"] += metric.success_count

        # Update max latency
        if metric.latency_ms > stats["max_latency"]:
            stats["max_latency"] = metric.latency_ms

        # Update average latency (simple running average)
        old_avg = stats["avg_latency"]
        new_avg = (old_avg * (stats["count"] - 1) + metric.latency_ms) / stats["count"]
        stats["avg_latency"] = new_avg

        # Calculate error rate
        total_ops = stats["error_count"] + stats["success_count"]
        if total_ops > 0:
            stats["error_rate"] = stats["error_count"] / total_ops * 100
        else:
            stats["error_rate"] = 0.0

        # Store additional fields
        if metric.cache_hit_rate is not None:
            stats["cache_hit_rate"] = metric.cache_hit_rate
        if metric.memory_mb is not None:
            stats["memory_mb"] = metric.memory_mb

    async def shutdown(self):
        """Graceful shutdown."""
        pass

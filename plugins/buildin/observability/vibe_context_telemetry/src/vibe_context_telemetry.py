"""
Vibe context update monitor.

Tracks:
- Context update frequency & size
- Update latency
- Memory impact
- Context serialization performance

ADR-0532: OS-Skills Architecture — Deterministic observability layer.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime
from collections import deque

from corvin_plugins.plugin_base import DeterministicPlugin, PluginTier


@dataclass
class ContextUpdate:
    """A Vibe context update record."""
    session_id: str
    update_size_bytes: int
    latency_ms: float
    success: bool
    timestamp: datetime


class VibeContextTelemetry(DeterministicPlugin):
    """
    Vibe context update telemetry tracker.

    Monitors:
    - Update frequency & latency
    - Context size growth
    - Serialization performance
    - <1ms recording latency
    """

    def __init__(self):
        """Initialize context telemetry."""
        self.update_log: deque = deque(maxlen=1000)
        self.session_context_size: Dict[str, int] = {}
        self.update_stats: Dict[str, Dict] = {}

    def get_tier(self) -> PluginTier:
        return PluginTier.GENERAL

    def get_max_latency_ms(self) -> int:
        return 1

    async def initialize(self, context):
        """Initialize context telemetry."""
        self.context = context
        self.start_time = datetime.utcnow()

    async def record_context_update(
        self, session_id: str, update_size_bytes: int, latency_ms: float, success: bool = True
    ):
        """Record a context update."""
        update = ContextUpdate(
            session_id=session_id,
            update_size_bytes=update_size_bytes,
            latency_ms=latency_ms,
            success=success,
            timestamp=datetime.utcnow(),
        )

        self.update_log.append(update)
        self.session_context_size[session_id] = update_size_bytes
        self._update_stats(session_id, update)

    async def get_diagnostics(self) -> Dict:
        """Return context telemetry diagnostic snapshot (unified interface)."""
        return await self.get_context_telemetry()

    async def get_context_telemetry(self) -> Dict:
        """Get context update telemetry."""
        if not self.update_log:
            return {"total_updates": 0, "sessions": {}}

        latencies = [u.latency_ms for u in self.update_log]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

        return {
            "total_updates": len(self.update_log),
            "avg_update_latency_ms": round(avg_latency, 2),
            "sessions_active": len(self.session_context_size),
            "total_context_size_bytes": sum(self.session_context_size.values()),
            "update_stats": self.update_stats,
        }

    async def on_health_check(self):
        """Report context telemetry health."""
        from corvin_plugins.protocol import HealthStatus

        telemetry = await self.get_context_telemetry()
        avg_latency = telemetry.get("avg_update_latency_ms", 0.0)

        ok = avg_latency < 50.0  # Alert if updates getting slow
        message = f"Avg update latency: {avg_latency}ms, Sessions: {telemetry['sessions_active']}"

        return HealthStatus(ok=ok, message=message)

    def _update_stats(self, session_id: str, update: ContextUpdate):
        """Update rolling statistics."""
        if session_id not in self.update_stats:
            self.update_stats[session_id] = {
                "updates": 0,
                "avg_latency_ms": 0.0,
                "max_size_bytes": 0,
            }

        stats = self.update_stats[session_id]
        stats["updates"] += 1

        # Update average latency
        old_avg = stats["avg_latency_ms"]
        new_avg = (old_avg * (stats["updates"] - 1) + update.latency_ms) / stats["updates"]
        stats["avg_latency_ms"] = new_avg

        # Track max size
        if update.update_size_bytes > stats["max_size_bytes"]:
            stats["max_size_bytes"] = update.update_size_bytes

    async def shutdown(self):
        """Graceful shutdown."""
        pass

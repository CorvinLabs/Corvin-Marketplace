"""
Instance heartbeat monitor.

Tracks:
- Heartbeat pulse frequency & jitter
- Responsive vs. unresponsive intervals
- Stale instance detection
- System vitality metrics

ADR-0532: OS-Skills Architecture — Deterministic observability layer.
"""

from dataclasses import dataclass
from typing import Dict, Optional, List
from datetime import datetime, timedelta

from corvin_plugins.plugin_base import DeterministicPlugin, PluginTier


@dataclass
class HeartbeatRecord:
    """Single heartbeat pulse record."""
    instance_id: str
    timestamp: datetime
    latency_ms: float
    healthy: bool


class HeartbeatMonitor(DeterministicPlugin):
    """
    System heartbeat monitor.

    Tracks:
    - Instance vitality
    - Responsiveness timing
    - Stale detection
    - <1ms heartbeat recording
    """

    def __init__(self):
        """Initialize heartbeat monitor."""
        self.instance_id: Optional[str] = None
        self.last_heartbeat: Optional[datetime] = None
        self.heartbeat_history: List[HeartbeatRecord] = []
        self.heartbeat_interval_ms = 5000  # 5 seconds
        self.stale_threshold_ms = 15000  # 15 seconds = 3 missed beats
        self.missed_beats = 0

    def get_tier(self) -> PluginTier:
        return PluginTier.GENERAL

    def get_max_latency_ms(self) -> int:
        return 1

    async def initialize(self, context):
        """Initialize heartbeat monitor."""
        self.context = context
        self.start_time = datetime.utcnow()
        self.last_heartbeat = datetime.utcnow()

    async def record_heartbeat(self, instance_id: str, latency_ms: float, healthy: bool = True):
        """Record a heartbeat pulse."""
        self.instance_id = instance_id
        self.last_heartbeat = datetime.utcnow()
        self.missed_beats = 0 if healthy else self.missed_beats + 1

        record = HeartbeatRecord(
            instance_id=instance_id,
            timestamp=self.last_heartbeat,
            latency_ms=latency_ms,
            healthy=healthy,
        )

        self.heartbeat_history.append(record)

        # Keep only last 1000 records
        if len(self.heartbeat_history) > 1000:
            self.heartbeat_history = self.heartbeat_history[-1000:]

    async def is_instance_alive(self) -> bool:
        """Check if instance is alive based on heartbeat."""
        if not self.last_heartbeat:
            return False

        elapsed = (datetime.utcnow() - self.last_heartbeat).total_seconds() * 1000
        return elapsed < self.stale_threshold_ms and self.missed_beats < 3

    async def get_diagnostics(self) -> Dict:
        """Return heartbeat diagnostic snapshot (unified interface)."""
        return await self.get_heartbeat_status()

    async def get_heartbeat_status(self) -> Dict:
        """Get current heartbeat status."""
        if not self.last_heartbeat:
            return {
                "status": "unknown",
                "elapsed_ms": None,
                "alive": False,
            }

        elapsed_ms = (datetime.utcnow() - self.last_heartbeat).total_seconds() * 1000

        return {
            "status": "alive" if await self.is_instance_alive() else "stale",
            "elapsed_ms": round(elapsed_ms, 1),
            "missed_beats": self.missed_beats,
            "heartbeat_count": len(self.heartbeat_history),
            "instance_id": self.instance_id,
        }

    async def on_health_check(self):
        """Report health based on heartbeat."""
        from corvin_plugins.protocol import HealthStatus

        alive = await self.is_instance_alive()
        status_dict = await self.get_heartbeat_status()

        return HealthStatus(
            ok=alive,
            message=f"Heartbeat status: {status_dict['status']}, Elapsed: {status_dict['elapsed_ms']}ms"
        )

    async def shutdown(self):
        """Graceful shutdown."""
        pass

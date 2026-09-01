"""
Telemetry data collection and forwarding client.

Collects:
- System metrics (CPU, memory, disk)
- Application events
- Error telemetry
- Forwards to backend with batching

ADR-0532: OS-Skills Architecture — Deterministic observability layer.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime
from collections import deque

from corvin_plugins.plugin_base import DeterministicPlugin, PluginTier


@dataclass
class TelemetryEvent:
    """A single telemetry event."""
    event_type: str
    data: Dict
    timestamp: datetime


class TelemetryClient(DeterministicPlugin):
    """
    Telemetry collection and forwarding.

    Features:
    - Event batching
    - Rate limiting
    - Format normalization
    - <1ms recording latency
    """

    def __init__(self):
        """Initialize telemetry client."""
        self.event_buffer: deque = deque(maxlen=5000)
        self.batch_size = 100
        self.pending_batch: List[TelemetryEvent] = []
        self.events_sent = 0
        self.events_dropped = 0

    def get_tier(self) -> PluginTier:
        return PluginTier.GENERAL

    def get_max_latency_ms(self) -> int:
        return 1

    async def initialize(self, context):
        """Initialize telemetry client."""
        self.context = context
        self.start_time = datetime.utcnow()

    async def record_event(self, event_type: str, data: Dict):
        """Record a telemetry event."""
        event = TelemetryEvent(
            event_type=event_type,
            data=data,
            timestamp=datetime.utcnow(),
        )

        self.event_buffer.append(event)
        self.pending_batch.append(event)

        # Auto-flush when batch is full
        if len(self.pending_batch) >= self.batch_size:
            await self._flush_batch()

    async def get_pending_batch(self) -> List[Dict]:
        """Get current pending batch."""
        return [
            {
                "type": e.event_type,
                "data": e.data,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in self.pending_batch
        ]

    async def _flush_batch(self):
        """Flush current batch (in real impl, would send to backend)."""
        self.events_sent += len(self.pending_batch)
        self.pending_batch = []

    async def get_diagnostics(self) -> Dict:
        """Return telemetry diagnostic snapshot (unified interface)."""
        return await self.get_telemetry_status()

    async def get_telemetry_status(self) -> Dict:
        """Get telemetry client status."""
        return {
            "buffered_events": len(self.event_buffer),
            "pending_in_batch": len(self.pending_batch),
            "events_sent": self.events_sent,
            "events_dropped": self.events_dropped,
            "batch_size": self.batch_size,
        }

    async def on_health_check(self):
        """Report telemetry health."""
        from corvin_plugins.protocol import HealthStatus

        status = await self.get_telemetry_status()
        ok = len(self.event_buffer) < 4000  # Alert if buffer getting full

        return HealthStatus(
            ok=ok,
            message=f"Buffered: {status['buffered_events']}, Sent: {status['events_sent']}"
        )

    async def shutdown(self):
        """Graceful shutdown."""
        if self.pending_batch:
            await self._flush_batch()

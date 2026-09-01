"""
Error event monitor with recovery tracking.

Observes:
- Error frequency & patterns
- Recovery attempt outcomes
- Escalation levels
- MTTR (mean time to recovery)

ADR-0532: OS-Skills Architecture — Deterministic observability layer.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from collections import deque

from corvin_plugins.plugin_base import DeterministicPlugin, PluginTier


@dataclass
class ErrorEvent:
    """A single error observation."""
    error_type: str
    component: str
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    recovery_attempts: int = 0
    resolved: bool = False


class ErrorHealing(DeterministicPlugin):
    """
    Error observation & recovery tracker.

    Tracks:
    - Error frequencies & types
    - Recovery outcomes
    - Escalation attempts
    - <1ms latency for recording
    """

    def __init__(self):
        """Initialize error tracker."""
        self.error_log: deque = deque(maxlen=500)
        self.error_types: Dict[str, int] = {}
        self.recovery_success_rate: Dict[str, float] = {}

    def get_tier(self) -> PluginTier:
        return PluginTier.GENERAL

    def get_max_latency_ms(self) -> int:
        return 1

    async def initialize(self, context):
        """Initialize error healing tracker."""
        self.context = context
        self.start_time = datetime.utcnow()

    async def record_error(self, error_type: str, component: str, message: str):
        """Record an error event."""
        error = ErrorEvent(
            error_type=error_type,
            component=component,
            message=message[:200],  # Truncate for safety
        )

        self.error_log.append(error)

        # Update error type counters
        self.error_types[error_type] = self.error_types.get(error_type, 0) + 1

    async def record_recovery_attempt(self, error_type: str, success: bool):
        """Record a recovery attempt outcome."""
        if error_type not in self.recovery_success_rate:
            self.recovery_success_rate[error_type] = 0.0

        # Simple exponential moving average
        current = self.recovery_success_rate[error_type]
        new_value = 1.0 if success else 0.0
        self.recovery_success_rate[error_type] = 0.7 * current + 0.3 * new_value

    async def get_diagnostics(self) -> Dict:
        """Return error healing diagnostic snapshot (unified interface)."""
        return await self.get_error_summary()

    async def get_error_summary(self) -> Dict:
        """Get summary of recent errors."""
        if not self.error_log:
            return {"total_errors": 0, "error_types": {}}

        return {
            "total_errors": len(self.error_log),
            "error_types": self.error_types,
            "recovery_rates": self.recovery_success_rate,
            "recent_errors": [
                {
                    "type": e.error_type,
                    "component": e.component,
                    "message": e.message,
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in list(self.error_log)[-10:]
            ],
        }

    async def on_health_check(self):
        """Report health status."""
        from corvin_plugins.protocol import HealthStatus

        error_summary = await self.get_error_summary()
        total_errors = error_summary["total_errors"]

        ok = total_errors < 100  # Alert if too many recent errors
        message = f"Recent errors: {total_errors}"

        return HealthStatus(ok=ok, message=message)

    async def shutdown(self):
        """Graceful shutdown."""
        pass

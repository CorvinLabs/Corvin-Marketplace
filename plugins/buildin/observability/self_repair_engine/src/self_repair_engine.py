"""
Self-repair engine monitor.

Observes:
- Repair attempt types & outcomes
- Auto-recovery success rates
- Escalation decisions
- MTBF (mean time between failures)

ADR-0532: OS-Skills Architecture — Deterministic observability layer.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime
from collections import deque

from corvin_plugins.plugin_base import DeterministicPlugin, PluginTier


@dataclass
class RepairAttempt:
    """A single repair attempt."""
    component: str
    repair_type: str
    success: bool
    duration_ms: float
    timestamp: datetime


class SelfRepairEngine(DeterministicPlugin):
    """
    Self-repair observation engine.

    Tracks:
    - Repair attempt outcomes
    - Success rates per repair type
    - Time-to-repair metrics
    - <1ms recording latency
    """

    def __init__(self):
        """Initialize repair monitor."""
        self.repair_log: deque = deque(maxlen=500)
        self.repair_stats: Dict[str, Dict] = {}
        self.mtbf_by_component: Dict[str, List[float]] = {}

    def get_tier(self) -> PluginTier:
        return PluginTier.GENERAL

    def get_max_latency_ms(self) -> int:
        return 1

    async def initialize(self, context):
        """Initialize repair monitor."""
        self.context = context
        self.start_time = datetime.utcnow()

    async def record_repair_attempt(
        self, component: str, repair_type: str, success: bool, duration_ms: float
    ):
        """Record a repair attempt."""
        attempt = RepairAttempt(
            component=component,
            repair_type=repair_type,
            success=success,
            duration_ms=duration_ms,
            timestamp=datetime.utcnow(),
        )

        self.repair_log.append(attempt)
        self._update_repair_stats(attempt)

    async def get_diagnostics(self) -> Dict:
        """Return repair diagnostic snapshot (unified interface)."""
        return await self.get_repair_summary()

    async def get_repair_summary(self) -> Dict:
        """Get repair statistics summary."""
        if not self.repair_log:
            return {
                "total_repairs": 0,
                "repair_types": {},
            }

        successful = sum(1 for r in self.repair_log if r.success)
        success_rate = (successful / len(self.repair_log) * 100) if self.repair_log else 0.0

        return {
            "total_repairs": len(self.repair_log),
            "successful": successful,
            "success_rate_percent": round(success_rate, 2),
            "repair_stats": self.repair_stats,
        }

    async def on_health_check(self):
        """Report repair engine health."""
        from corvin_plugins.protocol import HealthStatus

        summary = await self.get_repair_summary()
        success_rate = summary.get("success_rate_percent", 0.0)

        ok = success_rate >= 80.0
        message = f"Repair success rate: {success_rate}%"

        return HealthStatus(ok=ok, message=message)

    def _update_repair_stats(self, attempt: RepairAttempt):
        """Update rolling repair statistics."""
        repair_type = attempt.repair_type

        if repair_type not in self.repair_stats:
            self.repair_stats[repair_type] = {
                "attempts": 0,
                "successes": 0,
                "avg_duration_ms": 0.0,
            }

        stats = self.repair_stats[repair_type]
        stats["attempts"] += 1

        if attempt.success:
            stats["successes"] += 1

        # Update average duration
        old_avg = stats["avg_duration_ms"]
        new_avg = (old_avg * (stats["attempts"] - 1) + attempt.duration_ms) / stats["attempts"]
        stats["avg_duration_ms"] = new_avg

    async def shutdown(self):
        """Graceful shutdown."""
        pass

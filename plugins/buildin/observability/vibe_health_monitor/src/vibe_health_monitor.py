"""
Vibe session health monitor.

Tracks:
- Session lifecycle state
- Health score trends
- Context stability
- Memory footprint

ADR-0532: OS-Skills Architecture — Deterministic observability layer.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime
from collections import deque

from corvin_plugins.plugin_base import DeterministicPlugin, PluginTier


@dataclass
class SessionHealth:
    """Health snapshot for a Vibe session."""
    session_id: str
    health_score: float  # 0.0 - 100.0
    state: str
    memory_mb: float
    error_count: int
    last_update: datetime


class VibeHealthMonitor(DeterministicPlugin):
    """
    Vibe session health tracker.

    Monitors:
    - Per-session health scores
    - Memory & resource usage
    - Error accumulation
    - <1ms recording latency
    """

    def __init__(self):
        """Initialize health monitor."""
        self.sessions: Dict[str, SessionHealth] = {}
        self.health_history: deque = deque(maxlen=1000)

    def get_tier(self) -> PluginTier:
        return PluginTier.GENERAL

    def get_max_latency_ms(self) -> int:
        return 1

    async def initialize(self, context):
        """Initialize health monitor."""
        self.context = context
        self.start_time = datetime.utcnow()

    async def record_session_health(
        self, session_id: str, health_score: float, state: str, memory_mb: float, errors: int = 0
    ):
        """Record a session health snapshot."""
        health = SessionHealth(
            session_id=session_id,
            health_score=max(0.0, min(100.0, health_score)),
            state=state,
            memory_mb=memory_mb,
            error_count=errors,
            last_update=datetime.utcnow(),
        )

        self.sessions[session_id] = health
        self.health_history.append(health)

    async def get_session_health(self, session_id: str) -> Optional[Dict]:
        """Get health for a specific session."""
        if session_id not in self.sessions:
            return None

        health = self.sessions[session_id]
        return {
            "session_id": session_id,
            "health_score": health.health_score,
            "state": health.state,
            "memory_mb": health.memory_mb,
            "errors": health.error_count,
            "timestamp": health.last_update.isoformat(),
        }

    async def get_diagnostics(self) -> Dict:
        """Return health diagnostic snapshot (unified interface)."""
        return await self.get_overall_health()

    async def get_overall_health(self) -> Dict:
        """Get overall system health."""
        if not self.sessions:
            return {
                "status": "unknown",
                "avg_health_score": 0.0,
                "healthy_sessions": 0,
            }

        health_scores = [s.health_score for s in self.sessions.values()]
        avg_score = sum(health_scores) / len(health_scores) if health_scores else 0.0
        healthy_count = sum(1 for s in self.sessions.values() if s.health_score >= 80.0)

        status = "healthy" if avg_score >= 80.0 else ("degraded" if avg_score >= 50.0 else "unhealthy")

        return {
            "status": status,
            "avg_health_score": round(avg_score, 1),
            "healthy_sessions": healthy_count,
            "total_sessions": len(self.sessions),
            "total_memory_mb": round(sum(s.memory_mb for s in self.sessions.values()), 1),
        }

    async def on_health_check(self):
        """Report health monitor status."""
        from corvin_plugins.protocol import HealthStatus

        overall = await self.get_overall_health()
        ok = overall["status"] != "unhealthy"

        return HealthStatus(
            ok=ok,
            message=f"System health: {overall['status']}, Sessions: {overall['total_sessions']}"
        )

    async def shutdown(self):
        """Graceful shutdown."""
        pass

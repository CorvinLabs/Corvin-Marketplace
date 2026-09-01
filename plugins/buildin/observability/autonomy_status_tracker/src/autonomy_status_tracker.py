"""
Tracks autonomous session status, hardening state, and error recovery.

Part of Vibe Engineering & Brain Subsystems observability layer.
Monitors and audits core OS features (non-critical; optional).

ADR-0532: OS-Skills Architecture — Deterministic observability layer.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import asyncio

from corvin_plugins.plugin_base import DeterministicPlugin, PluginTier


@dataclass
class SessionStatus:
    """Tracks a single autonomous session state."""
    session_id: str
    state: str  # "running", "hardening", "recovering", "failed"
    hardening_level: int  # 0-5 escalation levels
    recovery_attempts: int
    last_error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


class AutonomyStatusTracker(DeterministicPlugin):
    """
    Fast autonomy session monitor.

    Tracks:
    - Session lifecycle (init → running → hardening → recovery)
    - Hardening escalation levels
    - Error recovery attempts
    - Sub-millisecond latency (<1ms)
    """

    def __init__(self):
        """Initialize the tracker."""
        self.sessions: Dict[str, SessionStatus] = {}
        self.event_queue: List[Dict] = []
        self.max_queue_size = 1000
        self.hardening_threshold = 3

    def get_tier(self) -> PluginTier:
        """This is general observability, not critical."""
        return PluginTier.GENERAL

    def get_max_latency_ms(self) -> int:
        """Must complete in <1ms (pure in-memory operations)."""
        return 1

    async def initialize(self, context):
        """Initialize with Vibe/Brain context."""
        self.context = context
        self.start_time = datetime.utcnow()

    async def on_session_start(self, session_id: str):
        """Record session start."""
        self.sessions[session_id] = SessionStatus(
            session_id=session_id,
            state="running",
            hardening_level=0,
            recovery_attempts=0,
        )
        self._enqueue_event("session_start", {"session_id": session_id})

    async def on_hardening_begin(self, session_id: str, level: int):
        """Record hardening escalation."""
        if session_id in self.sessions:
            self.sessions[session_id].state = "hardening"
            self.sessions[session_id].hardening_level = level
            self._enqueue_event("hardening_begin", {
                "session_id": session_id,
                "level": level,
            })

    async def on_recovery_attempt(self, session_id: str, error: str):
        """Record error recovery attempt."""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.state = "recovering"
            session.last_error = error
            session.recovery_attempts += 1
            self._enqueue_event("recovery_attempt", {
                "session_id": session_id,
                "attempt": session.recovery_attempts,
                "error": error[:100],  # Truncate for safety
            })

    async def on_session_end(self, session_id: str, status: str):
        """Record session completion."""
        if session_id in self.sessions:
            self.sessions[session_id].state = status  # "completed" or "failed"
            self._enqueue_event("session_end", {
                "session_id": session_id,
                "status": status,
            })

    async def get_session_status(self, session_id: str) -> Optional[Dict]:
        """Return current status for a session."""
        if session_id not in self.sessions:
            return None
        session = self.sessions[session_id]
        return {
            "session_id": session_id,
            "state": session.state,
            "hardening_level": session.hardening_level,
            "recovery_attempts": session.recovery_attempts,
            "last_error": session.last_error,
            "timestamp": session.timestamp.isoformat(),
        }

    async def get_diagnostics(self) -> Dict:
        """Return aggregated diagnostics snapshot."""
        active_sessions = [s for s in self.sessions.values() if s.state in ("running", "hardening")]
        failed_sessions = [s for s in self.sessions.values() if s.state == "failed"]
        hardening_sessions = [s for s in self.sessions.values() if s.state == "hardening"]

        return {
            "status": "operational",
            "total_sessions": len(self.sessions),
            "active_sessions": len(active_sessions),
            "failed_sessions": len(failed_sessions),
            "hardening_sessions": len(hardening_sessions),
            "max_hardening_level": max(
                (s.hardening_level for s in self.sessions.values()),
                default=0
            ),
            "total_recovery_attempts": sum(s.recovery_attempts for s in self.sessions.values()),
            "events_queued": len(self.event_queue),
        }

    async def on_health_check(self):
        """Report health status."""
        from corvin_plugins.protocol import HealthStatus

        queue_healthy = len(self.event_queue) < self.max_queue_size
        status = "operational" if queue_healthy else "degraded"
        message = f"Sessions: {len(self.sessions)}, Queue: {len(self.event_queue)}"

        return HealthStatus(ok=queue_healthy, message=message)

    def _enqueue_event(self, event_type: str, data: Dict):
        """Queue an event (pure in-memory, <1ms)."""
        if len(self.event_queue) >= self.max_queue_size:
            self.event_queue.pop(0)  # FIFO drop oldest

        self.event_queue.append({
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def shutdown(self):
        """Graceful shutdown."""
        pass

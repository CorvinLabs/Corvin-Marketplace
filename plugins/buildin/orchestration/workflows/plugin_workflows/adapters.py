"""Adapter layer — Decouples plugin from console-specific dependencies.

Each adapter is a Protocol (interface) with:
1. A Console-backed implementation (wraps corvin_console imports)
2. A Fallback implementation (graceful degradation when console unavailable)
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, NamedTuple, Optional, Protocol

_log = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Session Adapter
# ────────────────────────────────────────────────────────────────────────────

class SessionRecord(NamedTuple):
    """Authenticated session metadata."""

    tenant_id: str
    user_id: str
    session_id: str
    csrf_token: str


class SessionBackend(Protocol):
    """Abstract session/auth provider."""

    def validate_session(self, session_id: str) -> Optional[SessionRecord]:
        """Validate a session ID. Returns SessionRecord or None if invalid."""
        ...

    def validate_csrf(self, token: str, expected: str) -> bool:
        """Validate CSRF token."""
        ...


class ConsoleSessionBackend(SessionBackend):
    """Wraps corvin_console.auth + session_auth."""

    def __init__(self, session_auth_module: Any):
        self.session_auth = session_auth_module

    def validate_session(self, session_id: str) -> Optional[SessionRecord]:
        """Query console session table."""
        try:
            rec = self.session_auth.get_session(session_id)
            if not rec:
                return None
            return SessionRecord(
                tenant_id=rec.tenant_id,
                user_id=rec.user_id,
                session_id=rec.session_id,
                csrf_token=rec.csrf_token,
            )
        except Exception as e:
            _log.exception("Session lookup failed: %s", e)
            return None

    def validate_csrf(self, token: str, expected: str) -> bool:
        """Time-constant comparison."""
        import hmac

        return hmac.compare_digest(token, expected)


class DenyAllSessionBackend(SessionBackend):
    """Fallback: deny all requests (no auth)."""

    def validate_session(self, session_id: str) -> Optional[SessionRecord]:
        _log.warning("No session backend available; denying request")
        return None

    def validate_csrf(self, token: str, expected: str) -> bool:
        return False


# ────────────────────────────────────────────────────────────────────────────
# Audit Adapter
# ────────────────────────────────────────────────────────────────────────────

class AuditBackend(Protocol):
    """Abstract audit trail logging."""

    def log_event(
        self,
        event_type: str,
        tenant_id: str,
        **payload,
    ) -> None:
        """Log an audit event (async-safe, fire-and-forget)."""
        ...


class ConsoleAuditBackend(AuditBackend):
    """Wraps corvin_console.audit.log_event()."""

    def __init__(self, audit_module: Any):
        self.audit_module = audit_module

    def log_event(
        self,
        event_type: str,
        tenant_id: str,
        **payload,
    ) -> None:
        """Delegate to console audit backend."""
        try:
            payload["tenant_id"] = tenant_id
            self.audit_module.log_event(event_type, **payload)
        except Exception as e:
            _log.exception("Audit log failed: %s", e)


class NoOpAuditBackend(AuditBackend):
    """Fallback: log locally only."""

    def log_event(
        self,
        event_type: str,
        tenant_id: str,
        **payload,
    ) -> None:
        payload["tenant_id"] = tenant_id
        _log.info("AUDIT %s: %s", event_type, payload)


# ────────────────────────────────────────────────────────────────────────────
# Storage Adapter
# ────────────────────────────────────────────────────────────────────────────

class StorageBackend(Protocol):
    """Abstract file storage (workflows per tenant)."""

    def workflows_dir(self, tenant_id: str) -> Path:
        """Get tenant's workflows directory."""
        ...

    def yaml_path(self, tenant_id: str, wid: str) -> Path:
        """Get path to workflow YAML."""
        ...

    def meta_path(self, tenant_id: str, wid: str) -> Path:
        """Get path to workflow metadata."""
        ...

    def runs_dir(self, tenant_id: str, wid: str) -> Path:
        """Get path to runs directory."""
        ...


class ForgeStorageBackend(StorageBackend):
    """Uses forge.paths.tenant_home()."""

    def __init__(self, forge_paths_module: Any):
        self.forge_paths = forge_paths_module

    def workflows_dir(self, tenant_id: str) -> Path:
        return self.forge_paths.tenant_home(tenant_id) / "workflows"

    def yaml_path(self, tenant_id: str, wid: str) -> Path:
        return self.workflows_dir(tenant_id) / f"{wid}.awp.yaml"

    def meta_path(self, tenant_id: str, wid: str) -> Path:
        return self.workflows_dir(tenant_id) / f"{wid}.meta.json"

    def runs_dir(self, tenant_id: str, wid: str) -> Path:
        return self.workflows_dir(tenant_id) / wid / "runs"


class MemoryStorageBackend(StorageBackend):
    """Fallback: in-memory storage (per-session, no persistence)."""

    def __init__(self):
        self._storage: dict[str, dict[str, Any]] = {}

    def workflows_dir(self, tenant_id: str) -> Path:
        # Fake path (not used for actual I/O)
        return Path(f"/memory/{tenant_id}/workflows")

    def yaml_path(self, tenant_id: str, wid: str) -> Path:
        return Path(f"/memory/{tenant_id}/workflows/{wid}.awp.yaml")

    def meta_path(self, tenant_id: str, wid: str) -> Path:
        return Path(f"/memory/{tenant_id}/workflows/{wid}.meta.json")

    def runs_dir(self, tenant_id: str, wid: str) -> Path:
        return Path(f"/memory/{tenant_id}/workflows/{wid}/runs")


# ────────────────────────────────────────────────────────────────────────────
# License Adapter
# ────────────────────────────────────────────────────────────────────────────

class LicenseBackend(Protocol):
    """Abstract license enforcement."""

    def assert_limit(
        self,
        feature: str,
        requested: int = 1,
        **kwargs,
    ) -> None:
        """Assert license limit. Raises LicenseLimitError if exceeded."""
        ...


class LicenseLimitError(Exception):
    """License limit exceeded."""

    pass


class ConsoleLicenseBackend(LicenseBackend):
    """Wraps corvin_operator.license.validator."""

    def __init__(self, license_module: Any):
        self.license_module = license_module

    def assert_limit(
        self,
        feature: str,
        requested: int = 1,
        **kwargs,
    ) -> None:
        try:
            self.license_module.assert_limit(feature, requested, **kwargs)
        except Exception as e:
            _log.exception("License check failed: %s", e)
            raise LicenseLimitError(feature, requested) from e


class FreeTierLicenseBackend(LicenseBackend):
    """Fallback: Free tier limits."""

    FREE_TIER = {
        "workflows_concurrent": 5,
        "workflow_max_nodes": 20,
        "workflow_max_runs": 100,
    }

    def assert_limit(
        self,
        feature: str,
        requested: int = 1,
        **kwargs,
    ) -> None:
        limit = self.FREE_TIER.get(feature)
        if limit is not None and isinstance(limit, int) and requested > limit:
            raise LicenseLimitError(feature, requested)
        _log.warning("License limit check (free tier): %s OK", feature)


# ────────────────────────────────────────────────────────────────────────────
# Spawn Gate Adapter (ADR-0648)
# ────────────────────────────────────────────────────────────────────────────

class PromptGuard(Protocol):
    """Abstract prompt guard for claude CLI safety."""

    def guard(self, text: str) -> str:
        """Sanitize prompt. Raises RuntimeError if guard unavailable."""
        ...


class ConsolePromptGuard(PromptGuard):
    """Wraps corvin_console._spawn_gates.prompt_guard."""

    def __init__(self, guard_func: Any):
        self.guard_func = guard_func

    def guard(self, text: str) -> str:
        """Apply guard to prompt head."""
        return self.guard_func(text)


class NoOpPromptGuard(PromptGuard):
    """Fallback: pass-through (unsafe, logged)."""

    def guard(self, text: str) -> str:
        _log.warning("Prompt guard unavailable; passing through unguarded payload")
        return text


# ────────────────────────────────────────────────────────────────────────────
# Scheduler Adapter (Phase 4, soft dep)
# ────────────────────────────────────────────────────────────────────────────

class SchedulerBackend(Protocol):
    """Abstract cron scheduling."""

    def register_schedule(self, wid: str, cron: str, **kwargs) -> None:
        """Register a cron schedule. Raises SchedulerError if unavailable."""
        ...

    def unregister_schedule(self, wid: str) -> None:
        """Unregister a schedule."""
        ...

    def list_schedules(self) -> list[dict[str, Any]]:
        """List all active schedules."""
        ...


class SchedulerError(Exception):
    """Scheduler operation failed."""

    pass


class ConsoleSchedulerBackend(SchedulerBackend):
    """Wraps corvin_operator.bridges.shared.scheduler."""

    def __init__(self, scheduler_module: Any):
        self.scheduler = scheduler_module

    def register_schedule(self, wid: str, cron: str, **kwargs) -> None:
        try:
            self.scheduler.register(wid, cron, **kwargs)
        except Exception as e:
            raise SchedulerError(f"Register failed: {e}") from e

    def unregister_schedule(self, wid: str) -> None:
        try:
            self.scheduler.unregister(wid)
        except Exception as e:
            raise SchedulerError(f"Unregister failed: {e}") from e

    def list_schedules(self) -> list[dict[str, Any]]:
        try:
            return self.scheduler.list_all()
        except Exception as e:
            _log.exception("List schedules failed: %s", e)
            return []


class NoOpSchedulerBackend(SchedulerBackend):
    """Fallback: no scheduling."""

    def register_schedule(self, wid: str, cron: str, **kwargs) -> None:
        _log.warning("Scheduler unavailable; schedule not registered for %s", wid)

    def unregister_schedule(self, wid: str) -> None:
        _log.warning("Scheduler unavailable; schedule not unregistered for %s", wid)

    def list_schedules(self) -> list[dict[str, Any]]:
        return []

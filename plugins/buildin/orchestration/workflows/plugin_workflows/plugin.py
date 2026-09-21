"""Workflows Plugin Entry Point — Injected into CorvinOS console/gateway.

Handles adapter initialization, route registration, and plugin lifecycle.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter

from .adapters import (
    AuditBackend,
    NoOpAuditBackend,
    DenyAllSessionBackend,
    SessionBackend,
    ConsoleSessionBackend,
    StorageBackend,
    ForgeStorageBackend,
    MemoryStorageBackend,
    LicenseBackend,
    FreeTierLicenseBackend,
    PromptGuard,
    NoOpPromptGuard,
    SchedulerBackend,
    NoOpSchedulerBackend,
)

_log = logging.getLogger(__name__)


class WorkflowsPlugin:
    """Main plugin class — initialized at boot, provides routes and lifecycle."""

    def __init__(
        self,
        session_backend: Optional[SessionBackend] = None,
        audit_backend: Optional[AuditBackend] = None,
        storage_backend: Optional[StorageBackend] = None,
        license_backend: Optional[LicenseBackend] = None,
        prompt_guard: Optional[PromptGuard] = None,
        scheduler_backend: Optional[SchedulerBackend] = None,
        forge_paths: Optional[Any] = None,
        spawn_gates: Optional[Any] = None,
        awp_engine: Optional[Any] = None,
    ):
        """Initialize plugin with adapters (DI).

        If adapters not provided, use fallback implementations.
        """
        self.session_backend = session_backend or DenyAllSessionBackend()
        self.audit_backend = audit_backend or NoOpAuditBackend()
        self.storage_backend = storage_backend or MemoryStorageBackend()
        self.license_backend = license_backend or FreeTierLicenseBackend()
        self.prompt_guard = prompt_guard or NoOpPromptGuard()
        self.scheduler_backend = scheduler_backend or NoOpSchedulerBackend()
        self.forge_paths = forge_paths or self._get_default_forge_paths()
        self.spawn_gates = spawn_gates
        self.awp_engine = awp_engine

        self.router = APIRouter(prefix="/workflows", tags=["workflows"])
        self._register_routes()

        _log.info("WorkflowsPlugin initialized ✓")

    def _register_routes(self) -> None:
        """Register all workflow routes via dependency injection."""
        from .routes import create_workflow_routers

        # Wire all 7 route modules with dependency injection
        routers = create_workflow_routers(
            audit_backend=self.audit_backend,
            forge_paths=self.forge_paths,
            license_backend=self.license_backend,
            spawn_gates=self.spawn_gates,
            scheduler=self.scheduler_backend,
            prompt_guard=self.prompt_guard,
            awp_engine=self.awp_engine,
        )

        # Mount all routers on main router
        for router in routers:
            self.router.include_router(router)

        _log.info("Routes registered: %d sub-routers from create_workflow_routers()", len(routers))

    # ─────────────────────────────────────────────────────────────────────────
    # Helper Methods
    # ─────────────────────────────────────────────────────────────────────────

    def _get_default_forge_paths(self) -> Any:
        """Get default forge paths resolver (fallback if not injected)."""
        # In production, this would be injected from the gateway/console.
        # For testing, return a minimal object with required methods.
        class DefaultForgePaths:
            def tenant_workflows_path(self, tenant_id: str) -> str:
                import os
                return os.path.expanduser(f"~/.corvin/tenants/{tenant_id}/forge/workflows")

        return DefaultForgePaths()

    # ─────────────────────────────────────────────────────────────────────────
    # Plugin Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    async def on_load(self) -> None:
        """Called when plugin is loaded."""
        _log.info("WorkflowsPlugin.on_load() ✓")

    async def on_unload(self) -> None:
        """Called when plugin is unloaded."""
        _log.info("WorkflowsPlugin.on_unload() ✓")

    def get_router(self) -> APIRouter:
        """Return FastAPI router for mounting."""
        return self.router

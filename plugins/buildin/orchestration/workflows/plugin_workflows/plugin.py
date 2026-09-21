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

        self.router = APIRouter(prefix="/workflows", tags=["workflows"])
        self._register_routes()

        _log.info("WorkflowsPlugin initialized ✓")

    def _register_routes(self) -> None:
        """Register all workflow routes."""
        # Phase 1: CRUD
        self.router.get("")(self.list_workflows)
        self.router.post("")(self.create_workflow)
        self.router.get("/{wid}")(self.get_workflow)
        self.router.patch("/{wid}")(self.update_workflow)
        self.router.delete("/{wid}")(self.delete_workflow)

        # Phase 1: YAML management
        self.router.get("/{wid}/yaml")(self.get_workflow_yaml)
        self.router.put("/{wid}/yaml")(self.update_workflow_yaml)

        # Phase 1: Runs
        self.router.post("/{wid}/runs")(self.start_run)
        self.router.get("/{wid}/runs")(self.list_runs)
        self.router.get("/{wid}/runs/{rid}")(self.get_run)
        self.router.delete("/{wid}/runs/{rid}")(self.delete_run)

        # Phase 4: Scheduling
        self.router.get("/{wid}/schedule")(self.get_schedule)
        self.router.put("/{wid}/schedule")(self.set_schedule)
        self.router.delete("/{wid}/schedule")(self.remove_schedule)

        # Phase 5: Export/Import
        self.router.get("/{wid}/export.awpkg")(self.export_awpkg)
        self.router.post("/import")(self.import_workflow)

        # Phase 7: Chat
        # self.router.websocket("/{wid}/chat")(self.chat_handler)

        _log.info("Routes registered: %d routes", len(self.router.routes))

    # ─────────────────────────────────────────────────────────────────────────
    # CRUD Handlers (Phase 1)
    # ─────────────────────────────────────────────────────────────────────────

    async def list_workflows(self, tenant_id: Optional[str] = None) -> dict[str, Any]:
        """GET /workflows — List workflows (placeholder)."""
        return {
            "workflows": [],
            "count": 0,
            "message": "Phase 2–3: CRUD implementation pending",
        }

    async def create_workflow(self, title: str, description: str = "") -> dict[str, Any]:
        """POST /workflows — Create workflow (placeholder)."""
        return {"wid": "wf-0001", "message": "Phase 2–3: CRUD implementation pending"}

    async def get_workflow(self, wid: str) -> dict[str, Any]:
        """GET /workflows/{wid} — Get workflow (placeholder)."""
        return {"wid": wid, "message": "Phase 2–3: CRUD implementation pending"}

    async def update_workflow(self, wid: str, title: str = None, description: str = None) -> dict[str, Any]:
        """PATCH /workflows/{wid} — Update workflow (placeholder)."""
        return {"wid": wid, "message": "Phase 2–3: CRUD implementation pending"}

    async def delete_workflow(self, wid: str) -> dict[str, Any]:
        """DELETE /workflows/{wid} — Delete workflow (placeholder)."""
        return {"deleted": True, "message": "Phase 2–3: CRUD implementation pending"}

    # ─────────────────────────────────────────────────────────────────────────
    # YAML Management (Phase 1)
    # ─────────────────────────────────────────────────────────────────────────

    async def get_workflow_yaml(self, wid: str) -> dict[str, Any]:
        """GET /workflows/{wid}/yaml — Get YAML (placeholder)."""
        return {"yaml": "", "message": "Phase 2–3: Implementation pending"}

    async def update_workflow_yaml(self, wid: str, yaml: str) -> dict[str, Any]:
        """PUT /workflows/{wid}/yaml — Update YAML (placeholder)."""
        return {"updated": True, "message": "Phase 2–3: Implementation pending"}

    # ─────────────────────────────────────────────────────────────────────────
    # Runs (Phase 1)
    # ─────────────────────────────────────────────────────────────────────────

    async def start_run(self, wid: str) -> dict[str, Any]:
        """POST /workflows/{wid}/runs — Start run (placeholder)."""
        return {"rid": "run-0001", "message": "Phase 2–3: Implementation pending"}

    async def list_runs(self, wid: str) -> dict[str, Any]:
        """GET /workflows/{wid}/runs — List runs (placeholder)."""
        return {"runs": [], "count": 0, "message": "Phase 2–3: Implementation pending"}

    async def get_run(self, wid: str, rid: str) -> dict[str, Any]:
        """GET /workflows/{wid}/runs/{rid} — Get run (placeholder)."""
        return {"rid": rid, "message": "Phase 2–3: Implementation pending"}

    async def delete_run(self, wid: str, rid: str) -> dict[str, Any]:
        """DELETE /workflows/{wid}/runs/{rid} — Delete run (placeholder)."""
        return {"deleted": True, "message": "Phase 2–3: Implementation pending"}

    # ─────────────────────────────────────────────────────────────────────────
    # Scheduling (Phase 4)
    # ─────────────────────────────────────────────────────────────────────────

    async def get_schedule(self, wid: str) -> dict[str, Any]:
        """GET /workflows/{wid}/schedule — Get schedule (placeholder)."""
        return {"schedule": None, "message": "Phase 4: Implementation pending"}

    async def set_schedule(self, wid: str, cron: str) -> dict[str, Any]:
        """PUT /workflows/{wid}/schedule — Set schedule (placeholder)."""
        return {"schedule": cron, "message": "Phase 4: Implementation pending"}

    async def remove_schedule(self, wid: str) -> dict[str, Any]:
        """DELETE /workflows/{wid}/schedule — Remove schedule (placeholder)."""
        return {"removed": True, "message": "Phase 4: Implementation pending"}

    # ─────────────────────────────────────────────────────────────────────────
    # Export/Import (Phase 5)
    # ─────────────────────────────────────────────────────────────────────────

    async def export_awpkg(self, wid: str) -> dict[str, Any]:
        """GET /workflows/{wid}/export.awpkg — Export (placeholder)."""
        return {"message": "Phase 5: Implementation pending"}

    async def import_workflow(self, file: Any) -> dict[str, Any]:
        """POST /workflows/import — Import (placeholder)."""
        return {"wid": "wf-0002", "message": "Phase 5: Implementation pending"}

    # ─────────────────────────────────────────────────────────────────────────
    # Chat (Phase 7)
    # ─────────────────────────────────────────────────────────────────────────

    # async def chat_handler(self, websocket: WebSocket, wid: str) -> None:
    #     """WS /workflows/{wid}/chat — Design chat (placeholder)."""
    #     await websocket.accept()
    #     await websocket.send_json({"message": "Phase 7: Implementation pending"})
    #     await websocket.close()

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

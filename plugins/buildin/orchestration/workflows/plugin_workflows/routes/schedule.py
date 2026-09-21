"""Cron scheduling routes — registration with corvin-scheduler (Phase 4)."""
import logging
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status as http_status

from .models import SetScheduleRequest
from .helpers import validate_wid, require_workflow, write_atomic, meta_path

_log = logging.getLogger(__name__)

router = APIRouter()


# ── Dependency injection (soft dep) ────────────────────────────────────

class ScheduleAdapter:
    """Adapter for scheduler and audit backends."""

    def __init__(self, audit_backend, forge_paths, scheduler=None):
        self.audit_backend = audit_backend
        self.forge_paths = forge_paths
        self.scheduler = scheduler  # Soft dep — may be None


def get_schedule_adapter() -> ScheduleAdapter:
    """Inject dependencies (override in plugin bootstrap)."""
    raise NotImplementedError("schedule adapter not initialized in plugin bootstrap")


# ── Routes: Schedule ──────────────────────────────────────────────────

@router.get("/workflows/{wid}/schedule")
def get_schedule(
    wid: str,
    tenant_id: str,
    adapter: ScheduleAdapter = Depends(get_schedule_adapter),
) -> dict[str, Any]:
    """Get workflow's cron schedule if set."""
    validate_wid(wid)
    meta = require_workflow(tenant_id, wid, adapter.forge_paths)
    return {"schedule": meta.get("schedule"), "has_schedule": bool(meta.get("has_schedule"))}


@router.put("/workflows/{wid}/schedule")
def set_schedule(
    wid: str,
    body: SetScheduleRequest,
    tenant_id: str,
    sid_fingerprint: str,
    adapter: ScheduleAdapter = Depends(get_schedule_adapter),
) -> dict[str, Any]:
    """Set workflow cron schedule and register with corvin-scheduler.

    Phase 4 integration: schedules run via corvin-scheduler service.
    Soft dependency — if scheduler is unavailable, schedule is stored in meta only.
    """
    validate_wid(wid)
    meta = require_workflow(tenant_id, wid, adapter.forge_paths)

    # Remove old scheduler task if any
    if adapter.scheduler and meta.get("schedule_task_id"):
        try:
            adapter.scheduler.remove_task(meta["schedule_task_id"])
        except Exception:
            pass

    # Update metadata
    meta["schedule"] = {"cron": body.cron, "timezone": body.timezone, "overrun": body.overrun}
    meta["has_schedule"] = True
    meta["updated_at"] = time.time()

    # Register with corvin-scheduler (Phase 4, soft dep)
    scheduler_registered = False
    if adapter.scheduler:
        try:
            task = adapter.scheduler.add_task(
                channel="console",
                chat_id=tenant_id,
                sender="console",
                text=f"Scheduled run: workflow {wid}",
                when=body.cron,
                kind="workflow",
                workflow_name=wid,
                workflow_inputs={},
                tenant_id=tenant_id,
            )
            meta["schedule_task_id"] = task["id"]
            scheduler_registered = True
        except Exception as exc:
            _log.warning("scheduler registration failed: %s", exc)
            meta.pop("schedule_task_id", None)

    # Audit-first: write event before persisting to disk
    adapter.audit_backend.action_performed(
        tenant_id=tenant_id,
        sid_fingerprint=sid_fingerprint,
        action="workflow.scheduled",
        target_kind="workflow",
        target_id=wid,
    )
    write_atomic(meta_path(tenant_id, wid, adapter.forge_paths), meta)
    return {
        "ok": True,
        "schedule": meta["schedule"],
        "scheduler_registered": scheduler_registered,
    }


@router.delete("/workflows/{wid}/schedule")
def delete_schedule(
    wid: str,
    tenant_id: str,
    sid_fingerprint: str,
    adapter: ScheduleAdapter = Depends(get_schedule_adapter),
) -> dict[str, Any]:
    """Remove workflow schedule and unregister from corvin-scheduler."""
    validate_wid(wid)
    meta = require_workflow(tenant_id, wid, adapter.forge_paths)

    # Unregister from corvin-scheduler (Phase 4)
    if adapter.scheduler and meta.get("schedule_task_id"):
        try:
            adapter.scheduler.remove_task(meta["schedule_task_id"])
        except Exception:
            pass

    # Update metadata
    meta.pop("schedule", None)
    meta.pop("schedule_task_id", None)
    meta["has_schedule"] = False
    meta["updated_at"] = time.time()

    # Audit-first: write event before persisting to disk
    adapter.audit_backend.action_performed(
        tenant_id=tenant_id,
        sid_fingerprint=sid_fingerprint,
        action="workflow.unscheduled",
        target_kind="workflow",
        target_id=wid,
    )
    write_atomic(meta_path(tenant_id, wid, adapter.forge_paths), meta)
    return {"ok": True}

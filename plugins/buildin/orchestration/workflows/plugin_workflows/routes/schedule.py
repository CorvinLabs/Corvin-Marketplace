"""Cron scheduling routes — registration with corvin-scheduler (Phase 4).

Implements GET/PUT/DELETE endpoints for workflow scheduling with:
- Full async/await support
- Cron validation (croniter)
- Timezone validation (pytz)
- Audit logging (fire-and-forget)
- Graceful fallback to NoOpSchedulerBackend
"""
import asyncio
import logging
import time
from typing import Annotated, Any, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status as http_status

from .models import SetScheduleRequest, ScheduleResponse, ScheduleUpdateResponse
from .helpers import validate_wid, require_workflow, write_atomic, meta_path

_log = logging.getLogger(__name__)

router = APIRouter()


# ────────────────────────────────────────────────────────────────────────────
# Dependency Injection (Soft Dependencies)
# ────────────────────────────────────────────────────────────────────────────

class ScheduleAdapter:
    """Adapter for scheduler and audit backends."""

    def __init__(self, audit_backend, forge_paths, scheduler_backend=None):
        self.audit_backend = audit_backend
        self.forge_paths = forge_paths
        self.scheduler_backend = scheduler_backend  # Soft dep — may be None


def get_schedule_adapter() -> ScheduleAdapter:
    """Inject dependencies (override in plugin bootstrap)."""
    raise NotImplementedError("schedule adapter not initialized in plugin bootstrap")


# ────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ────────────────────────────────────────────────────────────────────────────

async def _schedule_audit_event(
    adapter: ScheduleAdapter,
    event_type: str,
    tenant_id: str,
    workflow_id: str,
    **kwargs,
) -> None:
    """Log audit event (fire-and-forget, async-safe)."""
    try:
        adapter.audit_backend.log_event(
            event_type,
            tenant_id=tenant_id,
            target_kind="workflow",
            target_id=workflow_id,
            **kwargs,
        )
    except Exception as exc:
        _log.exception("Audit event failed (non-fatal): %s", exc)


def _iso8601_now() -> str:
    """Get current timestamp in ISO8601 format (UTC)."""
    return datetime.utcnow().isoformat() + "Z"


# ────────────────────────────────────────────────────────────────────────────
# Routes: Schedule
# ────────────────────────────────────────────────────────────────────────────


@router.get(
    "/workflows/{workflow_id}/schedule",
    response_model=ScheduleResponse,
    status_code=http_status.HTTP_200_OK,
    summary="Get workflow schedule",
    tags=["Schedule"],
)
async def get_schedule(
    workflow_id: str,
    tenant_id: str,
    adapter: ScheduleAdapter = Depends(get_schedule_adapter),
) -> ScheduleResponse:
    """Get workflow's cron schedule if set.

    Returns:
        ScheduleResponse: Schedule details (cron, timezone, next_run, etc.)

    Raises:
        HTTPException 404: Workflow not found
        HTTPException 404: Workflow has no schedule
    """
    validate_wid(workflow_id)

    try:
        meta = require_workflow(tenant_id, workflow_id, adapter.forge_paths)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Workflow not found: {workflow_id}",
        ) from exc

    schedule_data = meta.get("schedule")
    if not schedule_data or not meta.get("has_schedule"):
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Workflow has no schedule: {workflow_id}",
        )

    return ScheduleResponse(
        workflow_id=workflow_id,
        cron_schedule=schedule_data.get("cron", ""),
        timezone=schedule_data.get("timezone", "UTC"),
        overrun_policy=schedule_data.get("overrun", "skip"),
        next_run=schedule_data.get("next_run"),
        last_run=schedule_data.get("last_run"),
        status="scheduled",
    )


@router.put(
    "/workflows/{workflow_id}/schedule",
    response_model=ScheduleUpdateResponse,
    status_code=http_status.HTTP_200_OK,
    summary="Set or update workflow schedule",
    tags=["Schedule"],
)
async def set_schedule(
    workflow_id: str,
    body: SetScheduleRequest,
    tenant_id: str,
    adapter: ScheduleAdapter = Depends(get_schedule_adapter),
) -> ScheduleUpdateResponse:
    """Set or update workflow cron schedule and register with corvin-scheduler.

    Phase 4 integration: schedules run via corvin-scheduler service.
    Soft dependency — if scheduler is unavailable, schedule is stored in meta only.

    Args:
        workflow_id: Workflow ID
        body: SetScheduleRequest with cron, timezone, overrun_policy
        tenant_id: Tenant ID (from auth)
        adapter: ScheduleAdapter (injected)

    Returns:
        ScheduleUpdateResponse: Confirmation with next_run timestamp

    Raises:
        HTTPException 404: Workflow not found
        HTTPException 400: Invalid request (validation failed in Pydantic)
    """
    validate_wid(workflow_id)

    try:
        meta = require_workflow(tenant_id, workflow_id, adapter.forge_paths)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Workflow not found: {workflow_id}",
        ) from exc

    # Remove old scheduler task if exists (fire-and-forget)
    old_task_id = meta.get("schedule_task_id")
    if adapter.scheduler_backend and old_task_id:
        try:
            await adapter.scheduler_backend.remove_task(old_task_id)
        except Exception as exc:
            _log.warning("Failed to remove old scheduler task: %s", exc)

    # Prepare schedule metadata
    now_ts = time.time()
    schedule_meta = {
        "cron": body.cron_schedule,
        "timezone": body.timezone,
        "overrun": body.overrun_policy,
        "created_at": now_ts if "created_at" not in meta.get("schedule", {}) else meta["schedule"].get("created_at"),
        "updated_at": now_ts,
    }

    # Register with corvin-scheduler (Phase 4, soft dep)
    scheduler_registered = False
    task_id = None
    next_run = None

    if adapter.scheduler_backend:
        try:
            task = await adapter.scheduler_backend.add_task(
                workflow_id=workflow_id,
                cron_schedule=body.cron_schedule,
                timezone=body.timezone,
                overrun_policy=body.overrun_policy,
            )
            task_id = task.task_id
            next_run = task.next_run
            scheduler_registered = True
            schedule_meta["next_run"] = next_run

            _log.info(
                "Scheduler task registered: workflow_id=%s, task_id=%s, next_run=%s",
                workflow_id,
                task_id,
                next_run,
            )
        except Exception as exc:
            _log.warning("Scheduler registration failed (non-fatal): %s", exc)
            meta.pop("schedule_task_id", None)
    else:
        _log.debug("Scheduler backend not available; storing schedule in meta only")

    # Audit-first: log event BEFORE persisting to disk
    await _schedule_audit_event(
        adapter,
        "workflow.schedule.created",
        tenant_id,
        workflow_id,
        cron=body.cron_schedule,
        timezone=body.timezone,
        overrun_policy=body.overrun_policy,
        scheduler_registered=scheduler_registered,
    )

    # Update metadata and persist to disk
    meta["schedule"] = schedule_meta
    if task_id:
        meta["schedule_task_id"] = task_id
    meta["has_schedule"] = True
    meta["updated_at"] = now_ts

    write_atomic(meta_path(tenant_id, workflow_id, adapter.forge_paths), meta)

    return ScheduleUpdateResponse(
        ok=True,
        workflow_id=workflow_id,
        cron_schedule=body.cron_schedule,
        timezone=body.timezone,
        next_run=next_run,
        scheduler_registered=scheduler_registered,
    )


@router.delete(
    "/workflows/{workflow_id}/schedule",
    status_code=http_status.HTTP_200_OK,
    summary="Remove workflow schedule",
    tags=["Schedule"],
)
async def delete_schedule(
    workflow_id: str,
    tenant_id: str,
    adapter: ScheduleAdapter = Depends(get_schedule_adapter),
) -> dict[str, Any]:
    """Remove workflow schedule and unregister from corvin-scheduler.

    Args:
        workflow_id: Workflow ID
        tenant_id: Tenant ID (from auth)
        adapter: ScheduleAdapter (injected)

    Returns:
        dict: Confirmation {"ok": true}

    Raises:
        HTTPException 404: Workflow not found
    """
    validate_wid(workflow_id)

    try:
        meta = require_workflow(tenant_id, workflow_id, adapter.forge_paths)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Workflow not found: {workflow_id}",
        ) from exc

    # Unregister from corvin-scheduler (Phase 4, soft dep)
    task_id = meta.get("schedule_task_id")
    if adapter.scheduler_backend and task_id:
        try:
            await adapter.scheduler_backend.remove_task(task_id)
            _log.info(
                "Scheduler task unregistered: workflow_id=%s, task_id=%s",
                workflow_id,
                task_id,
            )
        except Exception as exc:
            _log.warning("Scheduler unregister failed (non-fatal): %s", exc)

    # Audit-first: log event BEFORE persisting to disk
    await _schedule_audit_event(
        adapter,
        "workflow.schedule.deleted",
        tenant_id,
        workflow_id,
    )

    # Update metadata and persist to disk
    meta.pop("schedule", None)
    meta.pop("schedule_task_id", None)
    meta["has_schedule"] = False
    meta["updated_at"] = time.time()

    write_atomic(meta_path(tenant_id, workflow_id, adapter.forge_paths), meta)

    return {"ok": True}


@router.get(
    "/workflows/schedules",
    response_model=list[ScheduleResponse],
    status_code=http_status.HTTP_200_OK,
    summary="List all scheduled workflows",
    tags=["Schedule"],
)
async def list_schedules(
    tenant_id: str,
    adapter: ScheduleAdapter = Depends(get_schedule_adapter),
) -> list[ScheduleResponse]:
    """List all scheduled workflows for a tenant.

    Args:
        tenant_id: Tenant ID (from auth)
        adapter: ScheduleAdapter (injected)

    Returns:
        list[ScheduleResponse]: List of scheduled workflows
    """
    if not adapter.scheduler_backend:
        return []

    try:
        tasks = await adapter.scheduler_backend.list_tasks(tenant_id)
        return [
            ScheduleResponse(
                workflow_id=task.task_id,
                cron_schedule=task.cron,
                timezone=task.timezone,
                overrun_policy=task.overrun_policy,
                next_run=task.next_run,
                last_run=task.last_run,
                status=task.status,
            )
            for task in tasks
        ]
    except Exception as exc:
        _log.exception("Failed to list schedules: %s", exc)
        return []

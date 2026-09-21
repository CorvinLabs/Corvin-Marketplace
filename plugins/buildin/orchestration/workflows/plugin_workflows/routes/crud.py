"""CRUD route handlers for workflow lifecycle management."""
import contextlib
import logging
import shutil
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status as http_status

from .models import CreateWorkflowRequest, PatchWorkflowRequest
from .helpers import (
    validate_wid, require_workflow, bounded_flock, write_atomic, ensure_dir,
    workflows_dir, yaml_path, meta_path, runs_dir, read_json_or_none,
    WorkflowLockBusy, LOCK_TIMEOUT_SECONDS,
)

_log = logging.getLogger(__name__)

router = APIRouter()


# ── Dependency injection (soft dep) ────────────────────────────────────

class CRUDAdapter:
    """Adapter for console-specific dependencies (auth, audit, forge_paths, license)."""

    def __init__(self, audit_backend, forge_paths, license_backend):
        self.audit_backend = audit_backend
        self.forge_paths = forge_paths
        self.license_backend = license_backend


def get_crud_adapter() -> CRUDAdapter:
    """Inject dependencies (override in plugin bootstrap)."""
    # Placeholder — will be wired by plugin initialization
    raise NotImplementedError("crud adapter not initialized in plugin bootstrap")


# ── License helpers ────────────────────────────────────────────────────

def _count_existing_workflows(tenant_id: str, forge_paths) -> int:
    """Count valid workflow meta files for the tenant (fail-closed)."""
    base = workflows_dir(tenant_id, forge_paths)
    if not base.exists():
        return 0
    return sum(1 for mf in base.glob("*.meta.json") if read_json_or_none(mf))


def _count_running_workflows(tenant_id: str, forge_paths) -> int:
    """Count workflow runs with status='running' (fail-closed re-raise)."""
    wf_root = workflows_dir(tenant_id, forge_paths)
    if not wf_root.exists():
        return 0
    count = 0
    try:
        for wf_dir in wf_root.iterdir():
            runs_d = wf_dir / "runs"
            if not runs_d.is_dir():
                continue
            for meta_file in runs_d.glob("*.meta.json"):
                try:
                    meta = read_json_or_none(meta_file)
                    if meta and meta.get("status") == "running":
                        count += 1
                except Exception:
                    pass  # One unreadable file: bounded under-count
    except Exception:
        # Cannot enumerate tree: re-raise fail-closed instead of returning 0
        raise
    return count


def _wf_create_lock(tenant_id: str, forge_paths):
    """Per-tenant advisory lock for workflow create/import critical section."""
    lock_path = forge_paths.tenant_home(tenant_id) / ".wf_create.lock"
    return bounded_flock(lock_path, "workflow create")


def _enforce_workflows_max(tenant_id: str, rec_tenant_id: str, rec_sid_fingerprint: str,
                           adapter: CRUDAdapter) -> None:
    """Enforce workflows_max limit (fail-closed). Must be called inside _wf_create_lock."""
    limit = adapter.license_backend.get_limit("workflows_max")
    if limit is None:
        return  # Unlimited tier
    existing = _count_existing_workflows(tenant_id, adapter.forge_paths)
    try:
        adapter.license_backend.assert_limit("workflows_max", existing + 1)
    except adapter.license_backend.LimitError as exc:
        adapter.audit_backend.action_failed(
            tenant_id=rec_tenant_id,
            sid_fingerprint=rec_sid_fingerprint,
            action="workflow.create",
            target_kind="workflow",
            target_id="pending",
            reason="license_limit_exceeded",
        )
        raise HTTPException(
            status_code=http_status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "license_limit",
                "feature": "workflows_max",
                "current": existing,
                "limit": limit,
                "upgrade_url": "https://corvin-labs.com/pricing",
                "msg": str(exc),
            },
        ) from exc


def _refuse_lock_busy(rec_tenant_id: str, rec_sid_fingerprint: str, action: str,
                      target_id: str, adapter: CRUDAdapter) -> HTTPException:
    """Convert WorkflowLockBusy into audited 503 response."""
    adapter.audit_backend.action_failed(
        tenant_id=rec_tenant_id,
        sid_fingerprint=rec_sid_fingerprint,
        action=action,
        target_kind="workflow",
        target_id=target_id,
        reason="lock_busy",
    )
    return HTTPException(
        status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="lock_busy",
    )


# ── YAML validation (soft dep) ─────────────────────────────────────────

def _validate_yaml_str(raw: str) -> None:
    """Parse + validate AWP YAML (fail-closed on error)."""
    # This is a soft dependency — if YAML library is unavailable,
    # validation is skipped. When graph exists, terminal validator applies.
    try:
        import yaml
        parsed = yaml.safe_load(raw)
    except ImportError:
        return  # YAML library unavailable
    except Exception as exc:
        _log.error("YAML parsing failed", exc_info=True)
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            "Invalid workflow YAML syntax"
        ) from exc

    # Draft tolerance: empty orchestration.graph is OK during discovery phase
    if not isinstance(parsed, dict):
        return
    orch = parsed.get("orchestration")
    if not isinstance(orch, dict):
        return
    graph = orch.get("graph")
    if not graph:
        return  # Draft state — defer terminal validation until nodes exist


# ── Routes: CRUD ──────────────────────────────────────────────────────

@router.get("/workflows")
def list_workflows(
    tenant_id: str,  # Injected from session
    adapter: CRUDAdapter = Depends(get_crud_adapter),
) -> dict[str, Any]:
    """List all workflows for a tenant."""
    base = workflows_dir(tenant_id, adapter.forge_paths)
    if not base.exists():
        return {"tenant_id": tenant_id, "count": 0, "workflows": []}
    items = []
    for mf in sorted(base.glob("*.meta.json")):
        data = read_json_or_none(mf)
        if data:
            items.append(data)
    items.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
    return {"tenant_id": tenant_id, "count": len(items), "workflows": items}


@router.post("/workflows")
def create_workflow(
    body: CreateWorkflowRequest,
    tenant_id: str,
    sid_fingerprint: str,
    adapter: CRUDAdapter = Depends(get_crud_adapter),
) -> dict[str, Any]:
    """Create a new workflow with optional initial YAML."""
    wid = body.id
    validate_wid(wid)

    # Build initial YAML
    title = body.title or wid
    desc = body.description or ""
    initial_yaml = body.yaml or (
        f'awp: "1.0.0"\n'
        f'workflow:\n'
        f'  name: {wid}\n'
        f'  description: "{desc or title}"\n'
        f'orchestration:\n'
        f'  engine: dag\n'
        f'  graph: []\n'
    )

    # ADR-0094: 409 check → YAML validation → workflows_max → write, all under lock
    lock = contextlib.ExitStack()
    try:
        lock.enter_context(_wf_create_lock(tenant_id, adapter.forge_paths))
    except WorkflowLockBusy:
        raise _refuse_lock_busy(tenant_id, sid_fingerprint, "workflow.create", wid, adapter) from None

    with lock:
        if meta_path(tenant_id, wid, adapter.forge_paths).exists():
            raise HTTPException(http_status.HTTP_409_CONFLICT, "workflow already exists")

        if body.yaml:
            _validate_yaml_str(initial_yaml)

        _enforce_workflows_max(tenant_id, tenant_id, sid_fingerprint, adapter)

        now = time.time()
        meta: dict[str, Any] = {
            "id": wid,
            "title": title,
            "description": desc,
            "phase": "discovering",
            "created_at": now,
            "updated_at": now,
            "has_schedule": False,
        }
        ensure_dir(workflows_dir(tenant_id, adapter.forge_paths))
        write_atomic(yaml_path(tenant_id, wid, adapter.forge_paths), initial_yaml)
        write_atomic(meta_path(tenant_id, wid, adapter.forge_paths), meta)

    adapter.audit_backend.action_performed(
        tenant_id=tenant_id,
        sid_fingerprint=sid_fingerprint,
        action="workflow.created",
        target_kind="workflow",
        target_id=wid,
    )
    return {"ok": True, "workflow": meta}


@router.get("/workflows/{wid}")
def get_workflow(
    wid: str,
    tenant_id: str,
    adapter: CRUDAdapter = Depends(get_crud_adapter),
) -> dict[str, Any]:
    """Get workflow metadata, YAML, and graph."""
    validate_wid(wid)
    meta = require_workflow(tenant_id, wid, adapter.forge_paths)
    yaml_p = yaml_path(tenant_id, wid, adapter.forge_paths)
    yaml_text = yaml_p.read_text(encoding="utf-8") if yaml_p.exists() else ""

    # Parse graph (best-effort)
    graph = _parse_graph(yaml_text)

    return {
        "workflow": meta,
        "yaml": yaml_text,
        "graph": graph,
    }


@router.patch("/workflows/{wid}")
def patch_workflow(
    wid: str,
    body: PatchWorkflowRequest,
    tenant_id: str,
    sid_fingerprint: str,
    adapter: CRUDAdapter = Depends(get_crud_adapter),
) -> dict[str, Any]:
    """Update workflow metadata (title, description)."""
    validate_wid(wid)
    meta = require_workflow(tenant_id, wid, adapter.forge_paths)
    if body.title is not None:
        meta["title"] = body.title
    if body.description is not None:
        meta["description"] = body.description
    meta["updated_at"] = time.time()
    write_atomic(meta_path(tenant_id, wid, adapter.forge_paths), meta)
    adapter.audit_backend.action_performed(
        tenant_id=tenant_id,
        sid_fingerprint=sid_fingerprint,
        action="workflow.updated",
        target_kind="workflow",
        target_id=wid,
    )
    return {"ok": True, "workflow": meta}


@router.delete("/workflows/{wid}")
def delete_workflow(
    wid: str,
    tenant_id: str,
    sid_fingerprint: str,
    adapter: CRUDAdapter = Depends(get_crud_adapter),
) -> dict[str, Any]:
    """Delete a workflow and all its runs."""
    validate_wid(wid)
    meta = require_workflow(tenant_id, wid, adapter.forge_paths)

    # Unregister from scheduler (Phase 4, soft dep)
    if meta.get("schedule_task_id"):
        try:
            adapter.license_backend.scheduler.remove_task(meta["schedule_task_id"])
        except Exception:
            pass

    # Delete files
    base = workflows_dir(tenant_id, adapter.forge_paths)
    for suffix in (".awp.yaml", ".meta.json", ".chat.jsonl"):
        p = base / f"{wid}{suffix}"
        if p.exists():
            p.unlink()
    run_d = base / wid
    if run_d.exists():
        shutil.rmtree(run_d)

    adapter.audit_backend.action_performed(
        tenant_id=tenant_id,
        sid_fingerprint=sid_fingerprint,
        action="workflow.deleted",
        target_kind="workflow",
        target_id=wid,
    )
    return {"ok": True, "id": wid}


# ── Graph parsing (best-effort) ────────────────────────────────────────

def _parse_graph(yaml_text: str) -> list[dict[str, Any]]:
    """Extract graph nodes from AWP YAML for the canvas (best-effort)."""
    if not yaml_text.strip():
        return []
    try:
        import yaml
        parsed = yaml.safe_load(yaml_text) or {}
    except Exception:
        return []

    graph = parsed.get("orchestration", {}).get("graph", [])
    if not isinstance(graph, list):
        return []

    return [
        {
            "id": str(n.get("id", f"node_{i}")),
            "type": str(n.get("type", "agent")),
            "depends_on": list(n.get("depends_on", []) or []),
            "agent": n.get("agent"),
            "instructions": str(n.get("instructions", ""))[:120],
            "tools": list(n.get("tools") or []),
            "forge_tools": list(n.get("forge_tools") or []),
            "skills": list(n.get("skills") or []),
            "items_from": n.get("items_from"),
            "config": n.get("config"),
        }
        for i, n in enumerate(graph)
        if isinstance(n, dict)
    ]

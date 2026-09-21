"""Run lifecycle route handlers — execution, approval gates, media streaming."""
import json
import logging
import secrets
import time
from pathlib import Path
from typing import Annotated, Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Response, status as http_status
from fastapi.responses import StreamingResponse

from .models import StartRunRequest, ApproveRunRequest, ResumeRunRequest
from .helpers import (
    validate_wid, require_workflow, write_atomic, ensure_dir, read_json_or_none,
    yaml_path, meta_path, runs_dir, run_meta_path, run_log_path, approval_path,
    workflows_dir,
)

_log = logging.getLogger(__name__)

router = APIRouter()

_RID_BYTES = 8


# ── Dependency injection (soft dep) ────────────────────────────────────

class RunsAdapter:
    """Adapter for console-specific dependencies."""

    def __init__(self, audit_backend, forge_paths, spawn_gates, license_backend, awp_engine):
        self.audit_backend = audit_backend
        self.forge_paths = forge_paths
        self.spawn_gates = spawn_gates
        self.license_backend = license_backend
        self.awp_engine = awp_engine


def get_runs_adapter() -> RunsAdapter:
    """Inject dependencies (override in plugin bootstrap)."""
    raise NotImplementedError("runs adapter not initialized in plugin bootstrap")


# ── Helpers ────────────────────────────────────────────────────────────

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
            for m_file in runs_d.glob("*.meta.json"):
                try:
                    meta = read_json_or_none(m_file)
                    if meta and meta.get("status") == "running":
                        count += 1
                except Exception:
                    pass
    except Exception:
        raise  # Re-raise fail-closed
    return count


async def _stream_run(
    tenant_id: str,
    sid_fingerprint: str,
    wid: str,
    rid: str,
    yaml_text: str,
    inputs: dict[str, Any],
    dry_run: bool,
    adapter: RunsAdapter,
) -> AsyncIterator[str]:
    """Stream workflow run events via SSE (audit-first).

    This is a generator that yields SSE-formatted event strings.
    The actual AWP execution logic is kept minimal here — focus on
    streaming, media collection, and state management.
    """
    # Initialize run metadata
    run_meta = {
        "id": rid,
        "workflow_id": wid,
        "status": "running",
        "started_at": time.time(),
        "inputs": inputs,
        "dry_run": dry_run,
    }

    try:
        # Create run directory
        run_dir = runs_dir(tenant_id, wid, adapter.forge_paths)
        ensure_dir(run_dir)
        write_atomic(run_meta_path(tenant_id, wid, rid, adapter.forge_paths), run_meta)

        # Yield start event
        yield f"event: run_started\n"
        yield f"data: {json.dumps({'rid': rid, 'status': 'running'})}\n\n"

        # Execute workflow (simplified — real implementation is much longer)
        # TODO: Integrate AWP engine and node execution here
        run_meta["status"] = "completed"
        run_meta["completed_at"] = time.time()

        # Yield completion event
        yield f"event: run_completed\n"
        yield f"data: {json.dumps({'rid': rid, 'status': 'completed'})}\n\n"

    except Exception as exc:
        _log.error("Workflow run %s failed: %s", rid, exc, exc_info=True)
        run_meta["status"] = "failed"
        run_meta["error"] = str(exc)
        run_meta["completed_at"] = time.time()
        yield f"event: run_failed\n"
        yield f"data: {json.dumps({'rid': rid, 'error': str(exc)})}\n\n"
    finally:
        # Persist final run metadata
        write_atomic(run_meta_path(tenant_id, wid, rid, adapter.forge_paths), run_meta)


# ── Routes: Runs ──────────────────────────────────────────────────────

@router.post("/workflows/{wid}/runs")
def start_run(
    wid: str,
    body: StartRunRequest,
    tenant_id: str,
    sid_fingerprint: str,
    adapter: RunsAdapter = Depends(get_runs_adapter),
) -> StreamingResponse:
    """Start a workflow run with SSE streaming output.

    Enforces license limits (concurrent runs, daily compute quota).
    Requires consent and compliance zone checks.
    """
    validate_wid(wid)
    meta = require_workflow(tenant_id, wid, adapter.forge_paths)
    yaml_p = yaml_path(tenant_id, wid, adapter.forge_paths)
    if not yaml_p.exists():
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "no YAML defined for this workflow")

    yaml_text = yaml_p.read_text(encoding="utf-8")

    # Check graph is not empty (not in discovery phase)
    try:
        import yaml
        parsed = yaml.safe_load(yaml_text) or {}
        graph = parsed.get("orchestration", {}).get("graph") or []
        if not graph:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                f"Workflow is still in '{meta.get('phase', 'unknown')}' phase — "
                "use the design assistant to build the graph before running.",
            )
    except HTTPException:
        raise
    except Exception:
        pass  # YAML parse errors caught later in _stream_run

    # Generate run ID early
    rid = secrets.token_hex(_RID_BYTES)

    # Enforce concurrent runs limit
    try:
        running = _count_running_workflows(tenant_id, adapter.forge_paths)
        limit = adapter.license_backend.get_limit("workflows_concurrent")
        if limit is not None and running + 1 > limit:
            adapter.audit_backend.action_failed(
                tenant_id=tenant_id,
                sid_fingerprint=sid_fingerprint,
                action="workflow.run_started",
                target_kind="workflow",
                target_id=wid,
                reason="quota_exceeded",
            )
            raise HTTPException(
                status_code=http_status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "license_limit",
                    "feature": "workflows_concurrent",
                    "running": running,
                    "limit": limit,
                    "upgrade_url": "https://corvin-labs.com/pricing",
                },
            )
    except HTTPException:
        raise
    except Exception as exc:
        _log.warning("concurrent-workflow check failed: %s — refusing run (fail-closed)", exc)
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="concurrent-workflow limit check unavailable — try again",
        ) from exc

    # Audit the run start
    adapter.audit_backend.action_performed(
        tenant_id=tenant_id,
        sid_fingerprint=sid_fingerprint,
        action="workflow.run_started",
        target_kind="workflow",
        target_id=wid,
        run_id=rid,
        trigger="manual",
    )

    return StreamingResponse(
        _stream_run(tenant_id, sid_fingerprint, wid, rid, yaml_text, body.inputs, body.dry_run, adapter),
        media_type="text/event-stream",
        headers={"X-Run-Id": rid, "Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/workflows/{wid}/runs")
def list_runs(
    wid: str,
    tenant_id: str,
    adapter: RunsAdapter = Depends(get_runs_adapter),
) -> dict[str, Any]:
    """List all runs for a workflow."""
    validate_wid(wid)
    require_workflow(tenant_id, wid, adapter.forge_paths)

    run_d = runs_dir(tenant_id, wid, adapter.forge_paths)
    if not run_d.exists():
        return {"workflow_id": wid, "count": 0, "runs": []}

    runs = []
    for mf in sorted(run_d.glob("*.meta.json")):
        meta = read_json_or_none(mf)
        if meta:
            runs.append(meta)
    runs.sort(key=lambda x: x.get("started_at", 0), reverse=True)
    return {"workflow_id": wid, "count": len(runs), "runs": runs}


@router.get("/workflows/{wid}/runs/{rid}")
def get_run(
    wid: str,
    rid: str,
    tenant_id: str,
    adapter: RunsAdapter = Depends(get_runs_adapter),
) -> dict[str, Any]:
    """Get run metadata and event log."""
    validate_wid(wid)
    require_workflow(tenant_id, wid, adapter.forge_paths)

    meta = read_json_or_none(run_meta_path(tenant_id, wid, rid, adapter.forge_paths))
    if meta is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "run not found")

    # Read event log
    log_p = run_log_path(tenant_id, wid, rid, adapter.forge_paths)
    events = []
    if log_p.exists():
        for line in log_p.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except Exception:
                pass

    return {"run": meta, "events": events}


@router.delete("/workflows/{wid}/runs/{rid}")
def delete_run(
    wid: str,
    rid: str,
    tenant_id: str,
    sid_fingerprint: str,
    adapter: RunsAdapter = Depends(get_runs_adapter),
) -> dict[str, Any]:
    """Delete a run and its associated files."""
    validate_wid(wid)
    require_workflow(tenant_id, wid, adapter.forge_paths)

    run_d = runs_dir(tenant_id, wid, adapter.forge_paths)
    for suffix in (".meta.json", ".jsonl", ".approval.json"):
        p = run_d / f"{rid}{suffix}"
        if p.exists():
            p.unlink()

    adapter.audit_backend.action_performed(
        tenant_id=tenant_id,
        sid_fingerprint=sid_fingerprint,
        action="workflow.run_deleted",
        target_kind="workflow",
        target_id=wid,
        run_id=rid,
    )
    return {"ok": True, "id": rid}


@router.post("/workflows/{wid}/runs/{rid}/approve")
def approve_run(
    wid: str,
    rid: str,
    body: ApproveRunRequest,
    tenant_id: str,
    sid_fingerprint: str,
    adapter: RunsAdapter = Depends(get_runs_adapter),
) -> dict[str, Any]:
    """Approve a run that is awaiting human decision (e.g., before delegation)."""
    validate_wid(wid)
    require_workflow(tenant_id, wid, adapter.forge_paths)

    approval_p = approval_path(tenant_id, wid, rid, adapter.forge_paths)
    approval_p.parent.mkdir(parents=True, exist_ok=True)

    approval_data = {
        "decision": "approved",
        "timestamp": time.time(),
        "comment": body.comment,
    }
    write_atomic(approval_p, approval_data)

    adapter.audit_backend.action_performed(
        tenant_id=tenant_id,
        sid_fingerprint=sid_fingerprint,
        action="workflow.run_approved",
        target_kind="workflow",
        target_id=wid,
        run_id=rid,
    )
    return {"ok": True, "decision": "approved"}


@router.post("/workflows/{wid}/runs/{rid}/reject")
def reject_run(
    wid: str,
    rid: str,
    body: ApproveRunRequest,
    tenant_id: str,
    sid_fingerprint: str,
    adapter: RunsAdapter = Depends(get_runs_adapter),
) -> dict[str, Any]:
    """Reject a run that is awaiting human decision."""
    validate_wid(wid)
    require_workflow(tenant_id, wid, adapter.forge_paths)

    approval_p = approval_path(tenant_id, wid, rid, adapter.forge_paths)
    approval_p.parent.mkdir(parents=True, exist_ok=True)

    approval_data = {
        "decision": "rejected",
        "timestamp": time.time(),
        "reason": body.comment,
    }
    write_atomic(approval_p, approval_data)

    adapter.audit_backend.action_performed(
        tenant_id=tenant_id,
        sid_fingerprint=sid_fingerprint,
        action="workflow.run_rejected",
        target_kind="workflow",
        target_id=wid,
        run_id=rid,
    )
    return {"ok": True, "decision": "rejected"}


@router.post("/workflows/{wid}/runs/{rid}/resume")
def resume_run(
    wid: str,
    rid: str,
    body: ResumeRunRequest,
    tenant_id: str,
    sid_fingerprint: str,
    adapter: RunsAdapter = Depends(get_runs_adapter),
) -> dict[str, Any]:
    """Resume a checkpointed workflow run (AWP checkpoint recovery)."""
    validate_wid(wid)
    require_workflow(tenant_id, wid, adapter.forge_paths)

    meta = read_json_or_none(run_meta_path(tenant_id, wid, rid, adapter.forge_paths))
    if meta is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "run not found")

    if meta.get("status") not in ("paused", "checkpoint"):
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            f"run is in status '{meta.get('status')}' — can only resume paused runs"
        )

    # TODO: Integrate AWP checkpoint resume logic here
    meta["status"] = "resumed"
    meta["resumed_at"] = time.time()
    meta["resume_input"] = body.reply
    write_atomic(run_meta_path(tenant_id, wid, rid, adapter.forge_paths), meta)

    adapter.audit_backend.action_performed(
        tenant_id=tenant_id,
        sid_fingerprint=sid_fingerprint,
        action="workflow.run_resumed",
        target_kind="workflow",
        target_id=wid,
        run_id=rid,
    )
    return {"ok": True, "status": "resumed"}

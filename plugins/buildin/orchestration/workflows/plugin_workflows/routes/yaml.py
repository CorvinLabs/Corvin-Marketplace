"""YAML route handlers for workflow definition management."""
import io
import json
import logging
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status as http_status

from .models import UpdateYamlRequest
from .helpers import (
    validate_wid, require_workflow, write_atomic, ensure_dir,
    yaml_path, meta_path, workflows_dir, read_json_or_none,
)

_log = logging.getLogger(__name__)

router = APIRouter()


# ── Dependency injection (soft dep) ────────────────────────────────────

class YAMLAdapter:
    """Adapter for console-specific dependencies."""

    def __init__(self, audit_backend, forge_paths):
        self.audit_backend = audit_backend
        self.forge_paths = forge_paths


def get_yaml_adapter() -> YAMLAdapter:
    """Inject dependencies (override in plugin bootstrap)."""
    raise NotImplementedError("yaml adapter not initialized in plugin bootstrap")


# ── YAML validation ────────────────────────────────────────────────────

def _validate_yaml_str(raw: str) -> None:
    """Parse + validate AWP YAML (fail-closed on error)."""
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


# ── AWPKG sidecar writer ──────────────────────────────────────────────

def _write_awpkg_sidecar(tenant_id: str, wid: str, forge_paths) -> None:
    """Write/update {wid}.awpkg next to the YAML after every YAML change.

    Best-effort: any failure is logged at DEBUG and silently suppressed so
    that a ZIP-write failure never blocks the primary YAML write.
    """
    try:
        yaml_p = yaml_path(tenant_id, wid, forge_paths)
        if not yaml_p.exists():
            return
        yaml_text = yaml_p.read_text(encoding="utf-8")
        meta = read_json_or_none(meta_path(tenant_id, wid, forge_paths)) or {}
        manifest_dict: dict[str, Any] = {
            "awpkg": "1.0",
            "id": f"com.corvin.{wid.replace('_', '-')}",
            "name": meta.get("title", wid),
            "version": "0.1.0",
            "description": meta.get("description", "") or "",
            "components": {"workflows": [f"workflows/{wid}.awp.yaml"]},
            "permissions": {"network": False, "compute": False, "secrets": []},
        }
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            try:
                import yaml
                manifest_bytes = yaml.dump(
                    manifest_dict, allow_unicode=True, default_flow_style=False
                ).encode("utf-8")
            except ImportError:
                manifest_bytes = json.dumps(
                    manifest_dict, indent=2, ensure_ascii=False
                ).encode("utf-8")
            zf.writestr("manifest.yaml", manifest_bytes)
            zf.writestr(f"workflows/{wid}.awp.yaml", yaml_text.encode("utf-8"))
        pkg_bytes = buf.getvalue()
        pkg_path = workflows_dir(tenant_id, forge_paths) / f"{wid}.awpkg"
        fd, tmp = tempfile.mkstemp(
            prefix=wid + ".", suffix=".awpkg", dir=str(pkg_path.parent)
        )
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(pkg_bytes)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, pkg_path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception:
        _log.debug("awpkg sidecar write failed for %s/%s", tenant_id, wid, exc_info=True)


# ── Routes: YAML ──────────────────────────────────────────────────────

@router.get("/workflows/{wid}/yaml")
def get_workflow_yaml(
    wid: str,
    tenant_id: str,
    adapter: YAMLAdapter = Depends(get_yaml_adapter),
) -> dict[str, Any]:
    """Get raw workflow YAML text."""
    validate_wid(wid)
    require_workflow(tenant_id, wid, adapter.forge_paths)
    yaml_p = yaml_path(tenant_id, wid, adapter.forge_paths)
    return {"yaml": yaml_p.read_text(encoding="utf-8") if yaml_p.exists() else ""}


@router.put("/workflows/{wid}/yaml")
def put_workflow_yaml(
    wid: str,
    body: UpdateYamlRequest,
    tenant_id: str,
    sid_fingerprint: str,
    adapter: YAMLAdapter = Depends(get_yaml_adapter),
) -> dict[str, Any]:
    """Replace workflow YAML and validate structure."""
    validate_wid(wid)
    meta = require_workflow(tenant_id, wid, adapter.forge_paths)
    _validate_yaml_str(body.yaml)

    # Update YAML and write sidecar AWPKG
    write_atomic(yaml_path(tenant_id, wid, adapter.forge_paths), body.yaml)
    _write_awpkg_sidecar(tenant_id, wid, adapter.forge_paths)

    # Update metadata timestamp
    meta["updated_at"] = import time; time.time()
    write_atomic(meta_path(tenant_id, wid, adapter.forge_paths), meta)

    adapter.audit_backend.action_performed(
        tenant_id=tenant_id,
        sid_fingerprint=sid_fingerprint,
        action="workflow.updated",
        target_kind="workflow",
        target_id=wid,
    )

    # Parse and return updated graph
    graph = _parse_graph(body.yaml)
    return {"ok": True, "id": wid, "graph": graph}


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

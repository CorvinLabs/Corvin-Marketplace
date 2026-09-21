"""AWPKG/YAML import route — workflow discovery and tool registration (Phase 5)."""
import contextlib
import json
import logging
import tempfile
import zipfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status as http_status

from .helpers import (
    validate_wid, bounded_flock, write_atomic, ensure_dir,
    workflows_dir, yaml_path, meta_path, read_json_or_none, WorkflowLockBusy,
)

_log = logging.getLogger(__name__)

router = APIRouter()


# ── Dependency injection (soft dep) ────────────────────────────────────

class ImportAdapter:
    """Adapter for import dependencies."""

    def __init__(self, audit_backend, forge_paths, license_backend):
        self.audit_backend = audit_backend
        self.forge_paths = forge_paths
        self.license_backend = license_backend


def get_import_adapter() -> ImportAdapter:
    """Inject dependencies (override in plugin bootstrap)."""
    raise NotImplementedError("import adapter not initialized in plugin bootstrap")


# ── AWPKG extraction helpers ───────────────────────────────────────────

def _register_tools_from_zip(zf: zipfile.ZipFile, tenant_id: str, forge_paths) -> list[str]:
    """Write tools from imported AWPKG into Forge registry.

    Writes .py implementations to <tenant>/global/forge/tools/<name>.py
    and upserts registry.json entries.
    """
    registered = []
    home = forge_paths.tenant_home(tenant_id)
    tools_dir = home / "global" / "forge" / "tools"
    registry_file = home / "global" / "forge" / "registry.json"

    ensure_dir(tools_dir)
    registry = read_json_or_none(registry_file) or {}

    for item in zf.filelist:
        if not item.filename.startswith("tools/") or not item.filename.endswith(".json"):
            continue
        try:
            data = zf.read(item).decode("utf-8")
            bundle = json.loads(data)
            tool_name = bundle.get("name", Path(item.filename).stem)
            py_file = tools_dir / f"{tool_name}.py"
            py_file.write_text(bundle.get("code", ""), encoding="utf-8")
            registry[tool_name] = {
                "name": tool_name,
                "description": bundle.get("description", ""),
                "input_schema": bundle.get("input_schema", {}),
                "impl_path": str(py_file),
            }
            registered.append(tool_name)
        except Exception as exc:
            _log.warning("tool registration failed for %s: %s", item.filename, exc)

    if registered:
        write_atomic(registry_file, registry)
    return registered


def _extract_workflow_yaml_from_zip(zf: zipfile.ZipFile) -> str | None:
    """Extract the main workflow YAML from AWPKG (best-effort)."""
    for item in zf.filelist:
        if item.filename.endswith(".awp.yaml"):
            try:
                return zf.read(item).decode("utf-8")
            except Exception:
                pass
    return None


# ── Routes: Import ────────────────────────────────────────────────────

@router.post("/workflows/import")
def import_workflow(
    file: UploadFile = File(...),
    tenant_id: str = "",
    sid_fingerprint: str = "",
    adapter: ImportAdapter = Depends(get_import_adapter),
) -> dict[str, Any]:
    """Import workflow from uploaded AWPKG or YAML file.

    Phase 5 feature: discovers workflows from packages, registers tools,
    creates workflow entries.
    """
    if not file.filename:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "no file provided")

    # Determine file type
    is_awpkg = file.filename.lower().endswith(".awpkg")
    is_yaml = file.filename.lower().endswith((".yaml", ".yml"))

    if not is_awpkg and not is_yaml:
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            "file must be .awpkg (ZIP) or .yaml"
        )

    # Use per-tenant lock for import (same as create_workflow)
    lock = contextlib.ExitStack()
    try:
        lock_path = adapter.forge_paths.tenant_home(tenant_id) / ".wf_create.lock"
        lock.enter_context(bounded_flock(lock_path, "workflow import"))
    except WorkflowLockBusy:
        adapter.audit_backend.action_failed(
            tenant_id=tenant_id,
            sid_fingerprint=sid_fingerprint,
            action="workflow.import",
            target_kind="workflow",
            target_id="pending",
            reason="lock_busy",
        )
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="lock_busy",
        ) from None

    with lock:
        if is_yaml:
            # Direct YAML import
            yaml_text = file.file.read().decode("utf-8")
            wid = Path(file.filename).stem
            validate_wid(wid)

            if meta_path(tenant_id, wid, adapter.forge_paths).exists():
                raise HTTPException(http_status.HTTP_409_CONFLICT, "workflow already exists")

            import time
            now = time.time()
            meta: dict[str, Any] = {
                "id": wid,
                "title": wid,
                "description": "Imported workflow",
                "phase": "ready",
                "created_at": now,
                "updated_at": now,
                "has_schedule": False,
            }
            ensure_dir(workflows_dir(tenant_id, adapter.forge_paths))
            write_atomic(yaml_path(tenant_id, wid, adapter.forge_paths), yaml_text)
            write_atomic(meta_path(tenant_id, wid, adapter.forge_paths), meta)

            adapter.audit_backend.action_performed(
                tenant_id=tenant_id,
                sid_fingerprint=sid_fingerprint,
                action="workflow.imported",
                target_kind="workflow",
                target_id=wid,
            )
            return {"ok": True, "workflow": meta, "tools_registered": []}

        else:  # is_awpkg
            # AWPKG ZIP import
            fd, tmp_path = tempfile.mkstemp(suffix=".awpkg")
            try:
                with open(fd, "wb") as f:
                    f.write(file.file.read())

                with zipfile.ZipFile(tmp_path, "r") as zf:
                    yaml_text = _extract_workflow_yaml_from_zip(zf)
                    if not yaml_text:
                        raise HTTPException(
                            http_status.HTTP_400_BAD_REQUEST,
                            "no .awp.yaml found in AWPKG"
                        )

                    # Generate workflow ID from manifest or filename
                    wid = Path(file.filename).stem
                    validate_wid(wid)

                    if meta_path(tenant_id, wid, adapter.forge_paths).exists():
                        raise HTTPException(http_status.HTTP_409_CONFLICT, "workflow already exists")

                    # Register tools from AWPKG
                    tools_registered = _register_tools_from_zip(zf, tenant_id, adapter.forge_paths)

                    # Create workflow entry
                    import time
                    now = time.time()
                    meta: dict[str, Any] = {
                        "id": wid,
                        "title": wid,
                        "description": "Imported from AWPKG",
                        "phase": "ready",
                        "created_at": now,
                        "updated_at": now,
                        "has_schedule": False,
                    }
                    ensure_dir(workflows_dir(tenant_id, adapter.forge_paths))
                    write_atomic(yaml_path(tenant_id, wid, adapter.forge_paths), yaml_text)
                    write_atomic(meta_path(tenant_id, wid, adapter.forge_paths), meta)

                    adapter.audit_backend.action_performed(
                        tenant_id=tenant_id,
                        sid_fingerprint=sid_fingerprint,
                        action="workflow.imported",
                        target_kind="workflow",
                        target_id=wid,
                    )
                    return {
                        "ok": True,
                        "workflow": meta,
                        "tools_registered": tools_registered,
                    }
            finally:
                try:
                    Path(tmp_path).unlink()
                except Exception:
                    pass

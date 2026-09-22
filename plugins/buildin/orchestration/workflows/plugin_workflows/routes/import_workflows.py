"""AWPKG/YAML import route — workflow discovery and tool registration (Phase 5)."""
import contextlib
import hashlib
import json
import logging
import tempfile
import zipfile
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status as http_status

from .helpers import (
    validate_wid, bounded_flock, write_atomic, ensure_dir,
    workflows_dir, yaml_path, meta_path, read_json_or_none, WorkflowLockBusy,
)

_log = logging.getLogger(__name__)

router = APIRouter()

# Constants
_MAX_AWPKG_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit
_CONFLICT_MODES = {"overwrite", "rename", "skip"}


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


def _extract_workflow_yaml_from_zip(zf: zipfile.ZipFile) -> tuple[str | None, str | None]:
    """Extract the main workflow YAML and checksum from AWPKG (best-effort).

    Returns:
        (yaml_text, checksum) — checksum is None if not present in AWPKG
    """
    yaml_text = None
    checksum = None

    for item in zf.filelist:
        if item.filename.endswith(".awp.yaml"):
            try:
                yaml_text = zf.read(item).decode("utf-8")
            except Exception:
                pass
        elif item.filename == "checksum.txt":
            try:
                checksum = zf.read(item).decode("utf-8").strip()
            except Exception:
                pass

    return yaml_text, checksum


def _verify_workflow_checksum(yaml_text: str, stored_checksum: str | None) -> bool:
    """Verify workflow YAML checksum if present.

    Returns:
        True if checksum matches or not present; False if mismatch.
    """
    if not stored_checksum:
        return True  # No checksum to verify

    computed_checksum = hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()
    return computed_checksum == stored_checksum


async def _generate_unique_wid(base_wid: str, forge_paths, tenant_id: str) -> str:
    """Generate unique workflow ID by appending counter if needed."""
    counter = 1
    candidate = base_wid
    while meta_path(tenant_id, candidate, forge_paths).exists():
        candidate = f"{base_wid}_{counter}"
        counter += 1
    return candidate


# ── Routes: Import ────────────────────────────────────────────────────

@router.post("/workflows/import")
def import_workflow(
    file: UploadFile = File(...),
    tenant_id: str = "",
    sid_fingerprint: str = "",
    conflict_mode: str = Query("overwrite", description="Conflict resolution: overwrite|rename|skip"),
    adapter: ImportAdapter = Depends(get_import_adapter),
) -> dict[str, Any]:
    """Import workflow from uploaded AWPKG or YAML file.

    Phase 5 feature: discovers workflows from packages, registers tools,
    creates workflow entries.

    Args:
        file: Uploaded .awpkg (ZIP) or .yaml file
        conflict_mode: How to handle existing workflows (overwrite|rename|skip)

    Audit events:
      - workflow.import.started: Before import begins
      - workflow.import.completed: After successful import
      - workflow.import.failed: On error (invalid format, size exceeded, etc.)
      - workflow.import.conflict_<mode>: On conflict resolution
    """
    if not file.filename:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "no file provided")

    if conflict_mode not in _CONFLICT_MODES:
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            f"invalid conflict_mode: {conflict_mode} (must be one of {_CONFLICT_MODES})"
        )

    adapter.audit_backend.action_started(
        tenant_id=tenant_id,
        action="workflow.import",
        target_kind="workflow",
        target_id="pending",
    )

    # Determine file type
    is_awpkg = file.filename.lower().endswith(".awpkg")
    is_yaml = file.filename.lower().endswith((".yaml", ".yml"))

    if not is_awpkg and not is_yaml:
        adapter.audit_backend.action_failed(
            tenant_id=tenant_id,
            action="workflow.import.failed",
            target_kind="workflow",
            target_id="pending",
            reason="invalid_file_type",
        )
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
            action="workflow.import.failed",
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
            try:
                yaml_bytes = file.file.read()

                # Check size limit
                if len(yaml_bytes) > _MAX_AWPKG_SIZE_BYTES:
                    raise HTTPException(
                        http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        f"File size exceeds limit ({len(yaml_bytes)} > {_MAX_AWPKG_SIZE_BYTES} bytes)"
                    )

                yaml_text = yaml_bytes.decode("utf-8")
                wid = Path(file.filename).stem
                validate_wid(wid)

                # Handle existing workflow
                existing = meta_path(tenant_id, wid, adapter.forge_paths).exists()
                if existing:
                    if conflict_mode == "skip":
                        adapter.audit_backend.action_performed(
                            tenant_id=tenant_id,
                            action=f"workflow.import.conflict_{conflict_mode}",
                            target_kind="workflow",
                            target_id=wid,
                        )
                        return {"ok": True, "workflow_id": wid, "action": "skipped"}
                    elif conflict_mode == "rename":
                        import asyncio
                        wid = asyncio.run(_generate_unique_wid(wid, adapter.forge_paths, tenant_id))
                    elif conflict_mode == "overwrite":
                        # Will overwrite below
                        pass

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
                    action="workflow.import.completed",
                    target_kind="workflow",
                    target_id=wid,
                    details={"conflict_mode": conflict_mode, "size_bytes": len(yaml_bytes)}
                )
                _log.info(f"Imported YAML workflow {wid} (conflict_mode={conflict_mode})")
                return {"ok": True, "workflow_id": wid, "tools_registered": []}

            except HTTPException:
                raise
            except Exception as e:
                adapter.audit_backend.action_failed(
                    tenant_id=tenant_id,
                    action="workflow.import.failed",
                    target_kind="workflow",
                    target_id="pending",
                    reason=str(e),
                )
                _log.error(f"YAML import failed: {e}")
                raise HTTPException(http_status.HTTP_400_BAD_REQUEST, f"YAML import failed: {e}")

        else:  # is_awpkg
            # AWPKG ZIP import
            fd, tmp_path = tempfile.mkstemp(suffix=".awpkg")
            try:
                file_bytes = file.file.read()

                # Check size limit
                if len(file_bytes) > _MAX_AWPKG_SIZE_BYTES:
                    adapter.audit_backend.action_failed(
                        tenant_id=tenant_id,
                        action="workflow.import.failed",
                        target_kind="workflow",
                        target_id="pending",
                        reason="file_too_large",
                    )
                    raise HTTPException(
                        http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        f"AWPKG size exceeds limit ({len(file_bytes)} > {_MAX_AWPKG_SIZE_BYTES} bytes)"
                    )

                with open(fd, "wb") as f:
                    f.write(file_bytes)

                # Validate ZIP format
                try:
                    with zipfile.ZipFile(tmp_path, "r") as zf:
                        # Test ZIP integrity
                        bad_file = zf.testzip()
                        if bad_file:
                            raise ValueError(f"Corrupted ZIP file: {bad_file}")

                        yaml_text, stored_checksum = _extract_workflow_yaml_from_zip(zf)
                        if not yaml_text:
                            raise HTTPException(
                                http_status.HTTP_400_BAD_REQUEST,
                                "no .awp.yaml found in AWPKG"
                            )

                        # Verify checksum
                        if not _verify_workflow_checksum(yaml_text, stored_checksum):
                            adapter.audit_backend.action_failed(
                                tenant_id=tenant_id,
                                action="workflow.import.failed",
                                target_kind="workflow",
                                target_id="pending",
                                reason="checksum_mismatch",
                            )
                            raise HTTPException(
                                http_status.HTTP_400_BAD_REQUEST,
                                "AWPKG checksum verification failed (file corrupted)"
                            )

                        # Generate workflow ID from manifest or filename
                        wid = Path(file.filename).stem
                        validate_wid(wid)

                        # Handle existing workflow
                        existing = meta_path(tenant_id, wid, adapter.forge_paths).exists()
                        if existing:
                            if conflict_mode == "skip":
                                adapter.audit_backend.action_performed(
                                    tenant_id=tenant_id,
                                    action=f"workflow.import.conflict_{conflict_mode}",
                                    target_kind="workflow",
                                    target_id=wid,
                                )
                                return {"ok": True, "workflow_id": wid, "action": "skipped"}
                            elif conflict_mode == "rename":
                                import asyncio
                                wid = asyncio.run(_generate_unique_wid(wid, adapter.forge_paths, tenant_id))
                            elif conflict_mode == "overwrite":
                                # Will overwrite below
                                pass

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
                            action="workflow.import.completed",
                            target_kind="workflow",
                            target_id=wid,
                            details={
                                "conflict_mode": conflict_mode,
                                "size_bytes": len(file_bytes),
                                "checksum": stored_checksum[:16] if stored_checksum else None,
                                "tools_registered": len(tools_registered)
                            }
                        )
                        _log.info(f"Imported AWPKG workflow {wid} (tools={len(tools_registered)}, conflict_mode={conflict_mode})")
                        return {
                            "ok": True,
                            "workflow_id": wid,
                            "tools_registered": tools_registered,
                        }
                except zipfile.BadZipFile:
                    adapter.audit_backend.action_failed(
                        tenant_id=tenant_id,
                        action="workflow.import.failed",
                        target_kind="workflow",
                        target_id="pending",
                        reason="invalid_zip_format",
                    )
                    raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Invalid ZIP file")
                except HTTPException:
                    raise
                except Exception as e:
                    adapter.audit_backend.action_failed(
                        tenant_id=tenant_id,
                        action="workflow.import.failed",
                        target_kind="workflow",
                        target_id="pending",
                        reason=str(e),
                    )
                    _log.error(f"AWPKG import failed: {e}")
                    raise HTTPException(http_status.HTTP_400_BAD_REQUEST, f"AWPKG import failed: {e}")
            finally:
                try:
                    Path(tmp_path).unlink()
                except Exception:
                    pass

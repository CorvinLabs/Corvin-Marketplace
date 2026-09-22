"""AWPKG export route — workflow packaging for distribution (Phase 5)."""
import hashlib
import io
import json
import logging
import zipfile
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status as http_status

from .helpers import validate_wid, require_workflow, yaml_path, meta_path, read_json_or_none

_log = logging.getLogger(__name__)

router = APIRouter()

# Constants
_MAX_AWPKG_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit


# ── Dependency injection (soft dep) ────────────────────────────────────

class ExportAdapter:
    """Adapter for export dependencies."""

    def __init__(self, forge_paths, audit_backend=None):
        self.forge_paths = forge_paths
        self.audit_backend = audit_backend


def get_export_adapter() -> ExportAdapter:
    """Inject dependencies (override in plugin bootstrap)."""
    raise NotImplementedError("export adapter not initialized in plugin bootstrap")


# ── AWPKG helpers ──────────────────────────────────────────────────────

def _collect_workflow_refs(yaml_text: str) -> tuple[dict[str, list[str]], dict[str, list[str]], list[str], list[str]]:
    """Parse workflow YAML and return tool/skill references.

    Returns:
        agent_tools   : {agent_id: [tool_name, ...]}   — per node
        agent_skills  : {agent_id: [skill_name, ...]}  — per node
        all_tools     : flat deduplicated list of tool names
        all_skills    : flat deduplicated list of skill names
    """
    agent_tools: dict[str, list[str]] = {}
    agent_skills: dict[str, list[str]] = {}
    all_tools: list[str] = []
    all_skills: list[str] = []
    seen_tools: set[str] = set()
    seen_skills: set[str] = set()

    try:
        import yaml
        doc = yaml.safe_load(yaml_text) or {}
    except Exception:
        return agent_tools, agent_skills, all_tools, all_skills

    graph = (doc.get("orchestration") or {}).get("graph") or []
    for node in graph:
        if not isinstance(node, dict):
            continue
        agent_id = str(node.get("agent") or node.get("id") or "")
        node_tools = node.get("forge_tools") or node.get("tools") or []
        node_skills = node.get("skills") or []
        if isinstance(node_tools, str):
            node_tools = [node_tools]
        if isinstance(node_skills, str):
            node_skills = [node_skills]
        node_tools = [str(t) for t in node_tools if t]
        node_skills = [str(s) for s in node_skills if s]

        if node_tools:
            agent_tools.setdefault(agent_id, []).extend(node_tools)
        if node_skills:
            agent_skills.setdefault(agent_id, []).extend(node_skills)

        for t in node_tools:
            if t not in seen_tools:
                seen_tools.add(t)
                all_tools.append(t)
        for s in node_skills:
            if s not in seen_skills:
                seen_skills.add(s)
                all_skills.append(s)

    return agent_tools, agent_skills, all_tools, all_skills


def _resolve_forge_tool(tenant_id: str, tool_name: str, forge_paths) -> bytes | None:
    """Return a bundleable tool JSON (name+schema+code) from Forge registry.

    Returns None if tool not found or registry unavailable.
    """
    home = forge_paths.tenant_home(tenant_id)
    registry_file = home / "global" / "forge" / "registry.json"
    if not registry_file.exists():
        return None
    try:
        registry: dict = json.loads(registry_file.read_text(encoding="utf-8"))
    except Exception:
        return None

    # Match by exact name or with/without "code." prefix
    entry = (
        registry.get(tool_name)
        or registry.get(f"code.{tool_name}")
        or registry.get(tool_name.removeprefix("code.") if tool_name.startswith("code.") else None)
    )
    if not entry:
        return None

    actual_name: str = entry["name"]
    tools_dir = home / "global" / "forge" / "tools"
    py_file = tools_dir / f"{actual_name}.py"

    if not py_file.exists():
        # Fallback: check impl_path
        raw_impl = entry.get("impl_path", "")
        if raw_impl:
            from pathlib import Path
            py_file = Path(raw_impl)

    if not py_file.exists() or not py_file.is_file():
        return None

    try:
        code = py_file.read_text(encoding="utf-8")
        bundle = {
            "name": actual_name,
            "description": entry.get("description", ""),
            "input_schema": entry.get("input_schema", {"type": "object", "properties": {}, "required": []}),
            "meta": {
                "language": "python",
                "network": "deny",
                **entry.get("meta", {}),
            },
            "code": code,
        }
        return json.dumps(bundle, indent=2, ensure_ascii=False).encode("utf-8")
    except Exception as exc:
        _log.debug("tool resolution failed for %s: %s", tool_name, exc)
        return None


def _resolve_skill(tenant_id: str, skill_name: str, forge_paths) -> bytes | None:
    """Return SKILL.md bytes for a skill, checking multiple locations."""
    from pathlib import Path
    home = forge_paths.tenant_home(tenant_id)
    user_home = Path.home()

    candidates = [
        home / "global" / "skill-forge" / "skills" / skill_name / "SKILL.md",
        user_home / ".corvin" / "global" / "skill-forge" / "skills" / skill_name / "SKILL.md",
        user_home / ".claude" / "skills" / skill_name / "SKILL.md",
    ]
    for c in candidates:
        if c.exists():
            try:
                return c.read_bytes()
            except Exception:
                pass

    return None


# ── Routes: Export ────────────────────────────────────────────────────

@router.get("/workflows/{wid}/export.awpkg")
def export_awpkg(
    wid: str,
    tenant_id: str,
    adapter: ExportAdapter = Depends(get_export_adapter),
) -> Response:
    """Export workflow as AWPKG ZIP bundle with tools and skills.

    Phase 5 feature: creates a self-contained, portable workflow package.
    Returns: ZIP file as application/zip.

    Audit events:
      - workflow.export.started: Before export begins
      - workflow.export.completed: After successful export (includes size, checksum)
      - workflow.export.failed: On any error
    """
    validate_wid(wid)

    if adapter.audit_backend:
        adapter.audit_backend.action_started(
            tenant_id=tenant_id,
            action="workflow.export",
            target_kind="workflow",
            target_id=wid,
        )

    try:
        meta = require_workflow(tenant_id, wid, adapter.forge_paths)
        yaml_p = yaml_path(tenant_id, wid, adapter.forge_paths)
        if not yaml_p.exists():
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "workflow YAML not found")

        yaml_text = yaml_p.read_text(encoding="utf-8")
        agent_tools, agent_skills, all_tools, all_skills = _collect_workflow_refs(yaml_text)

        # Build AWPKG manifest
        manifest_dict: dict[str, Any] = {
            "awpkg": "1.0",
            "id": f"com.corvin.{wid.replace('_', '-')}",
            "name": meta.get("title", wid),
            "version": "0.1.0",
            "description": meta.get("description", "") or "",
            "components": {
                "workflows": [f"workflows/{wid}.awp.yaml"],
                "tools": [f"tools/{t}.json" for t in all_tools],
                "skills": [f"skills/{s}.md" for s in all_skills],
            },
            "permissions": {"network": False, "compute": False, "secrets": []},
            "references": {
                "tools_by_agent": agent_tools,
                "skills_by_agent": agent_skills,
            },
        }

        # Create ZIP
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Write manifest
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

            # Write workflow YAML
            zf.writestr(f"workflows/{wid}.awp.yaml", yaml_text.encode("utf-8"))

            # Write tools (best-effort)
            for tool_name in all_tools:
                tool_data = _resolve_forge_tool(tenant_id, tool_name, adapter.forge_paths)
                if tool_data:
                    zf.writestr(f"tools/{tool_name}.json", tool_data)

            # Write skills (best-effort)
            for skill_name in all_skills:
                skill_data = _resolve_skill(tenant_id, skill_name, adapter.forge_paths)
                if skill_data:
                    zf.writestr(f"skills/{skill_name}.md", skill_data)

            # Write checksum (SHA256 of workflow YAML)
            yaml_bytes = yaml_text.encode("utf-8")
            checksum = hashlib.sha256(yaml_bytes).hexdigest()
            zf.writestr("checksum.txt", checksum)

        pkg_bytes = buf.getvalue()

        # Enforce size limit
        if len(pkg_bytes) > _MAX_AWPKG_SIZE_BYTES:
            raise HTTPException(
                http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"AWPKG size exceeds limit ({len(pkg_bytes)} > {_MAX_AWPKG_SIZE_BYTES} bytes)"
            )

        # Audit success
        if adapter.audit_backend:
            adapter.audit_backend.action_performed(
                tenant_id=tenant_id,
                action="workflow.export.completed",
                target_kind="workflow",
                target_id=wid,
                details={
                    "size_bytes": len(pkg_bytes),
                    "checksum": checksum,
                    "tools_count": len(all_tools),
                    "skills_count": len(all_skills),
                }
            )

        _log.info(f"Exported workflow {wid} as AWPKG ({len(pkg_bytes)} bytes, checksum={checksum[:8]}...)")

        return Response(
            content=pkg_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={wid}.awpkg"},
        )
    except HTTPException:
        raise
    except Exception as e:
        if adapter.audit_backend:
            adapter.audit_backend.action_failed(
                tenant_id=tenant_id,
                action="workflow.export.failed",
                target_kind="workflow",
                target_id=wid,
                reason=str(e),
            )
        _log.error(f"Export failed for workflow {wid}: {e}")
        raise HTTPException(http_status.HTTP_500_INTERNAL_SERVER_ERROR, f"export failed: {e}")

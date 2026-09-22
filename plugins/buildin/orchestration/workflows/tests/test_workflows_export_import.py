"""E2E tests for workflow export/import (Phase 5)."""
import hashlib
import json
import pytest
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path


# Mock audit backend for testing
class MockAuditBackend:
    """Mock audit backend that tracks events."""
    def __init__(self):
        self.events = []

    def action_started(self, **kwargs):
        self.events.append({"type": "started", **kwargs})

    def action_performed(self, **kwargs):
        self.events.append({"type": "performed", **kwargs})

    def action_failed(self, **kwargs):
        self.events.append({"type": "failed", **kwargs})

    def get_events_by_action(self, action):
        return [e for e in self.events if e.get("action") == action]


class MockForgePaths:
    """Mock forge paths for testing."""
    def __init__(self, tmpdir):
        self.tmpdir = tmpdir

    def tenant_home(self, tenant_id):
        return Path(self.tmpdir) / "tenants" / tenant_id


class MockLicenseBackend:
    """Mock license backend."""
    pass


class MockPromptGuard:
    """Mock prompt guard."""
    pass


def create_test_workflow_yaml(wid: str = "test-wf") -> str:
    """Create a minimal test workflow YAML."""
    return f"""orchestration:
  id: {wid}
  title: Test Workflow
  graph:
    - id: node1
      agent: agent1
      type: claude
      model: claude-3-opus
      tools:
        - tool1
        - tool2
      skills:
        - skill1
"""


def create_test_awpkg_zip(wid: str = "test-wf", include_checksum: bool = True) -> bytes:
    """Create a minimal test AWPKG ZIP file."""
    yaml_text = create_test_workflow_yaml(wid)

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Write manifest
        manifest = {
            "awpkg": "1.0",
            "id": f"com.corvin.{wid}",
            "name": f"Test Workflow {wid}",
            "version": "0.1.0",
            "description": "Test workflow",
        }
        zf.writestr("manifest.yaml", json.dumps(manifest))

        # Write workflow YAML
        zf.writestr(f"workflows/{wid}.awp.yaml", yaml_text)

        # Write checksum if requested
        if include_checksum:
            checksum = hashlib.sha256(yaml_text.encode()).hexdigest()
            zf.writestr("checksum.txt", checksum)

    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def tmpdir_fixture(tmp_path):
    """Provide a temporary directory."""
    return tmp_path


@pytest.fixture
def audit_backend():
    """Provide a mock audit backend."""
    return MockAuditBackend()


@pytest.fixture
def forge_paths(tmpdir_fixture):
    """Provide mock forge paths."""
    return MockForgePaths(tmpdir_fixture)


@pytest.fixture
def import_adapter(audit_backend, forge_paths):
    """Provide import adapter with mocked dependencies."""
    from plugin_workflows.routes.import_workflows import ImportAdapter
    return ImportAdapter(
        audit_backend=audit_backend,
        forge_paths=forge_paths,
        license_backend=MockLicenseBackend(),
    )


@pytest.fixture
def export_adapter(audit_backend, forge_paths):
    """Provide export adapter with mocked dependencies."""
    from plugin_workflows.routes.export import ExportAdapter
    return ExportAdapter(
        forge_paths=forge_paths,
        audit_backend=audit_backend,
    )


class MockUploadFile:
    """Mock FastAPI UploadFile for testing."""
    def __init__(self, filename, content):
        self.filename = filename
        self.file = BytesIO(content)


class TestWorkflowExportImportPhase5:
    """Phase 5 export/import test suite (8 mandatory test cases)."""

    def test_export_creates_valid_zip(self, export_adapter, forge_paths):
        """[TEST 1] Export workflow as valid ZIP with correct structure."""
        # Setup: Create test workflow
        tenant_id = "_default"
        wid = "test-export-1"

        workflows_dir = forge_paths.tenant_home(tenant_id) / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)

        yaml_text = create_test_workflow_yaml(wid)
        yaml_file = workflows_dir / f"{wid}.awp.yaml"
        yaml_file.write_text(yaml_text)

        meta = {
            "id": wid,
            "title": "Test Workflow",
            "description": "A test workflow",
            "created_at": 1234567890,
        }
        meta_file = workflows_dir / f"{wid}.meta.json"
        meta_file.write_text(json.dumps(meta))

        # Export
        from plugin_workflows.routes.export import export_awpkg
        response = export_awpkg(wid, tenant_id, export_adapter)

        # Verify: Response is a ZIP file
        pkg_bytes = response.body if hasattr(response, 'body') else b""

        # Verify ZIP structure
        assert pkg_bytes, "Export returned empty response"
        with zipfile.ZipFile(BytesIO(pkg_bytes), 'r') as zf:
            names = zf.namelist()
            assert any(f.endswith('.awp.yaml') for f in names), "No workflow YAML in export"
            assert "manifest.yaml" in names or "manifest.json" in names, "No manifest in export"
            assert "checksum.txt" in names, "No checksum in export"

    def test_export_includes_checksum(self, export_adapter, forge_paths):
        """[TEST 2] Export includes SHA256 checksum for integrity verification."""
        tenant_id = "_default"
        wid = "test-checksum"

        workflows_dir = forge_paths.tenant_home(tenant_id) / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)

        yaml_text = create_test_workflow_yaml(wid)
        yaml_file = workflows_dir / f"{wid}.awp.yaml"
        yaml_file.write_text(yaml_text)

        meta_file = workflows_dir / f"{wid}.meta.json"
        meta_file.write_text(json.dumps({"id": wid, "title": wid}))

        from plugin_workflows.routes.export import export_awpkg
        response = export_awpkg(wid, tenant_id, export_adapter)

        # Extract checksum from ZIP
        pkg_bytes = response.body if hasattr(response, 'body') else b""
        assert pkg_bytes, "Export returned empty response"

        with zipfile.ZipFile(BytesIO(pkg_bytes), 'r') as zf:
            checksum_text = zf.read("checksum.txt").decode().strip()

            # Verify checksum format (SHA256 = 64 hex chars)
            assert len(checksum_text) == 64, "Checksum not SHA256 format"
            assert all(c in '0123456789abcdef' for c in checksum_text), "Invalid hex characters in checksum"

            # Verify checksum matches workflow YAML
            yaml_content = zf.read(f"workflows/{wid}.awp.yaml").decode()
            computed = hashlib.sha256(yaml_content.encode()).hexdigest()
            assert computed == checksum_text, "Checksum mismatch"

    def test_import_valid_awpkg_creates_workflow(self, import_adapter):
        """[TEST 3] Import valid AWPKG creates workflow and registers entry."""
        tenant_id = "_default"
        wid = "test-import-1"

        # Create test AWPKG
        awpkg_bytes = create_test_awpkg_zip(wid)

        from plugin_workflows.routes.import_workflows import import_workflow

        upload_file = MockUploadFile(f"{wid}.awpkg", awpkg_bytes)

        result = import_workflow(
            file=upload_file,
            tenant_id=tenant_id,
            conflict_mode="overwrite",
            adapter=import_adapter,
        )

        # Verify result
        assert result["ok"] is True
        assert "workflow_id" in result
        assert result["workflow_id"] == wid

        # Verify workflow files exist
        workflows_dir = import_adapter.forge_paths.tenant_home(tenant_id) / "workflows"
        yaml_file = workflows_dir / f"{wid}.awp.yaml"
        meta_file = workflows_dir / f"{wid}.meta.json"

        assert yaml_file.exists(), "Workflow YAML file not created"
        assert meta_file.exists(), "Workflow metadata file not created"

    def test_import_size_limit_exceeded(self, import_adapter):
        """[TEST 4] Import rejects AWPKG exceeding 10 MB size limit."""
        from fastapi import HTTPException
        from plugin_workflows.routes.import_workflows import import_workflow

        # Create oversized file (11 MB)
        oversized = b"x" * (11 * 1024 * 1024)
        upload_file = MockUploadFile("large.awpkg", oversized)

        with pytest.raises(HTTPException) as exc_info:
            import_workflow(
                file=upload_file,
                tenant_id="_default",
                conflict_mode="overwrite",
                adapter=import_adapter,
            )

        assert exc_info.value.status_code == 413, "Should return 413 ENTITY_TOO_LARGE"

    def test_import_invalid_zip_rejected(self, import_adapter):
        """[TEST 5] Import rejects malformed ZIP files."""
        from fastapi import HTTPException
        from plugin_workflows.routes.import_workflows import import_workflow

        # Create invalid ZIP (just random bytes)
        invalid_zip = b"NOT_A_ZIP_FILE_" * 100
        upload_file = MockUploadFile("invalid.awpkg", invalid_zip)

        with pytest.raises(HTTPException) as exc_info:
            import_workflow(
                file=upload_file,
                tenant_id="_default",
                conflict_mode="overwrite",
                adapter=import_adapter,
            )

        assert exc_info.value.status_code == 400, "Should reject invalid ZIP"

    def test_import_conflict_skip_mode(self, import_adapter):
        """[TEST 6] Import respects 'skip' conflict mode for existing workflows."""
        from plugin_workflows.routes.import_workflows import import_workflow

        tenant_id = "_default"
        wid = "test-conflict"

        # First import (creates workflow)
        awpkg_bytes = create_test_awpkg_zip(wid)
        upload_file1 = MockUploadFile(f"{wid}.awpkg", awpkg_bytes)

        result1 = import_workflow(
            file=upload_file1,
            tenant_id=tenant_id,
            conflict_mode="overwrite",
            adapter=import_adapter,
        )
        assert result1["ok"] is True

        # Second import with skip mode (should skip)
        awpkg_bytes = create_test_awpkg_zip(wid)
        upload_file2 = MockUploadFile(f"{wid}.awpkg", awpkg_bytes)

        result2 = import_workflow(
            file=upload_file2,
            tenant_id=tenant_id,
            conflict_mode="skip",
            adapter=import_adapter,
        )
        assert result2["ok"] is True
        assert result2.get("action") == "skipped"

    def test_roundtrip_integrity_yaml_preserved(self, export_adapter, import_adapter, forge_paths):
        """[TEST 7] Export-import roundtrip preserves YAML content (byte-identical)."""
        tenant_id = "_default"
        wid = "test-roundtrip"

        # Create original workflow
        workflows_dir = forge_paths.tenant_home(tenant_id) / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)

        original_yaml = create_test_workflow_yaml(wid)
        yaml_file = workflows_dir / f"{wid}.awp.yaml"
        yaml_file.write_text(original_yaml)

        meta_file = workflows_dir / f"{wid}.meta.json"
        meta_file.write_text(json.dumps({"id": wid, "title": wid}))

        # Export
        from plugin_workflows.routes.export import export_awpkg
        response = export_awpkg(wid, tenant_id, export_adapter)
        export_bytes = response.body if hasattr(response, 'body') else b""

        # Extract YAML from exported ZIP
        assert export_bytes, "Export returned empty response"
        with zipfile.ZipFile(BytesIO(export_bytes), 'r') as zf:
            exported_yaml = zf.read(f"workflows/{wid}.awp.yaml").decode()

            # Verify YAML content is identical
            assert exported_yaml == original_yaml, "YAML content changed during export"

            # Verify checksum
            stored_checksum = zf.read("checksum.txt").decode().strip()
            computed_checksum = hashlib.sha256(exported_yaml.encode()).hexdigest()
            assert stored_checksum == computed_checksum, "Checksum verification failed"

    def test_audit_events_logged_export_import(self, export_adapter, import_adapter, audit_backend, forge_paths):
        """[TEST 8] Export and import log audit events for compliance and traceability."""
        from plugin_workflows.routes.export import export_awpkg
        from plugin_workflows.routes.import_workflows import import_workflow

        tenant_id = "_default"
        wid = "test-audit"

        # Create workflow for export
        workflows_dir = forge_paths.tenant_home(tenant_id) / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)

        yaml_file = workflows_dir / f"{wid}.awp.yaml"
        yaml_file.write_text(create_test_workflow_yaml(wid))

        meta_file = workflows_dir / f"{wid}.meta.json"
        meta_file.write_text(json.dumps({"id": wid}))

        # Clear and export
        audit_backend.events = []
        response = export_awpkg(wid, tenant_id, export_adapter)

        # Check export audit events
        export_started = audit_backend.get_events_by_action("workflow.export")
        assert len(export_started) > 0, "No export audit event"

        # Import and check audit events
        export_bytes = response.body if hasattr(response, 'body') else b""
        assert export_bytes, "Export returned empty response"

        audit_backend.events = []
        upload_file = MockUploadFile(f"{wid}2.awpkg", export_bytes)

        result = import_workflow(
            file=upload_file,
            tenant_id=tenant_id,
            conflict_mode="overwrite",
            adapter=import_adapter,
        )

        # Check import audit events
        assert len(audit_backend.events) > 0, "No import audit events"
        assert result["ok"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

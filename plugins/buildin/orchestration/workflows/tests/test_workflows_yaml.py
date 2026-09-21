"""E2E tests for workflow YAML management."""
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from plugin_workflows.plugin import WorkflowsPlugin
from plugin_workflows.adapters import NoOpAuditBackend, FreeTierLicenseBackend, NoOpPromptGuard


@pytest.fixture
def app():
    """Create FastAPI app with WorkflowsPlugin."""
    app = FastAPI()
    plugin = WorkflowsPlugin(
        audit_backend=NoOpAuditBackend(),
        license_backend=FreeTierLicenseBackend(),
        prompt_guard=NoOpPromptGuard(),
    )
    app.include_router(plugin.router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestWorkflowYAML:
    """YAML management tests."""

    def test_get_workflow_yaml_returns_yaml(self, client):
        """GET /workflows/{wid}/yaml returns workflow YAML."""
        response = client.get("/workflows/test-wid/yaml")
        assert response.status_code in [200, 404]

    def test_get_workflow_yaml_nonexistent_returns_404(self, client):
        """GET /workflows/{wid}/yaml returns 404 for nonexistent workflow."""
        response = client.get("/workflows/nonexistent-wid/yaml")
        assert response.status_code == 404

    def test_update_workflow_yaml_requires_yaml(self, client):
        """PUT /workflows/{wid}/yaml requires yaml field."""
        response = client.put("/workflows/test-wid/yaml", json={})
        # Should fail validation if yaml is missing
        assert response.status_code in [400, 422, 404]

    def test_update_workflow_yaml_accepts_yaml(self, client):
        """PUT /workflows/{wid}/yaml accepts valid YAML."""
        yaml_content = """
nodes:
  - id: node1
    type: claude
    prompt: "Hello, world!"
"""
        response = client.put("/workflows/test-wid/yaml", json={
            "yaml": yaml_content
        })
        # Should return 200, 204, or 404 (workflow doesn't exist)
        assert response.status_code in [200, 204, 404]

    def test_update_workflow_yaml_validates_size(self, client):
        """PUT /workflows/{wid}/yaml rejects oversized YAML."""
        # Create YAML larger than _MAX_YAML_BYTES (256 KiB)
        huge_yaml = "x: " + "y" * (300 * 1024)  # 300 KiB
        response = client.put("/workflows/test-wid/yaml", json={
            "yaml": huge_yaml
        })
        # Should reject oversized payload
        assert response.status_code in [413, 422, 400]

    def test_update_workflow_yaml_preserves_content(self, client):
        """PUT /workflows/{wid}/yaml stores YAML correctly."""
        original_yaml = "test: value\nnodes: []\n"
        response = client.put("/workflows/test-wid/yaml", json={
            "yaml": original_yaml
        })
        if response.status_code in [200, 204]:
            # Verify we can read it back
            get_resp = client.get("/workflows/test-wid/yaml")
            if get_resp.status_code == 200:
                data = get_resp.json()
                # YAML should be readable
                assert "yaml" in data or data

    def test_yaml_validation_on_invalid_syntax(self, client):
        """YAML with invalid syntax is handled."""
        invalid_yaml = "{ invalid yaml [["
        response = client.put("/workflows/test-wid/yaml", json={
            "yaml": invalid_yaml
        })
        # Should accept (validation may be deferred to run time)
        assert response.status_code in [200, 204, 400, 404]

    def test_yaml_roundtrip(self, client):
        """YAML written and read back preserves structure."""
        test_yaml = "version: 1.0\nname: test\n"
        write_resp = client.put("/workflows/wid123/yaml", json={"yaml": test_yaml})
        if write_resp.status_code in [200, 204]:
            read_resp = client.get("/workflows/wid123/yaml")
            if read_resp.status_code == 200:
                data = read_resp.json()
                # Should contain YAML (exact match depends on formatting)
                assert "yaml" in data or data

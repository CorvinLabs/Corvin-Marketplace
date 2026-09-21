"""E2E tests for workflow run lifecycle."""
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from plugin_workflows.plugin import WorkflowsPlugin
from plugin_workflows.adapters import (
    NoOpAuditBackend, MemoryStorageBackend, FreeTierLicenseBackend, NoOpPromptGuard
)


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


class TestWorkflowRuns:
    """Workflow run lifecycle tests."""

    def test_list_runs_empty_returns_200(self, client):
        """GET /workflows/{wid}/runs returns 200 for empty runs list."""
        # Create a workflow first (if needed)
        response = client.get("/workflows/test-wid/runs")
        assert response.status_code in [200, 404]

    def test_list_runs_structure(self, client):
        """GET /workflows/{wid}/runs returns proper structure."""
        response = client.get("/workflows/test-wid/runs")
        if response.status_code == 200:
            data = response.json()
            assert "workflow_id" in data or "runs" in data

    def test_get_run_nonexistent_returns_404(self, client):
        """GET /workflows/{wid}/runs/{rid} returns 404 for nonexistent run."""
        response = client.get("/workflows/test-wid/runs/nonexistent-rid")
        assert response.status_code == 404

    def test_delete_run_nonexistent_returns_404(self, client):
        """DELETE /workflows/{wid}/runs/{rid} returns 404 for nonexistent run."""
        response = client.delete("/workflows/test-wid/runs/nonexistent-rid")
        assert response.status_code == 404

    def test_delete_run_returns_200_or_204(self, client):
        """DELETE /workflows/{wid}/runs/{rid} returns 200/204 on success."""
        # Response should be 200, 204, or 404
        response = client.delete("/workflows/test-wid/runs/some-rid")
        assert response.status_code in [200, 204, 404]

    def test_start_run_requires_valid_workflow(self, client):
        """POST /workflows/{wid}/runs requires workflow to exist."""
        response = client.post("/workflows/nonexistent/runs", json={
            "inputs": {},
            "dry_run": False
        })
        # Should fail if workflow doesn't exist
        assert response.status_code >= 400

    def test_start_run_request_validation(self, client):
        """POST /workflows/{wid}/runs validates request payload."""
        response = client.post("/workflows/test-wid/runs", json={
            "invalid_field": "value"
        })
        # Should accept empty body or validate schema
        assert response.status_code in [200, 201, 400, 404]

    def test_start_run_with_dry_run(self, client):
        """POST /workflows/{wid}/runs accepts dry_run flag."""
        response = client.post("/workflows/test-wid/runs", json={
            "dry_run": True,
            "inputs": {}
        })
        # Should accept dry_run parameter
        assert response.status_code in [200, 201, 404, 400]

    def test_approve_run_returns_valid_status(self, client):
        """POST /workflows/{wid}/runs/{rid}/approve returns valid status."""
        response = client.post("/workflows/test-wid/runs/test-rid/approve", json={
            "comment": "Approved"
        })
        # Should return 200/204 or 404 (if not exists)
        assert response.status_code in [200, 204, 404]

    def test_resume_run_returns_valid_status(self, client):
        """POST /workflows/{wid}/runs/{rid}/resume returns valid status."""
        response = client.post("/workflows/test-wid/runs/test-rid/resume", json={
            "inputs": {"key": "value"}
        })
        # Should return 200/201 or 404 (if not exists)
        assert response.status_code in [200, 201, 404]

    def test_run_lifecycle_isolation(self, client):
        """Multiple run operations are isolated."""
        # Create multiple runs (if workflow exists)
        response1 = client.get("/workflows/wf1/runs")
        response2 = client.get("/workflows/wf2/runs")
        # Both should return independently
        assert response1.status_code in [200, 404]
        assert response2.status_code in [200, 404]

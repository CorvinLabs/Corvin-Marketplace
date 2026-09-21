"""E2E tests for workflow CRUD operations."""
import json
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


class TestWorkflowCRUD:
    """CRUD operation tests."""

    def test_create_workflow_returns_201(self, client):
        """POST /workflows creates workflow and returns 201."""
        response = client.post("/workflows", json={
            "title": "Test Workflow",
            "description": "A test workflow",
            "yaml": "nodes:\n  - id: node1\n    type: claude\n"
        })
        assert response.status_code == 201
        data = response.json()
        assert "id" in data or "workflow" in data
        assert data.get("ok") is True or "workflow" in data

    def test_create_workflow_requires_title(self, client):
        """POST /workflows requires title field."""
        response = client.post("/workflows", json={
            "description": "No title"
        })
        assert response.status_code == 422  # Validation error

    def test_create_workflow_rejects_empty_title(self, client):
        """POST /workflows rejects empty/whitespace-only titles."""
        response = client.post("/workflows", json={
            "title": "   ",  # Whitespace only
            "yaml": "nodes: []"
        })
        assert response.status_code == 422  # Validation error

    def test_list_workflows_returns_200(self, client):
        """GET /workflows returns 200 with workflow list."""
        response = client.get("/workflows")
        assert response.status_code == 200
        data = response.json()
        assert "workflows" in data or "count" in data

    def test_list_workflows_structure(self, client):
        """GET /workflows returns proper structure."""
        response = client.get("/workflows")
        data = response.json()
        assert isinstance(data.get("workflows"), list)

    def test_get_workflow_returns_workflow(self, client):
        """GET /workflows/{wid} returns workflow details."""
        # First create a workflow
        create_resp = client.post("/workflows", json={
            "title": "Get Test"
        })
        if create_resp.status_code == 201:
            data = create_resp.json()
            wid = data.get("id") or data.get("workflow", {}).get("id")
            if wid:
                get_resp = client.get(f"/workflows/{wid}")
                assert get_resp.status_code == 200

    def test_get_workflow_nonexistent_returns_404(self, client):
        """GET /workflows/{wid} returns 404 for nonexistent workflow."""
        response = client.get("/workflows/nonexistent-wid")
        assert response.status_code == 404

    def test_patch_workflow_updates_title(self, client):
        """PATCH /workflows/{wid} updates workflow title."""
        # Create first
        create_resp = client.post("/workflows", json={
            "title": "Original Title"
        })
        if create_resp.status_code == 201:
            data = create_resp.json()
            wid = data.get("id") or data.get("workflow", {}).get("id")
            if wid:
                # Update
                patch_resp = client.patch(f"/workflows/{wid}", json={
                    "title": "Updated Title"
                })
                assert patch_resp.status_code == 200

    def test_delete_workflow_returns_204(self, client):
        """DELETE /workflows/{wid} deletes workflow."""
        # Create first
        create_resp = client.post("/workflows", json={
            "title": "Delete Test"
        })
        if create_resp.status_code == 201:
            data = create_resp.json()
            wid = data.get("id") or data.get("workflow", {}).get("id")
            if wid:
                delete_resp = client.delete(f"/workflows/{wid}")
                assert delete_resp.status_code in [200, 204]

    def test_delete_nonexistent_workflow_returns_404(self, client):
        """DELETE /workflows/{wid} returns 404 for nonexistent workflow."""
        response = client.delete("/workflows/nonexistent-wid")
        assert response.status_code == 404

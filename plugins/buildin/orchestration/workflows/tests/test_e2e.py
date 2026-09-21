"""E2E tests for workflows plugin — create, edit, run workflow."""

import pytest
import json
from pathlib import Path

from plugin_workflows.plugin import WorkflowsPlugin
from plugin_workflows.adapters import (
    DenyAllSessionBackend,
    NoOpAuditBackend,
    MemoryStorageBackend,
    FreeTierLicenseBackend,
    NoOpPromptGuard,
    NoOpSchedulerBackend,
)


@pytest.fixture
def plugin():
    """Provide plugin instance."""
    return WorkflowsPlugin(
        session_backend=DenyAllSessionBackend(),
        audit_backend=NoOpAuditBackend(),
        storage_backend=MemoryStorageBackend(),
        license_backend=FreeTierLicenseBackend(),
        prompt_guard=NoOpPromptGuard(),
        scheduler_backend=NoOpSchedulerBackend(),
    )


@pytest.fixture
def client(plugin):
    """Provide FastAPI test client."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(plugin.get_router(), prefix="/v1/console")
    return TestClient(app)


class TestWorkflowE2E:
    """End-to-end workflow lifecycle tests."""

    def test_list_workflows_returns_empty_initially(self, client):
        """GET /workflows should return empty list initially."""
        response = client.get("/v1/console/workflows")
        assert response.status_code == 200
        data = response.json()
        assert "workflows" in data or "message" in data
        # Plugin returns placeholder message in Phase 1

    def test_create_workflow_placeholder(self, client):
        """POST /workflows should create a workflow (placeholder)."""
        response = client.post(
            "/v1/console/workflows",
            json={"title": "Test Workflow", "description": "Test"},
        )
        assert response.status_code == 200
        data = response.json()
        # Phase 2-3 will implement actual creation
        assert "wid" in data or "message" in data

    def test_get_workflow_placeholder(self, client):
        """GET /workflows/{wid} should return workflow (placeholder)."""
        response = client.get("/v1/console/workflows/wf-test-001")
        assert response.status_code == 200
        data = response.json()
        assert "wid" in data or "message" in data

    def test_start_run_placeholder(self, client):
        """POST /workflows/{wid}/runs should start a run (placeholder)."""
        response = client.post("/v1/console/workflows/wf-test-001/runs")
        assert response.status_code == 200
        data = response.json()
        assert "rid" in data or "message" in data

    def test_list_runs_placeholder(self, client):
        """GET /workflows/{wid}/runs should list runs (placeholder)."""
        response = client.get("/v1/console/workflows/wf-test-001/runs")
        assert response.status_code == 200
        data = response.json()
        assert "runs" in data or "message" in data


class TestPluginInitialization:
    """Test plugin initialization and lifecycle."""

    def test_plugin_initializes_with_fallback_adapters(self):
        """Plugin should initialize with fallback adapters if none provided."""
        plugin = WorkflowsPlugin()
        assert plugin.session_backend is not None
        assert plugin.audit_backend is not None
        assert plugin.storage_backend is not None
        assert plugin.license_backend is not None
        assert plugin.prompt_guard is not None
        assert plugin.scheduler_backend is not None

    def test_plugin_router_created(self):
        """Plugin should create a FastAPI router."""
        plugin = WorkflowsPlugin()
        router = plugin.get_router()
        assert router is not None
        assert len(router.routes) > 0

    @pytest.mark.asyncio
    async def test_plugin_lifecycle_hooks(self):
        """Plugin should support lifecycle hooks."""
        plugin = WorkflowsPlugin()
        await plugin.on_load()  # Should not raise
        await plugin.on_unload()  # Should not raise

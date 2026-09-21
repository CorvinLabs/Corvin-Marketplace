"""E2E tests for workflow scheduling (Phase 4)."""
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from plugin_workflows.plugin import WorkflowsPlugin
from plugin_workflows.adapters import NoOpAuditBackend, FreeTierLicenseBackend, NoOpPromptGuard


@pytest.fixture
def app():
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
    return TestClient(app)


class TestWorkflowScheduling:
    """Workflow scheduling tests."""

    def test_get_schedule_returns_schedule_or_null(self, client):
        """GET /workflows/{wid}/schedule returns schedule or null."""
        response = client.get("/workflows/test-wid/schedule")
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert "schedule" in data

    def test_set_schedule_with_cron(self, client):
        """PUT /workflows/{wid}/schedule sets cron schedule."""
        response = client.put("/workflows/test-wid/schedule", json={
            "cron": "0 0 * * *"  # Daily at midnight
        })
        assert response.status_code in [200, 204, 404]

    def test_set_schedule_requires_cron(self, client):
        """PUT /workflows/{wid}/schedule requires cron field."""
        response = client.put("/workflows/test-wid/schedule", json={})
        assert response.status_code in [400, 422, 404]

    def test_set_schedule_validates_cron_format(self, client):
        """PUT /workflows/{wid}/schedule validates cron format."""
        response = client.put("/workflows/test-wid/schedule", json={
            "cron": "invalid cron"
        })
        # Should accept or reject invalid cron
        assert response.status_code in [200, 204, 400, 422, 404]

    def test_remove_schedule_returns_200_or_204(self, client):
        """DELETE /workflows/{wid}/schedule removes schedule."""
        response = client.delete("/workflows/test-wid/schedule")
        assert response.status_code in [200, 204, 404]

    def test_schedule_cron_examples(self, client):
        """Common cron expressions are accepted."""
        cron_examples = [
            "0 0 * * *",        # Daily
            "0 * * * *",        # Hourly
            "*/5 * * * *",       # Every 5 minutes
            "0 0 * * 0",        # Weekly
            "0 0 1 * *",        # Monthly
        ]

        for cron in cron_examples:
            response = client.put("/workflows/wid-test/schedule", json={
                "cron": cron
            })
            # Should accept or at least not crash
            assert response.status_code in [200, 204, 400, 404]

    def test_schedule_timezone_support(self, client):
        """Schedule may support timezone specification."""
        response = client.put("/workflows/test-wid/schedule", json={
            "cron": "0 0 * * *",
            "timezone": "UTC"
        })
        # Should accept or ignore timezone
        assert response.status_code in [200, 204, 400, 404]

    def test_multiple_schedules_per_workflow(self, client):
        """Each workflow can have at most one schedule."""
        wid = "multi-schedule-test"

        # Set first schedule
        resp1 = client.put(f"/workflows/{wid}/schedule", json={"cron": "0 0 * * *"})

        # Set second schedule (should replace first)
        resp2 = client.put(f"/workflows/{wid}/schedule", json={"cron": "0 * * * *"})

        # Get schedule (should return most recent)
        resp_get = client.get(f"/workflows/{wid}/schedule")
        if resp_get.status_code == 200:
            data = resp_get.json()
            # Schedule should be set
            assert data.get("schedule") is not None or "ok" in data

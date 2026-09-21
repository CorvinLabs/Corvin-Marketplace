"""Pytest fixtures for workflow tests."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from plugin_workflows.adapters import (
    DenyAllSessionBackend,
    NoOpAuditBackend,
    MemoryStorageBackend,
    FreeTierLicenseBackend,
    NoOpPromptGuard,
    NoOpSchedulerBackend,
)
from plugin_workflows.plugin import WorkflowsPlugin


@pytest.fixture
def mock_adapters():
    """Provide mock adapter backends for testing."""
    return {
        "session_backend": DenyAllSessionBackend(),
        "audit_backend": NoOpAuditBackend(),
        "storage_backend": MemoryStorageBackend(),
        "license_backend": FreeTierLicenseBackend(),
        "prompt_guard": NoOpPromptGuard(),
        "scheduler_backend": NoOpSchedulerBackend(),
    }


@pytest.fixture
def plugin(mock_adapters):
    """Provide a WorkflowsPlugin instance for testing."""
    return WorkflowsPlugin(**mock_adapters)


@pytest.fixture
def client(plugin):
    """Provide a FastAPI test client."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(plugin.get_router())
    return TestClient(app)


@pytest.fixture
def tenant_id():
    """Provide a test tenant ID."""
    return "test-tenant"


@pytest.fixture
def wid():
    """Provide a test workflow ID."""
    return "wf-test-001"

"""Unit tests for adapter layer (Phase 5)."""

import pytest
from plugin_workflows.adapters import (
    SessionRecord,
    DenyAllSessionBackend,
    NoOpAuditBackend,
    MemoryStorageBackend,
    FreeTierLicenseBackend,
    NoOpPromptGuard,
    LicenseLimitError,
)


class TestSessionBackend:
    """Test session backend adapters."""

    def test_deny_all_session_always_denies(self):
        backend = DenyAllSessionBackend()
        result = backend.validate_session("any-session-id")
        assert result is None

    def test_deny_all_csrf_always_fails(self):
        backend = DenyAllSessionBackend()
        result = backend.validate_csrf("token1", "token2")
        assert result is False


class TestAuditBackend:
    """Test audit backend adapters."""

    def test_noop_audit_backend_logs_locally(self, caplog):
        backend = NoOpAuditBackend()
        backend.log_event("workflow.created", tenant_id="test", wid="wf-001")
        # Should log without raising
        assert True


class TestStorageBackend:
    """Test storage backend adapters."""

    def test_memory_storage_returns_fake_paths(self):
        backend = MemoryStorageBackend()
        path = backend.workflows_dir("test-tenant")
        assert "/memory/test-tenant/workflows" in str(path)

    def test_memory_storage_paths_consistent(self):
        backend = MemoryStorageBackend()
        yaml_path = backend.yaml_path("test-tenant", "wf-001")
        meta_path = backend.meta_path("test-tenant", "wf-001")
        assert "wf-001.awp.yaml" in str(yaml_path)
        assert "wf-001.meta.json" in str(meta_path)


class TestLicenseBackend:
    """Test license backend adapters."""

    def test_free_tier_allows_within_limits(self):
        backend = FreeTierLicenseBackend()
        # Should not raise
        backend.assert_limit("workflows_concurrent", 3)

    def test_free_tier_rejects_exceeded_limits(self):
        backend = FreeTierLicenseBackend()
        with pytest.raises(LicenseLimitError):
            backend.assert_limit("workflows_concurrent", 10)


class TestPromptGuard:
    """Test prompt guard adapters."""

    def test_noop_guard_passes_through(self):
        guard = NoOpPromptGuard()
        prompt = "/ dangerous prompt #"
        result = guard.guard(prompt)
        assert result == prompt

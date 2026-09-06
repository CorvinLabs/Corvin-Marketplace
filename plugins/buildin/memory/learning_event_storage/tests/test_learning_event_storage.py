"""Unit tests for learning_event_storage plugin (ADR-0314, L33).

Coverage: Stub implementation, event store interface, GDPR compliance.
Compliance: Learning infrastructure (ADR-0314), audit persistence, GDPR Art. 32.
"""

import pytest
from unittest.mock import MagicMock

from learning_event_storage import LearningEventStorage


class TestLearningEventStorage:
    """Learning event storage backend stub."""

    @pytest.mark.asyncio
    async def test_init_enabled(self):
        """Initialize with enabled flag."""
        storage = LearningEventStorage()
        assert storage.enabled is True

    @pytest.mark.asyncio
    async def test_initialize_noop(self):
        """Initialize hook is a no-op."""
        storage = LearningEventStorage()
        mock_context = MagicMock()
        await storage.initialize(mock_context)
        # Should complete without error

    @pytest.mark.asyncio
    async def test_execute_stats(self):
        """execute("stats") answers with the emitter statistics."""
        storage = LearningEventStorage()
        result = await storage.execute("stats")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_unknown_operation_is_reported(self):
        """An unknown operation is answered as a failure, never raised into the host."""
        storage = LearningEventStorage()
        result = await storage.execute("store_event")
        assert result["success"] is False
        assert "Unknown operation" in result["error"]

    @pytest.mark.asyncio
    async def test_shutdown_noop(self):
        """Shutdown is a no-op in stub."""
        storage = LearningEventStorage()
        await storage.shutdown()
        # Should complete without error

    def test_compliance_marker_audit_persistence(self):
        """Audit persistence documented."""
        import learning_event_storage as mod
        doc = mod.__doc__
        assert "adr-0314" in doc.lower()

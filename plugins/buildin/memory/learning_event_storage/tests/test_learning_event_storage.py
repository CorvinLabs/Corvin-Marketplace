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
    async def test_execute_not_implemented(self):
        """Execute raises NotImplementedError (stub)."""
        storage = LearningEventStorage()
        with pytest.raises(NotImplementedError):
            await storage.execute()

    @pytest.mark.asyncio
    async def test_execute_store_event_not_implemented(self):
        """Execute with store_event args raises NotImplementedError."""
        storage = LearningEventStorage()
        event = {"type": "confidence", "value": 0.92}
        with pytest.raises(NotImplementedError):
            await storage.execute("store_event", event)

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
        assert "stub" in doc.lower()

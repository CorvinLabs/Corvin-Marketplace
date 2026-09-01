"""Unit tests for cel_session_memory plugin (ADR-0316, L28).

Coverage: Stub implementation validation, initialization, NotImplementedError path.
Compliance: Decision history layer (ADR-0316), GDPR Art. 30.
"""

import pytest
from unittest.mock import MagicMock

from cel_session_memory import CELSessionMemory


class TestCELSessionMemory:
    """CEL session memory provider stub."""

    @pytest.mark.asyncio
    async def test_init_state(self):
        """Initialize with enabled flag."""
        memory = CELSessionMemory()
        assert memory.enabled is True

    @pytest.mark.asyncio
    async def test_initialize_noop(self):
        """Initialize is a no-op in stub."""
        memory = CELSessionMemory()
        mock_context = MagicMock()
        # Should not raise
        await memory.initialize(mock_context)

    @pytest.mark.asyncio
    async def test_execute_not_implemented(self):
        """Execute raises NotImplementedError (stub)."""
        memory = CELSessionMemory()
        with pytest.raises(NotImplementedError):
            await memory.execute()

    @pytest.mark.asyncio
    async def test_execute_with_args_not_implemented(self):
        """Execute with arguments raises NotImplementedError."""
        memory = CELSessionMemory()
        with pytest.raises(NotImplementedError):
            await memory.execute("query", context="value")

    @pytest.mark.asyncio
    async def test_shutdown_noop(self):
        """Shutdown is a no-op in stub."""
        memory = CELSessionMemory()
        # Should not raise
        await memory.shutdown()

    def test_compliance_marker_decision_history(self):
        """Decision history layer documented."""
        import cel_session_memory as mod
        doc = mod.__doc__
        assert "stub" in doc.lower()

"""Unit tests for user_model_learner plugin (ADR-0318, L28).

Coverage: Stub implementation, user model interface.
Compliance: User model learning (ADR-0318), learning infrastructure, GDPR Art. 30.
"""

import pytest
from unittest.mock import MagicMock

from user_model_learner import UserModelLearner


class TestUserModelLearner:
    """User model learner stub implementation."""

    @pytest.mark.asyncio
    async def test_init_enabled(self):
        """Initialize with enabled flag."""
        learner = UserModelLearner()
        assert learner.enabled is True

    @pytest.mark.asyncio
    async def test_initialize_noop(self):
        """Initialize is a no-op in stub."""
        learner = UserModelLearner()
        mock_context = MagicMock()
        await learner.initialize(mock_context)

    @pytest.mark.asyncio
    async def test_execute_not_implemented(self):
        """Execute raises NotImplementedError."""
        learner = UserModelLearner()
        with pytest.raises(NotImplementedError):
            await learner.execute()

    @pytest.mark.asyncio
    async def test_execute_with_args_not_implemented(self):
        """Execute with arguments raises NotImplementedError."""
        learner = UserModelLearner()
        with pytest.raises(NotImplementedError):
            await learner.execute("learn_preference", {"pref": "value"})

    @pytest.mark.asyncio
    async def test_shutdown_noop(self):
        """Shutdown is a no-op."""
        learner = UserModelLearner()
        await learner.shutdown()

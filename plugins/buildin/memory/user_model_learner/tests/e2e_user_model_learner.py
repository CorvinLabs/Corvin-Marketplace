"""E2E test for user_model_learner plugin."""
import pytest
from user_model_learner import UserModelLearner

@pytest.mark.asyncio
async def test_e2e_user_model_learner_stub():
    """E2E: Learner stub raises NotImplementedError."""
    learner = UserModelLearner()
    await learner.initialize({})
    with pytest.raises(NotImplementedError):
        await learner.execute("learn")
    await learner.shutdown()

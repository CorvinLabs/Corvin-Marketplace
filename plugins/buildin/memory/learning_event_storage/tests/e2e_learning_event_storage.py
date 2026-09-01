"""E2E test for learning_event_storage plugin."""
import pytest
from learning_event_storage import LearningEventStorage

@pytest.mark.asyncio
async def test_e2e_learning_event_storage_stub():
    """E2E: Stub storage raises NotImplementedError."""
    storage = LearningEventStorage()
    await storage.initialize({})
    with pytest.raises(NotImplementedError):
        await storage.execute("store")
    await storage.shutdown()

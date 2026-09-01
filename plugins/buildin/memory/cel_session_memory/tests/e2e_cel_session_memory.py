"""E2E test for cel_session_memory plugin."""
import pytest
from cel_session_memory import CELSessionMemory

@pytest.mark.asyncio
async def test_e2e_cel_session_memory_stub():
    """E2E: Stub raises NotImplementedError."""
    memory = CELSessionMemory()
    await memory.initialize({})
    with pytest.raises(NotImplementedError):
        await memory.execute("store")
    await memory.shutdown()

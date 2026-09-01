"""E2E test for vibe_session_history plugin."""
import pytest
from vibe_session_history import VibeSessionHistory

@pytest.mark.asyncio
async def test_e2e_vibe_session_history_recording():
    """E2E: Session history records events."""
    history = VibeSessionHistory()
    await history.initialize({})
    await history.on_vibe_session_event({"type": "decided"})
    await history.on_brain_metric({"outcome": "success"})
    diags = await history.get_diagnostics()
    assert diags["events_collected"] == 2
    await history.shutdown()

"""E2E test for brain_learning_tracker plugin."""
import pytest
from brain_learning_tracker import BrainLearningTracker

@pytest.mark.asyncio
async def test_e2e_brain_learning_tracker_lifecycle():
    """E2E: Tracker records learning events."""
    tracker = BrainLearningTracker()
    await tracker.initialize({})
    await tracker.on_vibe_session_event({"type": "decided"})
    await tracker.on_brain_metric({"metric": "score"})
    diags = await tracker.get_diagnostics()
    assert diags["events_collected"] == 2
    await tracker.shutdown()

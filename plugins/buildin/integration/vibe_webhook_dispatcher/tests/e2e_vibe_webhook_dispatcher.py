"""E2E test for vibe_webhook_dispatcher plugin."""
import pytest
import asyncio
from vibe_webhook_dispatcher import VibeWebhookDispatcher

@pytest.mark.asyncio
async def test_e2e_vibe_webhook_dispatcher_event_collection():
    """E2E: Dispatcher collects and reports events."""
    dispatcher = VibeWebhookDispatcher()
    ctx = {}
    await dispatcher.initialize(ctx)
    
    await dispatcher.on_vibe_session_event({"type": "start"})
    await dispatcher.on_brain_metric({"metric": "latency"})
    
    diags = await dispatcher.get_diagnostics()
    assert diags["events_collected"] == 2
    assert diags["status"] == "operational"
    await dispatcher.shutdown()

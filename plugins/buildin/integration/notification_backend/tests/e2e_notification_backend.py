"""E2E test for notification_backend plugin."""

import pytest
import logging
from unittest.mock import patch
from notification_backend import get_active, set_active, release_owned_by

@pytest.mark.asyncio
async def test_e2e_notification_backend_lifecycle():
    """E2E: Custom notification backend lifecycle."""
    class TestNotificationBackend:
        def notify(self, event, payload, *, tenant_id="_default", severity="info"):
            return {"sent": True, "event": event}

    backend = TestNotificationBackend()

    with patch("loading.current") as mock_current:
        mock_current.return_value.plugin_id = "notify-plugin"
        set_active(backend)

    active = get_active()
    assert active is backend
    result = active.notify("test.event", {})
    assert result["sent"] is True

    assert release_owned_by("notify-plugin")

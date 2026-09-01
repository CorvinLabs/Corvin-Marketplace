"""E2E test for router_backend plugin."""

import pytest
from unittest.mock import patch
from router_backend import get_active, set_active, release_owned_by

@pytest.mark.asyncio
async def test_e2e_router_backend_custom_impl():
    """E2E: Custom router backend replaces default."""
    class CustomRouter:
        def route(self, text, personas, *, model="", mode="heuristic", tenant_id="_default", **kwargs):
            return {"selected": personas[0] if personas else None, "confidence": 0.99}

    router = CustomRouter()

    with patch("loading.current") as mock_current:
        mock_current.return_value.plugin_id = "router-plugin"
        set_active(router)

    active = get_active()
    result = active.route("test", [{"id": "p1"}, {"id": "p2"}])
    assert result["confidence"] == 0.99
    assert release_owned_by("router-plugin")

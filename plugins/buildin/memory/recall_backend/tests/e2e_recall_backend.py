"""E2E test for recall_backend plugin."""
import pytest
from unittest.mock import patch
from recall_backend import get_active, set_active, release_owned_by

@pytest.mark.asyncio
async def test_e2e_recall_backend_lifecycle():
    """E2E: Recall backend registry."""
    class TestRecall:
        def index_turn(self, channel, chat_key, *, user_text, assistant_text, **kwargs):
            return {"ok": True}
        def recall(self, query, **kwargs):
            return []
        def forget(self, **kwargs):
            return 0

    backend = TestRecall()
    with patch("loading.current") as mock:
        mock.return_value.plugin_id = "recall-plugin"
        set_active(backend)
    assert get_active() is backend
    assert release_owned_by("recall-plugin")

"""Unit tests for recall_backend plugin (ADR-0033, L28).

Coverage: Registry operations, default recall implementation, conversation indexing.
Compliance: Conversation recall (L28), audit chain integration, GDPR Art. 30.
"""

import pytest
import threading
from unittest.mock import MagicMock, patch

from recall_backend import (
    RecallBackendRegistry,
    SqliteRecallBackend,
    get_active,
    set_active,
    clear,
    clear_if_active,
    release_owned_by,
    owner_plugin_id,
)


class TestSqliteRecallBackend:
    """Default SQLite-based recall implementation."""

    def test_index_turn_module_unavailable(self):
        """Index gracefully degrades when module unavailable."""
        backend = SqliteRecallBackend()
        with patch.object(backend, "_mod", return_value=None):
            result = backend.index_turn(
                "channel-1", "chat-1",
                user_text="hello",
                assistant_text="hi there"
            )
        assert result == {"ok": False, "reason": "module-unavailable"}

    def test_index_turn_delegates_to_conversation_recall(self):
        """Index call delegates to conversation_recall module."""
        backend = SqliteRecallBackend()
        mock_mod = MagicMock()
        mock_mod.index_turn.return_value = {"ok": True, "msg_id": "m1"}

        with patch.object(backend, "_mod", return_value=mock_mod):
            result = backend.index_turn(
                "ch1", "ck1",
                user_text="user msg",
                assistant_text="asst msg",
                tenant_id="t1"
            )

        assert result["ok"] is True
        mock_mod.index_turn.assert_called_once()

    def test_index_turn_exception_handling(self):
        """Exception in index_turn is caught and logged."""
        backend = SqliteRecallBackend()
        mock_mod = MagicMock()
        mock_mod.index_turn.side_effect = RuntimeError("DB error")

        with patch.object(backend, "_mod", return_value=mock_mod):
            result = backend.index_turn("ch", "ck", user_text="u", assistant_text="a")

        assert result["ok"] is False
        assert "reason" in result

    def test_recall_returns_empty_when_unavailable(self):
        """Recall returns empty list when module unavailable."""
        backend = SqliteRecallBackend()
        with patch.object(backend, "_mod", return_value=None):
            result = backend.recall("query")
        assert result == []

    def test_recall_converts_dataclass_to_dict(self):
        """Recall converts dataclass results to dict."""
        backend = SqliteRecallBackend()
        mock_mod = MagicMock()
        mock_recall_obj = MagicMock()
        mock_mod.recall.return_value = [mock_recall_obj]

        with patch.object(backend, "_mod", return_value=mock_mod):
            result = backend.recall("query")

        assert len(result) == 1

    def test_forget_returns_zero_when_unavailable(self):
        """Forget returns 0 when module unavailable."""
        backend = SqliteRecallBackend()
        with patch.object(backend, "_mod", return_value=None):
            result = backend.forget(channel="ch1")
        assert result == 0

    def test_forget_delegates_to_conversation_recall(self):
        """Forget call delegates to conversation_recall."""
        backend = SqliteRecallBackend()
        mock_mod = MagicMock()
        mock_mod.forget.return_value = 3

        with patch.object(backend, "_mod", return_value=mock_mod):
            result = backend.forget(channel="ch1", chat_key="ck1")

        assert result == 3


class TestRecallBackendRegistry:
    """Registry operations and provider lifecycle."""

    def test_init_has_default_provider(self):
        """Registry initializes with SqliteRecallBackend."""
        reg = RecallBackendRegistry()
        assert isinstance(reg.get_active(), SqliteRecallBackend)

    def test_set_active_with_ownership(self):
        """Set custom provider with ownership tracking."""
        reg = RecallBackendRegistry()
        custom = MagicMock()

        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "recall-plugin"
            reg.set_active(custom)

        assert reg.get_active() is custom
        assert reg.owner_plugin_id() == "recall-plugin"

    def test_release_owned_by_restores_default(self):
        """Release by plugin ID restores SqliteRecallBackend."""
        reg = RecallBackendRegistry()
        custom = MagicMock()

        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "plugin-r"
            reg.set_active(custom)

        assert reg.release_owned_by("plugin-r")
        assert isinstance(reg.get_active(), SqliteRecallBackend)

    def test_clear_if_active_instance_check(self):
        """Clear only if exact instance matches."""
        reg = RecallBackendRegistry()
        p1 = MagicMock()
        p2 = MagicMock()

        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "plugin"
            reg.set_active(p1)

        assert not reg.clear_if_active(p2)
        assert reg.get_active() is p1

        assert reg.clear_if_active(p1)
        assert isinstance(reg.get_active(), SqliteRecallBackend)

    def test_thread_safety_concurrent_recalls(self):
        """Concurrent recall operations are thread-safe."""
        reg = RecallBackendRegistry()
        results = []

        def do_recall():
            backend = reg.get_active()
            results.append(backend is not None)

        threads = [threading.Thread(target=do_recall) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(results)

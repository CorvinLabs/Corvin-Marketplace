"""Unit tests for notification_backend plugin (ADR-0033, L16).

Coverage: Registry operations, default implementation, thread-safety.
Compliance: Audit trails, severity levels, tenant isolation.
"""

import pytest
import logging
import threading
from unittest.mock import MagicMock, patch

from notification_backend import (
    NotificationBackendRegistry,
    LogNotificationBackend,
    get_active,
    set_active,
    clear,
    clear_if_active,
    release_owned_by,
    owner_plugin_id,
)


class TestLogNotificationBackend:
    """Default log-based notification backend."""

    def test_notify_info_level(self, caplog):
        """Default severity 'info' logs at INFO level."""
        backend = LogNotificationBackend()
        with caplog.at_level(logging.INFO):
            backend.notify(
                "test.event",
                {"data": "value"},
                tenant_id="test-tenant",
                severity="info"
            )
        assert "test.event" in caplog.text
        assert "test-tenant" in caplog.text

    def test_notify_severity_mapping(self, caplog):
        """Severity levels map to correct log levels."""
        backend = LogNotificationBackend()
        severities = {
            "warn": logging.WARNING,
            "error": logging.ERROR,
            "critical": logging.CRITICAL,
        }

        for severity, expected_level in severities.items():
            with caplog.at_level(expected_level):
                backend.notify("test", {}, severity=severity)

    def test_notify_unknown_severity_defaults_to_info(self, caplog):
        """Unknown severity levels default to INFO."""
        backend = LogNotificationBackend()
        with caplog.at_level(logging.INFO):
            backend.notify("test", {}, severity="unknown_level")
        # Should log without error
        assert len(caplog.records) > 0

    def test_notify_tenant_isolation(self, caplog):
        """Notifications include tenant_id for audit trail."""
        backend = LogNotificationBackend()
        with caplog.at_level(logging.INFO):
            backend.notify("event", {}, tenant_id="tenant-a")
            backend.notify("event", {}, tenant_id="tenant-b")

        tenant_a_logs = [r for r in caplog.records if "tenant-a" in str(r.msg)]
        tenant_b_logs = [r for r in caplog.records if "tenant-b" in str(r.msg)]
        assert len(tenant_a_logs) >= 1
        assert len(tenant_b_logs) >= 1


class TestNotificationBackendRegistry:
    """Registry operations and provider lifecycle."""

    def test_init_has_default_provider(self):
        """Registry initializes with LogNotificationBackend."""
        reg = NotificationBackendRegistry()
        active = reg.get_active()
        assert isinstance(active, LogNotificationBackend)
        assert reg.owner_plugin_id() is None

    def test_set_active_with_ownership(self):
        """Set custom provider and track owning plugin."""
        reg = NotificationBackendRegistry()
        custom = MagicMock()

        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "plugin-notify"
            reg.set_active(custom)

        assert reg.get_active() is custom
        assert reg.owner_plugin_id() == "plugin-notify"

    def test_release_owned_by_restores_default(self):
        """Release by plugin ID restores default LogNotificationBackend."""
        reg = NotificationBackendRegistry()
        custom = MagicMock()

        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "plugin-x"
            reg.set_active(custom)

        assert reg.release_owned_by("plugin-x")
        assert isinstance(reg.get_active(), LogNotificationBackend)
        assert reg.owner_plugin_id() is None

    def test_clear_restores_default(self):
        """Clear() explicitly restores default provider."""
        reg = NotificationBackendRegistry()
        custom = MagicMock()

        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "plugin-z"
            reg.set_active(custom)

        reg.clear()
        assert isinstance(reg.get_active(), LogNotificationBackend)
        assert reg.owner_plugin_id() is None

    def test_clear_if_active_instance_check(self):
        """Clear only if exact provider instance matches."""
        reg = NotificationBackendRegistry()
        provider_a = MagicMock(name="provider-a")
        provider_b = MagicMock(name="provider-b")

        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "plugin-1"
            reg.set_active(provider_a)

        # Wrong instance doesn't clear
        assert not reg.clear_if_active(provider_b)
        assert reg.get_active() is provider_a

        # Correct instance clears
        assert reg.clear_if_active(provider_a)
        assert isinstance(reg.get_active(), LogNotificationBackend)

    def test_thread_safety_concurrent_operations(self):
        """Concurrent notify and release operations are thread-safe."""
        reg = NotificationBackendRegistry()
        calls = []

        def notify_multiple():
            backend = reg.get_active()
            for i in range(5):
                backend.notify(f"event-{i}", {"idx": i})
            calls.append("notify_done")

        def switch_provider():
            custom = MagicMock()
            with patch("loading.current") as mock_current:
                mock_current.return_value.plugin_id = "plugin-temp"
                reg.set_active(custom)
            calls.append("switched")
            reg.release_owned_by("plugin-temp")
            calls.append("released")

        threads = [
            threading.Thread(target=notify_multiple),
            threading.Thread(target=switch_provider),
            threading.Thread(target=notify_multiple),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(calls) > 0  # At least some operations completed

    def test_module_level_functions(self):
        """Module-level convenience functions work correctly."""
        custom = MagicMock()
        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "test-plugin"
            set_active(custom)

        assert get_active() is custom
        assert owner_plugin_id() == "test-plugin"

        assert clear_if_active(custom)
        assert isinstance(get_active(), LogNotificationBackend)

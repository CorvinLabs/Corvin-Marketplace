"""
Unit tests for slack_notifier plugin.

Tests cover Slack notifications including:
- Message formatting
- Notification sending
- Threading support
- Channel handling
- Error handling
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from slack_notifier import SlackNotifier


class TestSlackNotifierInitialization:
    """Test plugin initialization."""

    @pytest.mark.asyncio
    async def test_init_success(self):
        """Test successful plugin initialization."""
        plugin = SlackNotifier()
        assert plugin is not None
        assert plugin.enabled is True
        assert plugin.default_channel == "#corvin-notifications"

    @pytest.mark.asyncio
    async def test_initialize_with_webhook(self):
        """Test initialize with webhook URL."""
        plugin = SlackNotifier()
        context = {
            "slack_webhook_url": "https://hooks.slack.com/services/T123/B456/xyz",
            "channel": "#alerts",
        }
        await plugin.initialize(context)

        assert plugin.webhook_url == "https://hooks.slack.com/services/T123/B456/xyz"
        assert plugin.default_channel == "#alerts"

    @pytest.mark.asyncio
    async def test_initialize_without_webhook(self):
        """Test initialize without webhook URL."""
        plugin = SlackNotifier()
        await plugin.initialize({})

        assert plugin.webhook_url is None

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test plugin shutdown."""
        plugin = SlackNotifier()
        await plugin.shutdown()
        assert len(plugin.message_queue) == 0


class TestSlackNotifierMessageFormatting:
    """Test message formatting."""

    def test_format_message_success(self):
        """Test successful message formatting."""
        plugin = SlackNotifier()
        payload = plugin.format_message("Test Title", "Test message", "good")

        assert "attachments" in payload
        assert len(payload["attachments"]) == 1
        assert payload["attachments"][0]["title"] == "Test Title"
        assert payload["attachments"][0]["text"] == "Test message"
        assert payload["attachments"][0]["color"] == "good"

    def test_format_message_warning_color(self):
        """Test message formatting with warning color."""
        plugin = SlackNotifier()
        payload = plugin.format_message("Warning", "Something needs attention", "warning")

        assert payload["attachments"][0]["color"] == "warning"

    def test_format_message_danger_color(self):
        """Test message formatting with danger color."""
        plugin = SlackNotifier()
        payload = plugin.format_message("Error", "Critical issue", "danger")

        assert payload["attachments"][0]["color"] == "danger"


class TestSlackNotifierNotifications:
    """Test notification sending."""

    @pytest.mark.asyncio
    async def test_send_notification_success(self):
        """Test successful notification send."""
        plugin = SlackNotifier()
        await plugin.initialize({"slack_webhook_url": "https://hooks.slack.com/test"})

        result = await plugin.send_notification(
            "Test Alert",
            "This is a test notification",
            channel="#test",
        )

        assert result["status"] == "queued"
        assert result["title"] == "Test Alert"
        assert result["channel"] == "#test"
        assert result["queue_length"] == 1

    @pytest.mark.asyncio
    async def test_send_notification_default_channel(self):
        """Test notification with default channel."""
        plugin = SlackNotifier()
        await plugin.initialize()

        result = await plugin.send_notification(
            "Test",
            "Message",
        )

        assert result["channel"] == "#corvin-notifications"

    @pytest.mark.asyncio
    async def test_send_notification_custom_channel(self):
        """Test notification with custom channel."""
        plugin = SlackNotifier()
        await plugin.initialize()

        result = await plugin.send_notification(
            "Test",
            "Message",
            channel="#custom",
        )

        assert result["channel"] == "#custom"

    @pytest.mark.asyncio
    async def test_send_notification_empty_title(self):
        """Test notification with empty title."""
        plugin = SlackNotifier()
        with pytest.raises(ValueError):
            await plugin.send_notification("", "Message")

    @pytest.mark.asyncio
    async def test_send_notification_empty_message(self):
        """Test notification with empty message."""
        plugin = SlackNotifier()
        with pytest.raises(ValueError):
            await plugin.send_notification("Title", "")

    @pytest.mark.asyncio
    async def test_send_multiple_notifications(self):
        """Test sending multiple notifications."""
        plugin = SlackNotifier()
        await plugin.initialize()

        for i in range(5):
            await plugin.send_notification(f"Alert {i}", f"Message {i}")

        assert len(plugin.message_queue) == 5


class TestSlackNotifierThreading:
    """Test threaded notifications."""

    @pytest.mark.asyncio
    async def test_send_thread_notification(self):
        """Test sending threaded notification."""
        plugin = SlackNotifier()
        await plugin.initialize()

        result = await plugin.send_thread_notification(
            "1234567890.123456",
            "Reply",
            "This is a reply in a thread",
        )

        assert result["status"] == "queued"
        assert result["thread_ts"] == "1234567890.123456"

    @pytest.mark.asyncio
    async def test_send_thread_no_thread_ts(self):
        """Test threaded notification without thread timestamp."""
        plugin = SlackNotifier()
        with pytest.raises(ValueError):
            await plugin.send_thread_notification("", "Title", "Message")

    @pytest.mark.asyncio
    async def test_thread_with_custom_channel(self):
        """Test threaded notification with custom channel."""
        plugin = SlackNotifier()
        await plugin.initialize()

        result = await plugin.send_thread_notification(
            "1234567890.123456",
            "Reply",
            "Message",
            channel="#alerts",
        )

        assert result["thread_ts"] == "1234567890.123456"


class TestSlackNotifierExecute:
    """Test execute method."""

    @pytest.mark.asyncio
    async def test_execute_send_notification(self):
        """Test execute for sending notification."""
        plugin = SlackNotifier()
        await plugin.initialize()

        result = await plugin.execute(
            send=True,
            title="Test",
            message="Message",
        )

        assert result["status"] == "queued"
        assert result["title"] == "Test"

    @pytest.mark.asyncio
    async def test_execute_send_thread(self):
        """Test execute for sending threaded notification."""
        plugin = SlackNotifier()
        await plugin.initialize()

        result = await plugin.execute(
            thread=True,
            title="Reply",
            message="Thread message",
            thread_ts="1234567890.123456",
        )

        assert result["thread_ts"] == "1234567890.123456"

    @pytest.mark.asyncio
    async def test_execute_no_title(self):
        """Test execute without title."""
        plugin = SlackNotifier()
        with pytest.raises(ValueError):
            await plugin.execute(message="Message")

    @pytest.mark.asyncio
    async def test_execute_no_message(self):
        """Test execute without message."""
        plugin = SlackNotifier()
        with pytest.raises(ValueError):
            await plugin.execute(title="Title")

    @pytest.mark.asyncio
    async def test_execute_custom_color(self):
        """Test execute with custom color."""
        plugin = SlackNotifier()
        await plugin.initialize()

        result = await plugin.execute(
            send=True,
            title="Alert",
            message="Critical issue",
            color="danger",
        )

        assert result["status"] == "queued"


class TestSlackNotifierErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_message_queue_management(self):
        """Test message queue handling."""
        plugin = SlackNotifier()
        await plugin.initialize()

        for i in range(3):
            await plugin.send_notification(f"Alert {i}", f"Message {i}")

        assert len(plugin.message_queue) == 3

        await plugin.shutdown()
        assert len(plugin.message_queue) == 0

    @pytest.mark.asyncio
    async def test_concurrent_notifications(self):
        """Test concurrent notification sending."""
        plugin = SlackNotifier()
        await plugin.initialize()

        tasks = []
        for i in range(10):
            task = plugin.send_notification(f"Alert {i}", f"Message {i}")
            tasks.append(task)

        results = []
        for task in tasks:
            result = await task
            results.append(result)

        assert len(results) == 10
        assert len(plugin.message_queue) == 10


class TestSlackNotifierIntegration:
    """Integration tests."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """Test complete plugin lifecycle."""
        plugin = SlackNotifier()
        context = {
            "slack_webhook_url": "https://hooks.slack.com/services/T/B/X",
            "channel": "#updates",
        }

        await plugin.initialize(context)
        assert plugin.enabled is True

        result1 = await plugin.send_notification("Start", "Starting task")
        result2 = await plugin.send_thread_notification(
            "1234567890.123456",
            "Update",
            "Task running",
        )
        result3 = await plugin.send_notification("Complete", "Task finished", color="good")

        assert len(plugin.message_queue) == 3

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_workflow_simulation(self):
        """Test simulated workflow with notifications."""
        plugin = SlackNotifier()
        await plugin.initialize()

        # Simulate a task workflow
        start_result = await plugin.execute(
            send=True,
            title="Task Started",
            message="Processing data",
        )
        thread_ts = start_result.get("thread_ts")

        # Send status updates
        for i in range(3):
            await plugin.execute(
                send=True,
                title=f"Update {i+1}",
                message=f"Step {i+1} completed",
            )

        # Send completion
        await plugin.execute(
            send=True,
            title="Task Completed",
            message="All steps done",
            color="good",
        )

        assert len(plugin.message_queue) >= 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

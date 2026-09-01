"""
End-to-end tests for slack_notifier plugin.

Tests real plugin initialization, Slack integration, and notification workflows.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from slack_notifier import SlackNotifier


class TestSlackNotifierE2E:
    """End-to-end tests for Slack Notifier."""

    @pytest.mark.asyncio
    async def test_e2e_basic_notification(self):
        """E2E test: Send basic notification."""
        plugin = SlackNotifier()
        context = {
            "slack_webhook_url": "https://hooks.slack.com/services/T123/B456/xyz",
            "channel": "#notifications",
        }
        await plugin.initialize(context)

        # Send notification
        result = await plugin.send_notification(
            "Deployment Complete",
            "Version 1.2.0 deployed successfully",
            color="good",
        )

        # Verify
        assert result["status"] == "queued"
        assert result["title"] == "Deployment Complete"
        assert result["channel"] == "#notifications"

        # Cleanup
        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_notification_with_channels(self):
        """E2E test: Send notifications to different channels."""
        plugin = SlackNotifier()
        await plugin.initialize({"slack_webhook_url": "https://hooks.slack.com/test"})

        channels = ["#alerts", "#notifications", "#updates"]

        for i, channel in enumerate(channels):
            result = await plugin.send_notification(
                f"Alert {i+1}",
                f"Message to {channel}",
                channel=channel,
            )
            assert result["channel"] == channel

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_threaded_conversation(self):
        """E2E test: Send notification then reply in thread."""
        plugin = SlackNotifier()
        await plugin.initialize({"slack_webhook_url": "https://hooks.slack.com/test"})

        # Original message
        original = await plugin.send_notification(
            "Task Started",
            "Processing data...",
        )

        # Mock thread_ts (in real scenario, this comes from Slack response)
        thread_ts = "1234567890.123456"

        # Reply in thread
        reply = await plugin.send_thread_notification(
            thread_ts,
            "Update",
            "Still processing...",
        )

        assert reply["thread_ts"] == thread_ts
        assert len(plugin.message_queue) == 2

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_workflow_notifications(self):
        """E2E test: Simulate workflow notifications."""
        plugin = SlackNotifier()
        await plugin.initialize()

        # Workflow: Start -> Steps -> Complete

        # Step 1: Notify start
        await plugin.send_notification(
            "Workflow Started",
            "Processing batch import...",
            channel="#workflows",
            color="good",
        )

        # Step 2: Process updates
        for i in range(3):
            await plugin.send_notification(
                f"Step {i+1} Complete",
                f"Processed {(i+1)*100} records",
                channel="#workflows",
                color="good",
            )

        # Step 3: Notify completion
        await plugin.send_notification(
            "Workflow Complete",
            "All 300 records imported successfully",
            channel="#workflows",
            color="good",
        )

        # Verify
        assert len(plugin.message_queue) == 5

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_alert_escalation(self):
        """E2E test: Escalate alert through colors."""
        plugin = SlackNotifier()
        await plugin.initialize()

        alert_lifecycle = [
            ("Alert", "CPU usage at 60%", "warning"),
            ("Alert Escalated", "CPU usage at 80%", "danger"),
            ("Alert Resolved", "CPU usage back to normal", "good"),
        ]

        for title, message, color in alert_lifecycle:
            result = await plugin.send_notification(
                title,
                message,
                channel="#alerts",
                color=color,
            )
            assert result["status"] == "queued"

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_multi_channel_broadcast(self):
        """E2E test: Broadcast message to multiple channels."""
        plugin = SlackNotifier()
        await plugin.initialize()

        message_title = "Important Announcement"
        message_body = "Maintenance scheduled for tonight"

        channels = ["#engineering", "#devops", "#notifications", "#general"]

        for channel in channels:
            await plugin.send_notification(
                message_title,
                message_body,
                channel=channel,
                color="warning",
            )

        assert len(plugin.message_queue) == len(channels)

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_format_variations(self):
        """E2E test: Different message formatting options."""
        plugin = SlackNotifier()
        await plugin.initialize()

        # Test different colors
        colors = ["good", "warning", "danger"]

        for i, color in enumerate(colors):
            result = await plugin.send_notification(
                f"Test {i+1}",
                f"Message with {color} color",
                color=color,
            )
            assert result["status"] == "queued"

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_execute_interface(self):
        """E2E test: Using execute() method."""
        plugin = SlackNotifier()
        await plugin.initialize()

        # Send via execute
        result = await plugin.execute(
            send=True,
            title="Automated Alert",
            message="System check passed",
            color="good",
        )

        assert result["status"] == "queued"

        # Send thread via execute
        thread_result = await plugin.execute(
            thread=True,
            title="Reply",
            message="Got your message",
            thread_ts="1234567890.123456",
        )

        assert thread_result["thread_ts"] == "1234567890.123456"

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_error_recovery(self):
        """E2E test: Error handling and recovery."""
        plugin = SlackNotifier()
        await plugin.initialize()

        # Try invalid notification (should fail)
        try:
            await plugin.send_notification("", "Message")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass  # Expected

        # Continue with valid notification
        result = await plugin.send_notification(
            "Recovery Test",
            "Plugin recovered from error",
        )
        assert result["status"] == "queued"

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_production_scenario(self):
        """E2E test: Realistic production scenario."""
        plugin = SlackNotifier()
        context = {
            "slack_webhook_url": "https://hooks.slack.com/services/T/B/X",
            "channel": "#deployments",
        }
        await plugin.initialize(context)

        # Simulate deployment workflow
        stages = [
            ("Deployment Starting", "Rolling out v2.0.0", "warning"),
            ("Build Successful", "Docker image built", "good"),
            ("Staging Tests Passed", "All tests passed", "good"),
            ("Deployment Complete", "v2.0.0 live in production", "good"),
        ]

        for stage, message, color in stages:
            result = await plugin.send_notification(
                stage,
                message,
                color=color,
            )
            assert result["status"] == "queued"

        await plugin.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

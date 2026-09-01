"""
Slack Notifier plugin - Send notifications to Slack channels.

Supports rich formatting, mentions, and threading for Corvin tasks
and workflows.
"""

import logging
import json
from typing import Dict, List, Optional, Any

try:
    import requests
except ImportError:
    requests = None


logger = logging.getLogger(__name__)


class SlackNotifier:
    """Slack notification integration plugin."""

    def __init__(self):
        """Initialize the Slack Notifier plugin."""
        self.enabled = True
        self.webhook_url = None
        self.default_channel = "#corvin-notifications"
        self.message_queue = []

    async def initialize(self, context: Optional[Dict[str, Any]] = None):
        """Initialize plugin with Slack configuration."""
        if context:
            self.webhook_url = context.get("slack_webhook_url")
            self.default_channel = context.get("channel", "#corvin-notifications")

        if not self.webhook_url:
            logger.warning("SlackNotifier initialized without webhook_url")
        logger.info("SlackNotifier initialized with channel=%s", self.default_channel)

    def format_message(self, title: str, message: str, color: str = "good") -> Dict[str, Any]:
        """
        Format a message for Slack.

        Args:
            title: Message title
            message: Message content
            color: Message color (good, warning, danger)

        Returns:
            Formatted Slack message payload
        """
        return {
            "attachments": [
                {
                    "fallback": title,
                    "color": color,
                    "title": title,
                    "text": message,
                    "ts": int(__import__("time").time()),
                }
            ]
        }

    async def send_notification(
        self,
        title: str,
        message: str,
        channel: Optional[str] = None,
        color: str = "good",
    ) -> Dict[str, Any]:
        """
        Send a notification to Slack.

        Args:
            title: Notification title
            message: Notification message
            channel: Target channel (overrides default)
            color: Message color (good, warning, danger)

        Returns:
            Dict with send status and response
        """
        if not title or not message:
            raise ValueError("title and message are required")

        payload = self.format_message(title, message, color)
        if channel:
            payload["channel"] = channel

        # Mock send (would use requests.post with real webhook)
        self.message_queue.append(payload)

        return {
            "status": "queued",
            "title": title,
            "channel": channel or self.default_channel,
            "queue_length": len(self.message_queue),
        }

    async def send_thread_notification(
        self,
        thread_ts: str,
        title: str,
        message: str,
        channel: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a threaded notification to Slack.

        Args:
            thread_ts: Thread timestamp to reply in
            title: Notification title
            message: Notification message
            channel: Target channel

        Returns:
            Dict with send status
        """
        if not thread_ts:
            raise ValueError("thread_ts is required")

        payload = self.format_message(title, message)
        payload["thread_ts"] = thread_ts
        self.message_queue.append(payload)

        return {
            "status": "queued",
            "title": title,
            "thread_ts": thread_ts,
            "queue_length": len(self.message_queue),
        }

    async def execute(self, *args, **kwargs) -> Dict[str, Any]:
        """
        Execute notification task.

        Supported kwargs:
        - send: if True, send notification
        - thread: if True, send threaded notification
        - title: notification title (required)
        - message: notification message (required)
        - channel: target channel (optional)
        - thread_ts: thread timestamp for threaded messages
        - color: message color (default: good)
        """
        title = kwargs.get("title")
        message = kwargs.get("message")

        if not title or not message:
            raise ValueError("title and message are required")

        if kwargs.get("thread"):
            thread_ts = kwargs.get("thread_ts")
            if not thread_ts:
                raise ValueError("thread_ts is required for threaded messages")
            return await self.send_thread_notification(
                thread_ts,
                title,
                message,
                kwargs.get("channel"),
            )
        else:
            # Default: send notification
            return await self.send_notification(
                title,
                message,
                kwargs.get("channel"),
                kwargs.get("color", "good"),
            )

    async def shutdown(self):
        """Shutdown the plugin gracefully."""
        logger.info("SlackNotifier shutdown. Queued messages: %d", len(self.message_queue))
        self.message_queue.clear()

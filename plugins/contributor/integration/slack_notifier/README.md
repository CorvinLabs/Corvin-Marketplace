# Slack Notifier Plugin

Send notifications to Slack channels from Corvin tasks and workflows.

## Description

The Slack Notifier plugin integrates Corvin with Slack to:
- Send formatted notifications to channels
- Reply in threaded conversations
- Attach rich formatting and attachments
- Support mentions and custom colors

Perfect for workflow notifications, alerts, and team communication.

## Installation

```bash
pip install -e .
```

Or via Corvin-Marketplace:
```bash
corvin plugin install slack_notifier
```

## Configuration

The plugin requires a Slack Incoming Webhook URL:

```json
{
  "slack_webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
  "channel": "#corvin-notifications"
}
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `slack_webhook_url` | string | (required) | Slack incoming webhook URL for notifications |
| `channel` | string | `#corvin-notifications` | Default Slack channel (overridable per notification) |

## Usage

### Send Simple Notification

```python
plugin = SlackNotifier()
await plugin.initialize({
    "slack_webhook_url": "https://hooks.slack.com/services/T/B/X"
})

result = await plugin.send_notification(
    "Deployment Complete",
    "Version 1.2.0 deployed to production",
    color="good"
)
```

### Send to Custom Channel

```python
result = await plugin.send_notification(
    "Alert",
    "High CPU usage detected",
    channel="#alerts",
    color="warning"
)
```

### Send Threaded Reply

```python
result = await plugin.send_thread_notification(
    thread_ts="1234567890.123456",
    title="Status Update",
    message="Process is 50% complete"
)
```

### Via execute() Method

```python
# Send notification
result = await plugin.execute(
    send=True,
    title="Task Complete",
    message="All steps finished",
    channel="#updates",
    color="good"
)

# Send threaded reply
result = await plugin.execute(
    thread=True,
    title="Reply",
    message="Got it!",
    thread_ts="1234567890.123456"
)
```

## Architecture

```
┌────────────────────────┐
│  Corvin Task/Workflow  │
└────────┬───────────────┘
         │
    ┌────▼──────────┐
    │  Notification │
    │    Request    │
    └────┬──────────┘
         │
    ┌────▼─────────────────┐
    │  SlackNotifier       │
    │ - Format Message     │
    │ - Queue Handler      │
    └────┬─────────────────┘
         │
    ┌────▼─────────────────┐
    │  Message Builder      │
    │ - Attachments        │
    │ - Colors/Formatting  │
    └────┬─────────────────┘
         │
    ┌────▼────────────────────┐
    │  Slack API (Webhook)    │
    │  https://hooks.slack... │
    └────┬────────────────────┘
         │
    ┌────▼──────────────┐
    │  Slack Channel    │
    │  #notifications   │
    └───────────────────┘
```

## Message Colors

| Color | Use Case |
|-------|----------|
| `good` (green) | Success, completion, approval |
| `warning` (orange) | Warnings, attention needed |
| `danger` (red) | Errors, critical issues |

## Features

- **Formatted Messages**: Rich text formatting with attachments
- **Threading**: Reply in specific message threads for organized conversations
- **Channel Routing**: Send to different channels based on notification type
- **Color Coding**: Visual indicators for message severity
- **Async Operation**: Non-blocking notification sending
- **Queue Management**: Message queuing for reliable delivery

## Error Handling

- Validates required parameters (title, message, webhook URL)
- Graceful handling of API failures
- Message queue management for retries

## Testing

Run unit tests:

```bash
pytest tests/test_slack_notifier.py -v
```

Run E2E tests:

```bash
pytest tests/e2e_test_slack_notifier.py -v
```

## Limitations

- **Webhook Only**: Uses Slack incoming webhooks (not bot tokens)
- **Single Workspace**: Configured for one Slack workspace per instance
- **Text Content**: No file uploads or complex rich blocks yet
- **Queue in Memory**: Message queue is not persisted across restarts

## Requirements

- Python 3.8+
- requests >= 2.28.0

## Slack Setup

1. Go to your Slack workspace settings: https://api.slack.com/apps
2. Create a new app or select existing
3. Enable "Incoming Webhooks"
4. Create a new webhook for your target channel
5. Copy the webhook URL
6. Use it in the plugin configuration

## Author

Community Contributor (example.com)

## License

MIT - See LICENSE file

## Support

For issues, feature requests, or contributions, visit:
https://github.com/community-plugin/slack-notifier

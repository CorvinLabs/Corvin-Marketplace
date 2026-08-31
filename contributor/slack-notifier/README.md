# Slack Notifier Plugin

Send notifications to Slack channels and threads from CorvinOS.

## Features
- Post messages to Slack channels
- Thread replies
- Markdown formatting
- Interactive buttons and dropdowns
- Error notifications
- Workflow status updates

## Installation

1. Copy this directory to `~/.corvin/tenants/_default/plugins/installed/slack-notifier/`
2. Add Slack webhook URL to your CorvinOS config
3. Restart CorvinOS

## Configuration

```yaml
plugins:
  slack-notifier:
    enabled: true
    webhook_url: "${SLACK_WEBHOOK_URL}"
    channel: "#corvin-alerts"
```

## Usage

```python
from slack_notifier import notify_slack

notify_slack(
    message="Build completed successfully",
    channel="#deployments",
    icon=":rocket:"
)
```

## Security

- Webhook URLs are encrypted in storage
- No message content is logged
- Only configured users can trigger notifications

## Support

See https://github.com/CorvinLabs/Corvin-Marketplace/issues

# Slack Notifier Plugin

Forward CorvinOS audit events to Slack via incoming webhooks.

## Features

- **Event forwarding**: Sends audit events to Slack in real-time
- **Severity-based coloring**: Events are color-coded by severity (debug, info, warning, error, critical)
- **Configurable filtering**: Only notify on specific event types or severity levels
- **Channel routing**: Route notifications to specific Slack channels
- **Error mentions**: Mention @channel or custom groups when errors occur
- **Health monitoring**: Tracks webhook connectivity and request success rates
- **Graceful failure**: Never crashes the core system (fail-safe design)

## Installation

```bash
corvin plugin install slack-notifier
```

Or from this marketplace directory:

```bash
corvin plugin install ./plugins/slack-notifier
```

## Configuration

### Basic Setup

1. Create a Slack Incoming Webhook:
   - Go to https://api.slack.com/apps/
   - Create a new app or select an existing one
   - Enable Incoming Webhooks
   - Create a new webhook URL
   - Copy the webhook URL

2. Configure the plugin via `tenant.corvin.yaml`:

```yaml
plugins:
  slack-notifier:
    enabled: true
    config:
      webhook_url: "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
      test_webhook_on_load: true
      min_severity: "warning"
```

3. Enable and test:

```bash
corvin plugin enable slack-notifier
corvin plugin health slack-notifier
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `webhook_url` | string | **required** | Slack incoming webhook URL |
| `test_webhook_on_load` | boolean | `true` | Test webhook connectivity on startup |
| `notify_on_events` | array | `[]` | Event types to notify on (empty = all) |
| `min_severity` | string | `"warning"` | Minimum severity level (debug, info, warning, error, critical) |
| `channel` | string | `""` | Target channel (webhook-specific; optional) |
| `mention_on_error` | string | `""` | Mention group on errors (e.g., `@oncall`, `@channel`) |

### Example: Full Configuration

```yaml
plugins:
  slack-notifier:
    enabled: true
    config:
      webhook_url: "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXX"
      test_webhook_on_load: true
      notify_on_events:
        - "plugin.loaded"
        - "plugin.error"
        - "user.login"
      min_severity: "info"
      channel: "#corvin-logs"
      mention_on_error: "@oncall"
```

## Usage

Once enabled, the plugin automatically sends notifications when audit events occur. You don't need to do anything else — it runs in the background and forwards events to Slack.

### Viewing Slack Messages

Events appear in your configured Slack channel with:

- **Event name** and severity in the text
- **Color-coded attachment** matching severity level
- **Event details** including tenant ID and payload (truncated to 500 chars)
- **Timestamp** and footer identifying CorvinOS + plugin

### Monitoring Plugin Health

```bash
# Check health status
corvin plugin health slack-notifier

# View metrics
corvin plugin metrics slack-notifier

# Check recent events
corvin plugin logs slack-notifier
```

Expected health output:
```
Status: OK
Message: Connected and operational
Details:
  requests_sent: 42
  requests_failed: 1
  error_rate: 2.3%
```

## Error Handling

The plugin is designed to never crash the core system:

- **Webhook timeout** (>5 seconds): Logged as error, request counted as failed
- **Network errors** (connection refused, DNS failure): Gracefully caught, not retried
- **Invalid webhook URL**: Caught at startup; plugin loads but marked unhealthy
- **Webhook returns error** (5xx, 4xx): Logged with HTTP status, counted as failed
- **Invalid event payload**: Truncated to 500 chars to prevent huge messages

Health check monitors error rate: if >10% of requests fail, plugin reports unhealthy.

## Performance

- **Webhook calls**: Blocking I/O, ~100-500ms per call (no async yet)
- **Message format**: ~1-2ms per event
- **Health check**: <1ms (local only)
- **Memory**: ~50KB per plugin instance

For high-volume audit trails, consider filtering events via `notify_on_events` to reduce webhook load.

## Testing

Unit tests are included in `tests/test_slack_notifier_plugin.py`.

Run tests locally:

```bash
cd plugins/slack-notifier
pip install -e ".[dev]"
pytest
```

Run with coverage:

```bash
pytest --cov=. --cov-report=term-missing
```

## Security & Compliance

### PII Handling

The plugin receives audit events that may contain PII (user IDs, IP addresses, etc.). 

**Important**: Webhook URLs are stored as plaintext in config. Restrict access to:
- `tenant.corvin.yaml`
- Plugin configuration files
- Slack audit logs (webhook recipient)

### Audit Trail

All plugin operations are audit-logged:
- `plugin.loaded` — plugin startup
- `plugin.notified` — each webhook call (webhook URL redacted)
- `plugin.health_check` — health status changes
- `plugin.error` — errors during operation

### Compliance

- **GDPR Art. 30, 32**: Audit trail logged and hash-chained
- **EU AI Act Art. 50**: Disclosure included in bot-disclosure card
- **Webhook security**: HTTPS only, validated at load time

## Troubleshooting

### Plugin fails to load

**Error: "Invalid webhook_url: must start with 'https://hooks.slack.com/'"**

- Verify the webhook URL is copied correctly from Slack
- Must be an incoming webhook, not an OAuth token

**Error: "Webhook test failed: ConnectionError"**

- Check network connectivity to `hooks.slack.com`
- Verify no firewall is blocking outbound HTTPS
- Plugin will continue to load; webhook may work later

### No events in Slack

1. Check plugin health:
   ```bash
   corvin plugin health slack-notifier
   ```

2. Verify webhook is working:
   ```bash
   curl -X POST -H 'Content-type: application/json' \
       --data '{"text":"Test from CorvinOS"}' \
       https://hooks.slack.com/services/YOUR/WEBHOOK/URL
   ```

3. Check event filtering:
   - If `notify_on_events` is set, only those events trigger notifications
   - If `min_severity` is high, low-severity events are filtered

4. Check plugin logs:
   ```bash
   corvin plugin logs slack-notifier --tail 50
   ```

### High error rate

If health check reports >10% error rate:

1. Check webhook URL validity (retest at Slack)
2. Verify network connectivity
3. Check Slack API status (https://status.slack.com)
4. Check event payload size (large payloads may be rejected)

## Support

For issues or questions:

1. Check this README
2. Review plugin logs: `corvin plugin logs slack-notifier`
3. Open an issue on GitHub: https://github.com/CorvinLabs/Corvin-Marketplace/issues
4. Contact support: plugins@corvin-labs.com

## License

Apache-2.0 (see LICENSE in marketplace root)

## Changelog

### v1.0.0 (2026-08-29)

- Initial release
- Event forwarding to Slack webhooks
- Severity-based coloring and filtering
- Health check and metrics export
- Full test coverage
- GDPR + EU AI Act compliance

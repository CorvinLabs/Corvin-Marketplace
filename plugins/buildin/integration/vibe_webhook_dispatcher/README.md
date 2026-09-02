# Vibe Webhook Dispatcher

## Overview

The Vibe Webhook Dispatcher plugin enables external systems to subscribe to lifecycle events, milestones, and error states from Vibe sessions. It provides webhook registration, reliable event delivery with retry logic, signature-based webhook authentication, and event filtering by type or pattern. External systems can integrate deeply with Vibe workflows by receiving real-time notifications of session state changes without polling or tight coupling.

## Use Case

**Scenario:** Integrating Vibe sessions with external systems

- An analytics platform wants to receive notifications whenever a Vibe session completes, so it can immediately ingest the decision trace and session artifacts for compliance reporting without querying the API
- A monitoring dashboard needs to be notified of Vibe session errors and milestones in real-time to display status and trigger escalations to operations teams
- An external CI/CD pipeline integrates Vibe session decisions (e.g., "should we deploy?") into automated workflow—it subscribes to decision milestone events so deployment automation can proceed immediately upon Vibe decision

**Impact:** External systems are kept in sync with Vibe session state without continuous polling; real-time notifications enable responsive downstream automation; webhook security (HMAC signatures) prevents spoofing.

## API Example

```python
from corvin_plugins.providers.vibe_webhook_dispatcher import WebhookDispatcher, WebhookSubscription

# Initialize dispatcher
dispatcher = WebhookDispatcher(
    base_url="https://vibe.example.com",
    webhook_timeout_seconds=10,
    max_retries=3,
    retry_backoff_seconds=5
)

# Register a webhook for session lifecycle events
subscription = WebhookSubscription(
    webhook_url="https://external-analytics.example.com/vibe/events",
    events=[
        "session.started",
        "session.decision_made",
        "session.completed",
        "session.error"
    ],
    secret_token="webhook_secret_key_12345",  # For signature verification
    active=True
)

webhook_id = dispatcher.register_webhook(subscription)
print(f"Webhook registered with ID: {webhook_id}")

# When Vibe session reaches a milestone, webhook is called automatically
# Example webhook payload (sent by dispatcher):
webhook_payload = {
    "event_type": "session.decision_made",
    "session_id": "session-abc123",
    "timestamp": "2026-09-02T15:30:45.123Z",
    "tenant_id": "_default",
    "data": {
        "decision_type": "should_deploy",
        "decision": "yes",
        "confidence": 0.92,
        "reasoning_summary": "All checks passed and metrics healthy"
    },
    "signature": "sha256=abcd1234..."  # HMAC signature for verification
}

# Example external system (receiver) validates signature
import hmac
import hashlib

def verify_webhook_signature(payload, signature, secret):
    expected_sig = "sha256=" + hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected_sig)

# Configure event filtering
dispatcher.update_webhook(
    webhook_id=webhook_id,
    events=[
        "session.completed",
        "session.error"
    ]
)

# Get webhook statistics
stats = dispatcher.get_webhook_stats(webhook_id)
print(f"Deliveries: {stats.total_deliveries}")
print(f"Success rate: {stats.success_rate * 100:.1f}%")
print(f"Last delivery: {stats.last_delivery_timestamp}")
```

## Configuration

The Vibe Webhook Dispatcher requires the following configuration in `tenant.corvin.yaml`:

```yaml
plugins:
  vibe_webhook_dispatcher:
    enabled: true
    webhook_timeout_seconds: 10
    max_retries: 3
    retry_backoff_seconds: 5
    max_webhook_payload_size_bytes: 1048576  # 1 MB
    rate_limit_webhooks_per_second: 100
    enable_webhook_signing: true
    signing_algorithm: "sha256"
    webhook_event_types:
      - "session.started"
      - "session.decision_made"
      - "session.milestone"
      - "session.completed"
      - "session.error"
      - "session.cancelled"
    delivery_persistence: true  # Persist failed deliveries for retry
    persistence_ttl_days: 7
```

## Status

**Implementation:** Production Ready
**Tests:** 20 unit tests + 16 integration tests (36 total)
**Compliance:** ADR-0510 (Hub Wiring), ADR-0511 (Marketplace), ADR-0538 (A2A Protocol v6)

---
**Plugin ID:** plugin:buildin-integration-vibe_webhook_dispatcher
**Version:** 1.0.0 | **Boot Layer:** bundled
**Maintainer:** plugins@anthropic.com
**License:** Apache-2.0

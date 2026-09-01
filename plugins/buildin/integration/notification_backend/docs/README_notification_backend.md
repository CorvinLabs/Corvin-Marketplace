# Notification Backend Plugin

## Purpose

The **Notification Backend** plugin provides a registry for managing system notification handlers with thread-safe provider swapping. It includes a default logging-based implementation and enables plugins to install custom notification backends for audit trail integration (L16, GDPR Art. 30).

## Usage Example

```python
from corvin_plugins.providers.notification_backend import get_active, set_active

class SlackNotificationBackend:
    def notify(self, event, payload, *, tenant_id="_default", severity="info"):
        # Send to Slack webhook
        slack_post(f"[{severity}] {event}: {payload}")

# Install during plugin load
ctx.notification_registry.set_active(SlackNotificationBackend())

# Caller retrieves and uses
backend = get_active()
backend.notify("adapter.rate_limited", {"severity": "warn"}, tenant_id="tenant-1")
```

## Integration Points

**Provides:**
- `set_active(provider)` — Install custom notification backend
- `get_active()` — Retrieve active backend (never caches; respects hot-reload)
- `clear()` — Restore default LogNotificationBackend
- `release_owned_by(plugin_id)` — Release by plugin identity
- `clear_if_active(provider)` — Restore default only if instance matches

**Requires:**
- `corvin_plugins.loading.current()` — Plugin ownership tracking

**Default Implementation:**
- **LogNotificationBackend** — Logs events to Python logger with severity mapping (info/warn/error/critical)

**Integrates with:**
- **L16 Security**: Audit trail recording for security events
- **Tenant Isolation**: All notifications include `tenant_id` for multi-tenant audit trails
- **GDPR Art. 30**: Audit records for all system notifications

## Data Flow Diagram

```svg
<svg width="600" height="350" xmlns="http://www.w3.org/2000/svg">
  <text x="10" y="25" font-size="18" font-weight="bold">Notification Backend Registry</text>
  
  <!-- Event sources -->
  <rect x="20" y="60" width="80" height="40" fill="#e8f4f8" stroke="#333" stroke-width="2"/>
  <text x="25" y="85" font-size="11" font-weight="bold">Auth Guard</text>
  
  <rect x="110" y="60" width="80" height="40" fill="#e8f4f8" stroke="#333" stroke-width="2"/>
  <text x="120" y="85" font-size="11" font-weight="bold">Rate Limiter</text>
  
  <rect x="200" y="60" width="80" height="40" fill="#e8f4f8" stroke="#333" stroke-width="2"/>
  <text x="210" y="85" font-size="11" font-weight="bold">Error Handler</text>
  
  <!-- Notify calls -->
  <path d="M 60 100 L 150 140" stroke="#333" stroke-width="1.5" marker-end="url(#arrowhead)"/>
  <path d="M 150 100 L 180 140" stroke="#333" stroke-width="1.5" marker-end="url(#arrowhead)"/>
  <path d="M 240 100 L 200 140" stroke="#333" stroke-width="1.5" marker-end="url(#arrowhead)"/>
  
  <!-- Registry -->
  <rect x="120" y="140" width="160" height="70" fill="#fff8dc" stroke="#333" stroke-width="2"/>
  <text x="130" y="160" font-size="12" font-weight="bold">NotificationBackendRegistry</text>
  <text x="130" y="175" font-size="10">_lock (thread-safe)</text>
  <text x="130" y="188" font-size="10">_owner_plugin_id (ownership)</text>
  <text x="130" y="201" font-size="10">_active (provider instance)</text>
  
  <!-- get_active() -->
  <path d="M 280 175 L 340 175" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="300" y="170" font-size="9">get_active()</text>
  
  <!-- Backends -->
  <rect x="340" y="140" width="90" height="35" fill="#e8f8e8" stroke="#333" stroke-width="2"/>
  <text x="350" y="162" font-size="11" font-weight="bold">Log Backend</text>
  <text x="350" y="170" font-size="9">(default)</text>
  
  <rect x="340" y="185" width="90" height="35" fill="#f0e8f4" stroke="#333" stroke-width="2"/>
  <text x="350" y="207" font-size="11" font-weight="bold">Custom Backend</text>
  <text x="350" y="215" font-size="9">(plugin-installed)</text>
  
  <!-- Audit trail -->
  <rect x="120" y="270" width="320" height="50" fill="#ffe8e8" stroke="#333" stroke-width="2" stroke-dasharray="5,5"/>
  <text x="130" y="290" font-size="11" font-weight="bold">Audit Trail (GDPR Art. 30)</text>
  <text x="130" y="305" font-size="10">event, payload, tenant_id, severity, timestamp</text>
  
  <path d="M 240 210 L 240 270" stroke="#999" stroke-width="1" stroke-dasharray="3,3"/>
  
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#333"/>
    </marker>
  </defs>
</svg>
```

## Compliance Notes

- **ADR-0033**: Provider registry pattern — unified contract for multi-provider registry
- **L16 Security Hardening**: Audit trail recording for security-relevant events
- **GDPR Art. 30**: Record-keeping for processing activities; all notifications logged to audit trail
- **GDPR Art. 6**: Lawful basis for audit notifications (F legitimate interest)
- **Thread-safety**: All operations protected by `threading.Lock()`
- **Hot-reload**: `get_active()` never caches; always retrieves current provider

## References

- **Plugin**: `plugin:buildin-integration-notification_backend` (buildin tier, bundled boot layer)
- **Source**: `/home/shumway/projects/Corvin-Marketplace/plugins/buildin/integration/notification_backend/src/notification_backend.py`
- **Tests**: `tests/test_notification_backend.py` (9 test cases covering registry, severity mapping, thread-safety)

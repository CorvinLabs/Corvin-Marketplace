# CorvinOS Plugin Development Guide

**References:** ADR-0233 (plugin-system), ADR-0243 (boot-layers), ADR-0249 (trust-anchor), ADR-0262 (plugin-builder-v2)

This guide covers everything needed to build, test, and publish a plugin to the Corvin Marketplace.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Choosing Your Plugin Type](#choosing-your-plugin-type)
3. [Plugin Structure](#plugin-structure)
4. [Manifest Reference](#manifest-reference)
5. [Implementation Patterns](#implementation-patterns)
6. [Testing Your Plugin](#testing-your-plugin)
7. [Validation](#validation)
8. [Publishing](#publishing)
9. [Security & Compliance](#security--compliance)
10. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Option 1: Using Plugin-Builder (Recommended)

Interactive guided creation with scaffolding:

```bash
# In CorvinOS chat
/plugin-builder

# Answer interview questions
# → Problem domain
# → Desired solution
# → Scope (router, notifier, etc.)

# Outputs: ready-to-code plugin scaffold
```

See [ADR-0262](https://github.com/CorvinLabs/Corvin-ADR/blob/main/decisions/ADR-0262-plugin-builder-v2.md) for details.

### Option 2: Manual Scaffolding

Clone the Corvin-Marketplace and use the template:

```bash
git clone https://github.com/CorvinLabs/Corvin-Marketplace
cd Corvin-Marketplace/plugins

# Copy template
cp -r _TEMPLATE my-plugin

# Edit manifest.yaml
# Implement plugin.py
# Write tests
```

### Option 3: Clone a Template Repository

```bash
git clone https://github.com/CorvinLabs/plugin-template-router-backend
cd plugin-template-router-backend

# Edit manifest.yaml, plugin.py, tests/
```

---

## Choosing Your Plugin Type

CorvinOS has **11 extension points**. Not all are currently invoked by the runtime — check before committing to one:

```bash
corvin plugin types    # Lists live vs. dead extension points
```

### Live Plugin Types (actively invoked)

| Type | Layer | Purpose | Complexity |
|---|---|---|---|
| **`router_backend`** | L5 | Route messages to the right handler | Medium |
| **`audit_backend`** | L16 | Receive copies of audit events (additive-only) | Medium |
| **`notification_backend`** | L3+ | Notify external systems of events | Low |
| **`summary_provider`** | L11 | Generate summary text | Medium |
| **`recall_backend`** | L28 | Store/retrieve user conversation history | High |

### Dead Plugin Types (never invoked, don't use)

| Type | Layer | Reason |
|---|---|---|
| `user_backend` | L18–21 | No credential-based login yet (wired but unreachable) |
| `stt_provider` | L23 | Only metadata stored (internal only) |
| `data_connector` | L24 | Unimplemented in v0.x |
| `compute_engine` | L25 | Experimental, no dispatch code |
| `worker_engine` | L22 | Hardcoded engine selection |
| `bridge_channel` | Bridges | Bridge registry doesn't call discovery |

**Recommendation:** Only use live types. If you need a dead type, open an issue in Corvin-ADR to request wiring.

---

## Plugin Structure

### Directory Layout

```
my-plugin/
├── manifest.yaml              # Plugin metadata (required)
├── plugin.py                  # Implementation (required)
├── pyproject.toml             # Python project config + entry points
├── README.md                  # Documentation
├── requirements.txt           # Python dependencies
├── tests/
│   ├── __init__.py
│   ├── test_plugin.py         # Unit tests
│   └── test_wiring.py         # E2E wiring proof (ADR-0259)
└── docs/
    ├── EXAMPLES.md            # Usage examples
    └── TROUBLESHOOTING.md     # Common issues & fixes
```

### Minimal plugin.py

```python
"""My Plugin — brief description."""

from corvin_plugins.protocol import PluginContext, HealthStatus


class MyRouterBackend:
    """Router backend plugin."""

    # Required attributes (plugin contract, ADR-0030)
    plugin_id = "com.example.my-router"
    plugin_type = "router_backend"
    version = "1.0.0"
    display_name = "My Router Backend"

    # Lifecycle (required)
    def on_load(self, ctx: PluginContext) -> None:
        """Called when plugin loads. Register with the layer."""
        ctx.router_registry.set_active(self)

    def on_unload(self) -> None:
        """Called when plugin unloads. Clean up resources."""
        pass

    def health_check(self) -> HealthStatus:
        """Return health status. Must complete within 2 seconds."""
        return HealthStatus(ok=True, message="ok")

    # Capability (required for this type)
    def route(self, message, context):
        """Route a message. Return None on no-match or error (never raise)."""
        if "my-condition" in message:
            return "my-handler"
        return None
```

### pyproject.toml Entry Points

```toml
[project]
name = "my-plugin"
version = "1.0.0"
description = "My plugin for CorvinOS"

[project.entry-points."corvin.plugins"]
# Entry point name = module:ClassName
my-router = "plugin:MyRouterBackend"
```

**Entry point format:** Must match `manifest.yaml`'s `entry_point` field.

---

## Manifest Reference

See [PLUGIN_MANIFEST.md](PLUGIN_MANIFEST.md) for detailed field specifications.

### Minimal manifest.yaml

```yaml
plugin: "1.0"
id: "com.example.my-router"
name: "My Router"
version: "1.0.0"
description: "Routes messages based on keywords."
author: "Your Name"
license: "Apache-2.0"
entry_point: "plugin.py::MyRouterBackend"
plugin_type: "router_backend"
```

### Adding Permissions & Risk Disclosure

```yaml
# ... fields above ...

permissions:
  network_egress: []        # No network access
  pii_risk: "low"
  data_locality: "local"
  audit_logging: true

dependencies: []
requires: []
keywords: ["routing", "messages"]
```

### Versioning & Compatibility

```yaml
min_corvin_version: "0.10.0"
max_corvin_version: null    # null = no upper bound

dependencies:
  - id: "com.other.plugin"
    version: ">=1.0.0,<2.0.0"
```

---

## Implementation Patterns

### Pattern 1: Router Backend

```python
class MyRouter:
    plugin_id = "com.example.router"
    plugin_type = "router_backend"
    version = "1.0.0"
    display_name = "My Router"

    def on_load(self, ctx):
        ctx.router_registry.set_active(self)

    def on_unload(self):
        pass

    def health_check(self):
        return HealthStatus(ok=True)

    def route(self, message, context):
        """Route must never raise. Return None on error."""
        try:
            if self._should_handle(message):
                return self._get_handler(message)
        except Exception as e:
            logging.error(f"Router error: {e}")
        return None

    def _should_handle(self, message):
        # Your logic
        return "keyword" in message

    def _get_handler(self, message):
        # Return handler name
        return "my-handler"
```

### Pattern 2: Notification Backend

```python
class MyNotifier:
    plugin_id = "com.example.notifier"
    plugin_type = "notification_backend"
    version = "1.0.0"
    display_name = "My Notifier"

    def on_load(self, ctx):
        ctx.notification_registry.set_active(self)

    def on_unload(self):
        # Close connections, flush queues
        pass

    def health_check(self):
        return HealthStatus(ok=True)

    def notify(self, event, payload, *, tenant_id="_default", severity="info"):
        """
        Send notification. Must not:
        - Block >100ms
        - Log message content or PII
        - Raise exceptions
        """
        try:
            # Redact payload (never send raw content)
            safe_payload = self._redact(payload)
            self._send_notification(event, safe_payload, severity)
        except Exception as e:
            logging.error(f"Notification failed: {e}")

    def _redact(self, payload):
        # Remove PII, credentials, message content
        return {
            "event": payload.get("event"),
            "severity": payload.get("severity"),
            "timestamp": payload.get("timestamp"),
        }

    def _send_notification(self, event, payload, severity):
        # Send to external system (async if possible)
        pass
```

### Pattern 3: Audit Backend

```python
class MyAuditBackend:
    plugin_id = "com.example.audit"
    plugin_type = "audit_backend"
    version = "1.0.0"
    display_name = "My Audit Backend"

    def on_load(self, ctx):
        ctx.providers.audit_backend.set_active(self)

    def on_unload(self):
        pass

    def health_check(self):
        return HealthStatus(ok=True)

    def write_event(self, event, *, tenant_id="_default"):
        """
        Write audit event. CONSTRAINTS (ADR-0232):
        - Receives COPY after core write commits
        - Cannot suppress, delay, or rewrite core chain
        - Must not raise (fire-and-forget)
        - Never store secrets or PII unredacted
        """
        try:
            # Event is immutable (frozen dataclass)
            # Just forward to external store
            self._forward_to_external_system(event)
        except Exception as e:
            logging.error(f"Audit write failed: {e}")
            # Do NOT re-raise; fire-and-forget

    def _forward_to_external_system(self, event):
        # Send to SIEM, database, webhook, etc.
        pass
```

---

## Testing Your Plugin

### Unit Tests (test_plugin.py)

```python
"""Unit tests for the plugin."""

import pytest
from plugin import MyRouter


class TestMyRouter:
    def test_route_matching(self):
        router = MyRouter()
        # Mock PluginContext
        result = router.route("message with keyword", None)
        assert result == "my-handler"

    def test_route_no_match(self):
        router = MyRouter()
        result = router.route("unrelated message", None)
        assert result is None

    def test_router_never_raises(self):
        """Route must be fail-safe."""
        router = MyRouter()
        # Test with invalid input
        result = router.route(None, None)
        assert result is None
        # No exception raised

    def test_health_check(self):
        router = MyRouter()
        health = router.health_check()
        assert health.ok is True
```

### E2E Wiring Proof (test_wiring.py)

Tests that the plugin is **actually invoked by the runtime** (ADR-0259):

```python
"""E2E wiring proof — plugin is reachable from the runtime."""

import pytest
from corvin_plugins.protocol import PluginContext
from plugin import MyRouter


class TestMyRouterWiring:
    def test_plugin_loads_via_entry_point(self):
        """Proof: Entry point is correctly wired."""
        import importlib.metadata

        # Check entry point exists
        eps = importlib.metadata.entry_points()
        my_router_ep = None

        for ep in eps.get("corvin.plugins", []):
            if ep.name == "my-router":
                my_router_ep = ep
                break

        assert my_router_ep is not None
        # Load the class
        plugin_cls = my_router_ep.load()
        assert plugin_cls is MyRouter

    def test_plugin_initializes_via_context(self):
        """Proof: Plugin integrates with PluginContext."""
        # This would require a real CorvinOS instance
        # For now, check that the interface matches
        plugin = MyRouter()
        assert hasattr(plugin, "on_load")
        assert hasattr(plugin, "on_unload")
        assert hasattr(plugin, "health_check")
        assert hasattr(plugin, "route")  # capability method
```

### Running Tests

```bash
# Install test dependencies
pip install -r requirements.txt pytest

# Run tests
pytest tests/

# With coverage
pip install pytest-cov
pytest tests/ --cov=. --cov-report=html
```

---

## Validation

### Validate Locally

Before submitting a PR, validate your plugin:

```bash
# Navigate to Corvin-Marketplace
cd /path/to/Corvin-Marketplace

# Validate your plugin
./scripts/register-plugin.sh --validate ./plugins/my-plugin

# If using CorvinOS CLI
corvin plugin check ./plugins/my-plugin
```

### What Gets Validated

1. **Manifest schema** — validates against JSON schema
2. **Entry points** — checks `plugin.py::ClassName` exists
3. **Dependencies** — validates version constraints, detects circular deps
4. **Wiring** — imports the class to verify it's importable
5. **Code quality** — linting via ruff (optional)
6. **Tests** — runs pytest (optional)

### Fixing Validation Errors

| Error | Fix |
|---|---|
| `MANIFEST_NOT_FOUND` | Create `manifest.yaml` in plugin directory |
| `SCHEMA_VALIDATION_ERROR` | Check field names and types against [PLUGIN_MANIFEST.md](PLUGIN_MANIFEST.md) |
| `ENTRY_POINT_MODULE_NOT_FOUND` | Ensure `plugin.py` exists in plugin directory |
| `ENTRY_POINT_CLASS_NOT_FOUND` | Check class name matches manifest's `entry_point` field |
| `INVALID_DEPENDENCY_VERSION` | Use valid semver (e.g., `>=1.0.0,<2.0.0`) |
| `CIRCULAR_DEPENDENCY` | Check `dependencies` list for cycles (A→B→A) |
| `UNSUPPORTED_PLUGIN_TYPE` | Plugin type is not live — see [Choosing Your Plugin Type](#choosing-your-plugin-type) |

---

## Publishing

### Prerequisites

1. **CLA Signature** — Sign the CLA once (one-time per author)
   - Visit: https://corvin-labs.com/cla
   - Takes 2 minutes

2. **Plugin Ready** — Local validation passes
   ```bash
   ./scripts/register-plugin.sh --validate ./plugins/my-plugin
   ```

3. **Tests Passing**
   ```bash
   pytest plugins/my-plugin/tests/
   ```

### Submission Steps

1. **Fork the Corvin-Marketplace repo**
   ```bash
   git clone https://github.com/YOUR_USERNAME/Corvin-Marketplace
   cd Corvin-Marketplace
   ```

2. **Create a feature branch**
   ```bash
   git checkout -b add-my-plugin
   ```

3. **Copy your plugin to the plugins/ directory**
   ```bash
   cp -r ~/my-plugin ./plugins/
   ```

4. **Commit your changes**
   ```bash
   git add plugins/my-plugin/
   git commit -m "Add plugin: my-plugin (router_backend, Tier-C, community)"
   ```

5. **Push and create a PR**
   ```bash
   git push origin add-my-plugin
   # Then create PR on GitHub
   ```

6. **PR Checklist** (will be auto-checked by CI)
   - ✅ Manifest validates against schema
   - ✅ Entry point is correct
   - ✅ Tests pass
   - ✅ No circular dependencies
   - ✅ Code passes linting (ruff)
   - ✅ CLA signed

### After Merge

- **CI regenerates registry.json** (24h)
- **Voice discovery indexes the plugin** (24h)
- **Marketplace UI lists the plugin** (24h)
- **CorvinOS instances auto-sync via `corvin plugin sync`** (within 7d)

---

## Security & Compliance

### Trust Model (ADR-0249)

Your plugin will be published as **`origin: community`**. This means:

- ✅ **Listed in marketplace** — anyone can see it
- ✅ **Publicly auditable** — code in this repo is open
- ⚠️ **Not maintainer-signed** — no Ed25519 signature (only maintainer can do this)
- ⚠️ **Consent-gated** — users see a warning before installing
- ⚠️ **No auto-updates** — users must explicitly approve updates

**If you want `origin: vetted`:** Your plugin must be reviewed and signed by the CorvinOS maintainer. Open an issue in [Corvin-ADR](https://github.com/CorvinLabs/Corvin-ADR) to request.

### Boot Layers (ADR-0243)

Your plugin will declare **`boot_layer: installed`**. This means:

- ✅ Loads after core + bundled plugins
- ✅ Can be disabled by the operator
- ❌ **Cannot** replace core functionality
- ❌ **Cannot** declare `compliance` or `core` boot layers (community origin constraint)

### Permissions Disclosure (Governance, not Enforcement)

Declare what your plugin does to help operators review it:

```yaml
permissions:
  network_egress: ["api.example.com"]  # [] = no network access
  pii_risk: "medium"                    # none, low, medium, high
  data_locality: "remote"               # local, remote, hybrid
  audit_logging: true                   # Always true for compliance
```

**Important:** These are **informational only**. The runtime does NOT enforce them. Once loaded, a plugin runs in-process and can call any Python code.

### Audit Trail (ADR-0232)

Every plugin invocation is logged to the hash-chained audit log:

```json
{
  "type": "plugin_invoked",
  "plugin_id": "com.example.my-router",
  "plugin_type": "router_backend",
  "timestamp": "2026-08-29T14:30:00Z",
  "tenant_id": "_default",
  "duration_ms": 42
}
```

See [Layer 16 — Security Hardening](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/claude-ref/layer-16-security.md) for details.

---

## Troubleshooting

### Plugin loads but route() is never called

**Likely cause:** Entry point not registered correctly.

```bash
# Check entry point
grep -A2 "entry_point:" manifest.yaml
# Should be: entry_point: "plugin.py::MyRouterBackend"

# Check pyproject.toml
grep -A1 '[[project.entry-points."corvin.plugins"]]'
# Should be: my-router = "plugin:MyRouterBackend"

# Verify import
python3 -c "from plugin import MyRouterBackend; print('OK')"
```

### Health check timeout (>2 seconds)

**Cause:** `health_check()` method takes too long.

```python
def health_check(self):
    # DON'T do this (too slow):
    # network_call()
    # file_io()
    # large_database_query()

    # DO this (fast, local check):
    return HealthStatus(ok=True, message="ok")
```

### Manifest validation fails

Run the validator with detailed output:

```bash
./scripts/register-plugin.sh --validate ./plugins/my-plugin
# Shows which field failed and why
```

### Plugin raises exception

**All plugin methods must be fail-safe:**

```python
def route(self, message, context):
    try:
        # your logic
        return handler_name
    except Exception as e:
        logging.error(f"Router error: {e}")
        return None  # Fail gracefully
```

### Circular dependency detection

```bash
# Check dependencies
grep -A5 "dependencies:" plugins/my-plugin/manifest.yaml

# Manually trace:
# - my-plugin depends on: X
# - X depends on: Y
# - Y depends on: my-plugin  ← CYCLE!
```

---

## References

- **[ADR-0233](https://github.com/CorvinLabs/Corvin-ADR/blob/main/decisions/ADR-0233-plugin-consolidation.md)** — Plugin System Architecture
- **[ADR-0243](https://github.com/CorvinLabs/Corvin-ADR/blob/main/decisions/ADR-0243-plugin-boot-layers.md)** — Boot Layers (compliance·core·bundled·installed)
- **[ADR-0249](https://github.com/CorvinLabs/Corvin-ADR/blob/main/decisions/ADR-0249-plugin-trust-anchor.md)** — Trust Anchor & Signatures
- **[ADR-0262](https://github.com/CorvinLabs/Corvin-ADR/blob/main/decisions/ADR-0262-plugin-builder-v2.md)** — Plugin-Builder v2
- **[Plugin Architecture](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/plugin-architecture.md)** — Complete architecture reference
- **[Plugin Manifest](PLUGIN_MANIFEST.md)** — Detailed manifest field reference
- **[Corvin-Marketplace README](README.md)** — Repository overview

---

**Questions?** Open an issue in [Corvin-ADR](https://github.com/CorvinLabs/Corvin-ADR) or [CorvinOS](https://github.com/CorvinLabs/CorvinOS).

**Ready to build?** Start with `/plugin-builder` or clone the template repo. Happy coding!

# Example Router Backend Plugin

A reference implementation of a router backend plugin for CorvinOS.

## What This Plugin Does

This plugin demonstrates a simple router that directs messages to handlers based on keyword matching:

- **"database" or "sql"** → `database-handler`
- **"email" or "mail"** → `email-handler`
- **"api" or "rest"** → `api-handler`
- **Other messages** → No route (returns `None`)

## Key Features

✅ **Never raises exceptions** — implements fail-safe routing  
✅ **Fast health check** — responds in <10ms  
✅ **No network access** — local-only, no egress  
✅ **Proper logging** — no PII leakage  
✅ **Full test coverage** — unit + wiring tests  

## Files

- **`manifest.yaml`** — Plugin metadata (name, version, permissions, dependencies)
- **`plugin.py`** — Implementation (router backend contract)
- **`pyproject.toml`** — Python package config + entry point
- **`tests/`** — Unit tests and E2E wiring proof
- **`docs/`** — Extended documentation (examples, troubleshooting)

## Usage

### Installation

```bash
cd Corvin-Marketplace/plugins/examples/example-router-backend

# Validate locally
../../scripts/register-plugin.sh --validate .

# Or via CorvinOS CLI
corvin plugin check .
```

### Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
pytest tests/ --cov=. --cov-report=html
```

### Example: Route a Message

In CorvinOS or a test harness:

```python
from plugin import ExampleRouterBackend

router = ExampleRouterBackend()

# Route a message
result = router.route("I need to query my database")
print(result)  # Output: "database-handler"

# No match
result = router.route("Tell me a joke")
print(result)  # Output: None

# Error handling (never raises)
result = router.route(None)  # ← This would normally crash
print(result)  # Output: None (gracefully handled)
```

## Manifest Fields Explained

| Field | Value | Meaning |
|---|---|---|
| `id` | `com.corvinlabs.example-router` | Unique reverse-domain ID |
| `plugin_type` | `router_backend` | Implements message routing |
| `origin` | `community` | Unreviewed, self-published |
| `boot_layer` | `installed` | Loads after core, can be disabled |
| `pii_risk` | `none` | Handles no PII |
| `network_egress` | `[]` | No network access |

## How to Extend This

### Add a New Routing Rule

Edit `plugin.py`'s `_match_handler()` method:

```python
def _match_handler(self, message: str) -> Optional[str]:
    message_lower = message.lower()
    
    # ... existing rules ...
    
    # NEW: Add your rule here
    if "payment" in message_lower or "invoice" in message_lower:
        return "payment-handler"
    
    return None
```

### Add Dependencies

If your plugin needs external packages, update `pyproject.toml`:

```toml
dependencies = [
    "requests>=2.28",
    "pydantic>=1.9",
]
```

And `manifest.yaml`:

```yaml
requires:
  - "requests>=2.28"
  - "pydantic>=1.9"
```

### Add Network Access

Update `manifest.yaml` permissions:

```yaml
permissions:
  network_egress: ["api.example.com"]  # Allowed endpoints
  data_locality: "remote"              # Sends data externally
```

## Testing Patterns

### Unit Test (test_plugin.py)

```python
def test_route_database_query():
    router = ExampleRouterBackend()
    result = router.route("I need to query my database")
    assert result == "database-handler"
```

### E2E Wiring Proof (test_wiring.py)

```python
def test_plugin_entry_point_exists():
    """Proof: Entry point is correctly wired (ADR-0259)"""
    import importlib.metadata
    eps = importlib.metadata.entry_points()
    ep = [e for e in eps.get("corvin.plugins", []) if e.name == "example-router"]
    assert len(ep) > 0
    plugin_cls = ep[0].load()
    assert plugin_cls.__name__ == "ExampleRouterBackend"
```

## Security Considerations

### ✅ This Plugin is Safe

- ✅ No network access
- ✅ No file I/O
- ✅ No database access
- ✅ No PII handling
- ✅ No secrets in config

### ⚠️ Plugin Permissions (Informational)

Once loaded, a plugin runs in-process with full Python capabilities. The `permissions` section in `manifest.yaml` is **informational** to help operators review the plugin before installing.

It is **NOT** a sandbox or enforcement boundary.

## References

- [PLUGIN_DEVELOPMENT.md](../../PLUGIN_DEVELOPMENT.md) — Comprehensive developer guide
- [PLUGIN_MANIFEST.md](../../PLUGIN_MANIFEST.md) — Manifest field reference
- [ARCHITECTURE.md](../../ARCHITECTURE.md) — System architecture
- [ADR-0233](https://github.com/CorvinLabs/Corvin-ADR/blob/main/decisions/ADR-0233-plugin-consolidation.md) — Plugin system
- [ADR-0243](https://github.com/CorvinLabs/Corvin-ADR/blob/main/decisions/ADR-0243-plugin-boot-layers.md) — Boot layers

## Contributing

This is a reference implementation. To build your own plugin:

1. Use `/plugin-builder` in CorvinOS chat (interactive scaffolding)
2. Or copy this example as a template
3. Modify `manifest.yaml`, `plugin.py`, and tests
4. Submit PR to [Corvin-Marketplace](https://github.com/CorvinLabs/Corvin-Marketplace)

See [Contributing Guide](../../CONTRIBUTING.md) for submission requirements.

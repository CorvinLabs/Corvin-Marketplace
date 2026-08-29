# Plugin Marketplace Architecture

**References:** ADR-0233 (plugin-system), ADR-0243 (boot-layers), ADR-0249 (trust-anchor), ADR-0262 (plugin-builder-v2)

This document describes how Corvin-Marketplace fits into the CorvinOS ecosystem and how plugins flow from development to production use.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Plugin Lifecycle](#plugin-lifecycle)
3. [Trust Model](#trust-model)
4. [Distribution Model](#distribution-model)
5. [Registry System](#registry-system)
6. [Integration with CorvinOS](#integration-with-corvinOS)
7. [Security Boundaries](#security-boundaries)

---

## System Overview

### Five Components

```
┌─────────────────────────────────────────────────────────┐
│ Corvin-Marketplace (this repository)                    │
├─────────────────────────────────────────────────────────┤
│ • plugins/        — Community plugin registry           │
│ • schema/         — JSON schemas (manifests, registry)  │
│ • scripts/        — CLI tools (validate, register)      │
│ • registry.json   — Auto-generated plugin catalog       │
└─────────────────────────────────────────────────────────┘
         ↑                                    ↓
         │                            (daily sync)
         │                                    ↓
┌────────────────────────────────────────────────────────┐
│ CorvinOS Instance (~/.corvin/)                         │
├────────────────────────────────────────────────────────┤
│ • tenants/{tenant}/plugins/registry.yaml  — Local copy │
│ • core/plugins/                           — Core code  │
│ • bootstrap_plugins()                     — Loader     │
└────────────────────────────────────────────────────────┘
         ↑                                    ↑
         │                                    │
         └────────────────────────────────────┘
              (plugin.on_load/health_check)
```

### Conceptual Flow

```
Developer                 Corvin-Marketplace              CorvinOS Instance
    │                            │                              │
    ├─ Write plugin             │                              │
    │  (plugin.py + manifest)    │                              │
    │                            │                              │
    ├─ Local validation         │                              │
    │  (register-plugin.sh)      │                              │
    │                            │                              │
    ├─ Push to GitHub           │                              │
    │                            │                              │
    ├─ Create PR                │                              │
    │                            │                              │
    ├─ CI validates             │                              │
    │  (GitHub Actions)          │                              │
    │                            │                              │
    ├─ Merge to main            │                              │
    │                            │                              │
    │                       ┌─ registry.json generated        │
    │                       │  (CI/CD)                         │
    │                       │                                  │
    │                       ├─ Marketplace UI updated         │
    │                       │                    ├─ Operator discovers
    │                       │                    │  plugin
    │                       │                    │
    │                       │                    ├─ corvin plugin sync
    │                       │                    │  downloads registry
    │                       │                    │
    │                       │                    ├─ registry.yaml
    │                       │                    │  updated
    │                       │                    │
    │                       │                    ├─ corvin plugin install
    │                       │                    │  loads plugin
    │                       │                    │
    │                       │                    ├─ plugin runs
    │                       │                    │  (bootstrapped)
    │                       │                    │
    │                       │                    └─ Audit logged
```

---

## Plugin Lifecycle

### Phase 1: Development

**Location:** Developer's local machine  
**Input:** Problem statement, desired outcome  
**Output:** Plugin code + manifest

**Steps:**

1. **Ideation:** Use `/plugin-builder` in CorvinOS chat (ADR-0262)
   - Interview-driven: problem → solution → scope
   - Auto-generates plugin scaffold

2. **Implementation:** Write `plugin.py` and `manifest.yaml`
   - Implement lifecycle contract (`on_load`, `on_unload`, `health_check`)
   - Implement capability methods (e.g., `route()` for router backends)
   - Write unit tests

3. **Local Testing**
   ```bash
   pytest tests/
   ./scripts/register-plugin.sh --validate .
   ```

### Phase 2: Submission to Marketplace

**Location:** GitHub (Corvin-Marketplace)  
**Input:** Validated plugin from Phase 1  
**Output:** Plugin merged to main, registry.json regenerated

**Steps:**

1. **Fork repository** on GitHub
2. **Create branch:** `git checkout -b add-my-plugin`
3. **Copy plugin:** `cp -r ~/my-plugin ./plugins/`
4. **Commit:** `git add plugins/my-plugin/; git commit -m "Add plugin: ..."`
5. **Push & PR:** GitHub Actions runs:
   - Manifest schema validation
   - Entry point verification
   - Tests (`pytest plugins/my-plugin/tests/`)
   - Code linting (`ruff`)
   - Registry regeneration (dry-run)
6. **Merge to main:** CI regenerates `registry.json` (committed to repo)

### Phase 3: Distribution via Marketplace

**Location:** GitHub (registry.json)  
**Input:** Merged plugin in main branch  
**Output:** registry.json + Marketplace UI indexed

**Steps:**

1. **Registry.json auto-generated** (CI/CD runs `scripts/plugin_registry_manager.py generate`)
2. **Committed to repo** (makes it discoverable via API)
3. **Marketplace UI** lists plugin (within 24h)
4. **Voice discovery** indexes keywords (within 24h)

### Phase 4: Installation at Operator's Site

**Location:** CorvinOS Instance  
**Input:** registry.json from Marketplace  
**Output:** Plugin loaded in process

**Steps:**

1. **Operator discovers plugin:**
   - Marketplace UI search
   - Voice ask: "Show me database plugins"
   - `corvin plugin search <keyword>`

2. **Operator reviews plugin:**
   - Read manifest (`origin`, `boot_layer`, permissions)
   - Check GitHub repo
   - Review code

3. **Operator installs locally** (no network fetching):
   ```bash
   git clone https://github.com/CorvinLabs/Corvin-Marketplace
   cd Corvin-Marketplace/plugins/my-plugin
   corvin plugin install .
   ```

4. **CorvinOS loads plugin:**
   - Validates manifest against registry rules
   - Imports class from entry_point
   - Calls `on_load(ctx)`
   - Health check passes?
   - ✅ Plugin active

5. **Audit logged:**
   - Event: `plugin.installed`
   - Event: `plugin.loaded`
   - Event: `plugin.invoked` (each use)

---

## Trust Model

### Three Provenance Levels (ADR-0249)

```
┌──────────────────────────────────────────────────────────┐
│ Origin: BUILTIN (core plugins only)                      │
├──────────────────────────────────────────────────────────┤
│ • Written by CorvinOS team                               │
│ • Shipped in installation                                │
│ • Non-disableable (compliance boot layer)               │
│ • Examples: bot-disclosure, audit-chain, consent-gate  │
│ • Trust: ✅ Embedded trust (core of OS)                 │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ Origin: VETTED (maintainer-reviewed)                     │
├──────────────────────────────────────────────────────────┤
│ • Community-written, reviewed by maintainer              │
│ • Ed25519-signed by maintainer key                       │
│ • Published in Marketplace                               │
│ • Auto-discoverable, auto-loadable (with consent)       │
│ • Examples: trusted third-party integrations             │
│ • Trust: ✅ Cryptographic (maintainer signature)        │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ Origin: COMMUNITY (unreviewed, self-published)           │
├──────────────────────────────────────────────────────────┤
│ • Community-written, unreviewed                          │
│ • No signature (anyone can generate one)                 │
│ • Published in Marketplace (PR review only)             │
│ • Requires explicit operator opt-in                      │
│ • Must be installed locally (no one-click)              │
│ • Examples: user-owned, custom integrations              │
│ • Trust: ⚠️  Attribution only (PR audit trail)          │
└──────────────────────────────────────────────────────────┘
```

### Signature Verification (for vetted plugins only)

```
Operator's ~/.corvin/global/plugin_trust_anchors.txt
    ↓
    └─ Maintainer's Ed25519 public key (pinned)

Plugin manifest includes:
    signature:
      algorithm: "ed25519"
      public_key: "..." (maintainer's key)
      value: "..." (base64url signature)

Verification (ADR-0249):
    1. Compute SHA256(manifest_content)
    2. Verify signature with pinned public key
    3. ✅ If valid: origin=vetted is trusted
    4. ❌ If invalid: reject (fail-closed)
```

**Community plugins MUST NOT include signature** — if they do, validation rejects them (prevent privilege escalation).

---

## Distribution Model

### Non-Network-Isolated Design (ADR-0248)

**Philosophy:** No one-click installer. Manual installation preserves human review.

**Flow:**

```
Marketplace hosts registry.json
    (via GitHub, not a custom registry server)
                ↓
Operator discovers plugin
    (web UI, voice search, or CLI)
                ↓
Operator manually clones Marketplace repo
    (or downloads plugin ZIP)
                ↓
Operator reviews code
    (GitHub PR history, README, examples)
                ↓
Operator runs: corvin plugin install ./plugins/my-plugin
    (local path only, never remote URL)
                ↓
CorvinOS validates:
    • Manifest schema
    • Entry point exists
    • Plugin type is live
    • No circular dependencies
    • Signature if vetted
                ↓
CorvinOS loads plugin
    (imports class, calls on_load)
```

**Key constraints:**
- ❌ No `corvin plugin install https://...` (network fetch forbidden)
- ❌ No `corvin plugin install my-plugin` (name-based install forbidden)
- ✅ Only `corvin plugin install /local/path/to/plugin`

This preserves the review step and prevents supply-chain compromise.

---

## Registry System

### registry.json Structure

**Location:** `Corvin-Marketplace/registry.json` (committed to repo)

**Auto-generated by:** `scripts/plugin_registry_manager.py generate`

**Regenerated:** Every merge to main (CI/CD)

**Schema:** `schema/registry.v1.json`

**Format:**

```json
{
  "version": "1.0",
  "generated_at": "2026-08-29T14:00:00Z",
  "plugins": {
    "com.example.my-router": {
      "plugin_id": "com.example.my-router",
      "name": "My Router",
      "version": "1.0.0",
      "description": "Routes messages...",
      "author": "Jane Doe",
      "license": "Apache-2.0",
      "entry_point": "plugin.py::MyRouter",
      "plugin_type": "router_backend",
      "origin": "community",
      "boot_layer": "installed",
      "permissions": {...},
      "registered_at": "2026-08-29T14:00:00Z",
      "directory": "plugins/com.example.my-router"
    },
    ...
  }
}
```

### Consumption

**Local instances sync from Marketplace:**

1. **Operator runs:** `corvin plugin sync`
2. **CorvinOS downloads:** `https://github.com/CorvinLabs/Corvin-Marketplace/raw/main/registry.json`
3. **Caches locally:** `~/.corvin/tenants/{tenant}/plugins/registry.yaml`
4. **Voice discovery** indexes keywords
5. **Marketplace UI** queries local copy

**No automatic installation** — operator must explicitly run `corvin plugin install`.

---

## Integration with CorvinOS

### Plugin Loading (corvin_plugins module)

```python
# CorvinOS bootstrap sequence

from corvin_plugins import bootstrap_plugins, validation

# Phase 1: Discover plugins from tenant config
plugins_to_load = load_from_tenant_yaml(tenant_config)

# Phase 2: Validate each plugin
for plugin_spec in plugins_to_load:
    manifest = validation.load_manifest(plugin_spec.manifest_path)
    validation.validate_plugin_record(manifest)
    validation.check_entry_point_importable(manifest)
    # ... more validation

# Phase 3: Import and instantiate
for plugin_spec in plugins_to_load:
    module = importlib.import_module(plugin_spec.module)
    plugin_class = getattr(module, plugin_spec.class_name)
    plugin_instance = plugin_class()

# Phase 4: Load (register with layer)
for plugin_instance in plugins:
    context = build_plugin_context()
    plugin_instance.on_load(context)

# Phase 5: Health check
for plugin_instance in plugins:
    health = plugin_instance.health_check()
    if not health.ok:
        logger.error(f"Plugin unhealthy: {health.message}")
```

### Tenant Configuration

**File:** `~/.corvin/tenants/{tenant}/tenant.corvin.yaml`

```yaml
spec:
  plugins:
    installed:
      - id: "com.example.my-router"
        module: "corvin_marketplace_plugins.my_router"
        class_name: "MyRouterBackend"
        manifest_path: "/path/to/manifest.yaml"
        enabled: true

    # Can declare same plugin multiple times with different configs
    # (rare, but supported for multi-instance use)
```

**Important:** Plugins are declared in tenant config, not auto-discovered from filesystem. This:
- ✅ Makes plugin list explicit and reviewable
- ✅ Allows per-tenant configuration
- ✅ Prevents surprise plugins
- ❌ Requires manual entry (no one-click)

---

## Security Boundaries

### In-Process Plugins Are NOT Sandboxed

**Key invariant:** A plugin has the same privileges as the CorvinOS process.

```python
# DON'T assume this fails:

class MaliciousPlugin:
    def on_load(self, ctx):
        import os
        os.system("rm -rf ~/")  # ← This RUNS (no sandbox)
        
        from core.compliance import audit_chain
        audit_chain.suppress_event()  # ← Modifies core data
        
        import secrets
        print(secrets.token_key)  # ← Leaks secrets
```

**Protections that DO exist:**

1. **Boot tripwire (ADR-0232/0233)**
   - Runs first, independent of plugins
   - Asserts audit chain writer is reachable
   - Fail-closed if audit is broken
   - Non-overridable

2. **Audit trail**
   - Every plugin invocation logged
   - Immutable hash-chain (GDPR Art. 30, 32)
   - Plugin cannot suppress/rewrite core events

3. **Consent gate**
   - Tier-C (community) plugins require explicit operator approval
   - Per-plugin opt-in, not global switch

4. **Governance surface**
   - Console shows plugin permissions (informational)
   - Marketplace tags trust level
   - Operator can disable plugin

**Plugins CANNOT:**
- ❌ Bypass audit chain
- ❌ Suppress/rewrite core events (additive-only for audit backends)
- ❌ Override consent gates
- ❌ Claim higher origin/boot_layer than allowed

**For true containment:** Use separate process or subprocess (ADR-0241).

### Per-Tenant Isolation

All plugin instances are tenant-scoped:

```python
def on_load(self, ctx: PluginContext):
    tenant_id = ctx.current_tenant_id()  # Scoped
    registry = ctx.router_registry       # Tenant-filtered
    
    # Plugin sees only its tenant's events/data
```

Registry queries filter by `tenant_id`:
- Audit trail: `WHERE tenant_id = ?`
- User backend: `WHERE tenant_id = ?`
- Recall backend: `WHERE tenant_id = ?`

---

## References

- **[ADR-0233](https://github.com/CorvinLabs/Corvin-ADR/blob/main/decisions/ADR-0233-plugin-consolidation.md)** — Plugin System Architecture
- **[ADR-0243](https://github.com/CorvinLabs/Corvin-ADR/blob/main/decisions/ADR-0243-plugin-boot-layers.md)** — Boot Layers
- **[ADR-0249](https://github.com/CorvinLabs/Corvin-ADR/blob/main/decisions/ADR-0249-plugin-trust-anchor.md)** — Trust Anchor & Signatures
- **[ADR-0262](https://github.com/CorvinLabs/Corvin-ADR/blob/main/decisions/ADR-0262-plugin-builder-v2.md)** — Plugin-Builder v2
- **[PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md)** — Developer guide
- **[PLUGIN_MANIFEST.md](PLUGIN_MANIFEST.md)** — Manifest field reference
- **[Plugin Registry Manager](../scripts/plugin_registry_manager.py)** — Registry generation tool

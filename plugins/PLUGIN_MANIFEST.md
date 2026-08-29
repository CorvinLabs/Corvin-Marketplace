# Plugin Manifest Specification

**Version:** 1.0  
**References:** [schema/plugin-manifest.v1.json](../schema/plugin-manifest.v1.json), [PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md), ADR-0233/0243/0249

A plugin manifest (`manifest.yaml`) declares the plugin's identity, capabilities, and compliance requirements. It is the source of truth for the plugin's metadata.

---

## Table of Contents

1. [Format Version](#format-version)
2. [Required Fields](#required-fields)
3. [Optional Fields](#optional-fields)
4. [Examples](#examples)
5. [Validation Rules](#validation-rules)
6. [Version Management](#version-management)

---

## Format Version

### `plugin: "1.0"`

**Type:** String  
**Required:** Yes  
**Fixed Value:** `"1.0"`

Specifies the manifest format version. Currently fixed at `"1.0"`. Must be present for forward compatibility.

```yaml
plugin: "1.0"
```

---

## Required Fields

### `id`

**Type:** String (pattern: `^[a-z][a-z0-9-]*(\\.[a-z][a-z0-9-]*)+$`)  
**Required:** Yes  
**Max Length:** 128  
**Default:** None

Globally unique reverse-domain identifier for the plugin. Use reverse-domain naming similar to Java packages:

- ✅ `com.example.my-plugin`
- ✅ `org.corvinlabs.audit-backend`
- ✅ `com.github.username.plugin-name`
- ❌ `my-plugin` (missing reverse-domain prefix)
- ❌ `MY_PLUGIN` (uppercase not allowed)
- ❌ `com..double.dots` (consecutive dots forbidden)

The `id` is also used as the directory name in `plugins/{id}/`, so it must be filesystem-safe.

```yaml
id: "com.example.my-plugin"
```

### `name`

**Type:** String  
**Required:** Yes  
**Length:** 1–80  
**Default:** None

Human-readable display name for the plugin. Shown in UI, logs, and documentation.

```yaml
name: "PostgreSQL Router Backend"
```

### `version`

**Type:** String (SemVer format: `MAJOR.MINOR.PATCH`)  
**Required:** Yes  
**Default:** None

Semantic version indicating plugin version. Follow [semver.org](https://semver.org/):
- Patch (1.0.0 → 1.0.1): Bug fixes, no behavior change
- Minor (1.0.0 → 1.1.0): New features, backward compatible
- Major (1.0.0 → 2.0.0): Breaking changes

Pre-release versions allowed:
- `1.0.0-alpha.1`
- `1.0.0-rc.1`

```yaml
version: "1.0.0"
```

### `description`

**Type:** String  
**Required:** Yes  
**Length:** 10–1000  
**Default:** None

One-paragraph (3–5 sentences) description of the plugin's purpose and key features.

```yaml
description: |
  PostgreSQL router backend for CorvinOS.
  Routes database-related queries to PostgreSQL handlers.
  Supports both read and write operations.
```

### `author`

**Type:** String  
**Required:** Yes  
**Max Length:** 200  
**Default:** None

Plugin author name, organization, or GitHub username.

```yaml
author: "Jane Doe"
# or
author: "ACME Corporation"
# or
author: "github/username"
```

### `license`

**Type:** String (enum)  
**Required:** Yes  
**Default:** None  
**Allowed:** `Apache-2.0`, `MIT`, `GPL-3.0-only`, `GPL-3.0-or-later`, `BSD-3-Clause`, `ISC`

SPDX license identifier. Choose one:

- **`Apache-2.0`** (recommended for CorvinOS plugins) — permissive, requires attribution
- **`MIT`** — permissive, minimal restrictions
- **`GPL-3.0-only`** — copyleft, reciprocal
- **`GPL-3.0-or-later`** — copyleft, allows later GPL versions
- **`BSD-3-Clause`** — permissive, clause-based
- **`ISC`** — permissive, simple

```yaml
license: "Apache-2.0"
```

### `entry_point`

**Type:** String (format: `module.py::ClassName`)  
**Required:** Yes  
**Default:** None

Entry point for the plugin class. Must be importable and point to a class that implements the plugin contract (ADR-0030).

Format: `{module_path}::{class_name}`

- `plugin.py::MyRouter` — class in `plugin.py`
- `backend/router.py::PostgreSQLRouter` — class in `backend/router.py`

The class must implement:
- `on_load(ctx: PluginContext) → None`
- `on_unload() → None`
- `health_check() → HealthStatus`
- Type-specific capability methods (e.g., `route()` for router_backend)

```yaml
entry_point: "plugin.py::MyRouterBackend"
```

---

## Optional Fields

### `email`

**Type:** String (email format)  
**Required:** No  
**Max Length:** 256  
**Default:** None

Contact email for plugin support or questions.

```yaml
email: "jane.doe@example.com"
```

### `homepage`

**Type:** String (URI)  
**Required:** No  
**Max Length:** 512  
**Default:** None

URL to plugin documentation or project homepage.

```yaml
homepage: "https://github.com/example/my-plugin"
```

### `repository`

**Type:** String (URI)  
**Required:** No  
**Max Length:** 512  
**Default:** None

URL to plugin source code repository (GitHub, GitLab, etc.).

```yaml
repository: "https://github.com/example/my-plugin"
```

### `plugin_type`

**Type:** String (enum)  
**Required:** No (see note)  
**Default:** Inferred from entry_point class if possible  
**Allowed:** Router of KNOWN_PLUGIN_TYPES (see [PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md#choosing-your-plugin-type))

Declares which layer extension point this plugin implements. Must be a live plugin type (not dead/unreachable).

```yaml
plugin_type: "router_backend"
```

**Live types:**
- `router_backend` (L5) — message routing
- `notification_backend` (L3+) — event notifications
- `audit_backend` (L16) — audit trail logging
- `summary_provider` (L11) — summary generation
- `recall_backend` (L28) — conversation history

### `origin`

**Type:** String (enum)  
**Required:** No  
**Default:** `"community"`  
**Allowed:** `"builtin"`, `"vetted"`, `"community"`  
**Constraint:** Community plugins MUST be `"community"` (cannot claim other origins)

Declares plugin provenance (ADR-0249):

- **`builtin`** — shipped with CorvinOS core (maintainer only)
- **`vetted`** — community plugin reviewed + signed by maintainer (requires out-of-band signing)
- **`community`** — unreviewed, self-published (default for marketplace submissions)

Community origin means:
- ✅ Operator must explicitly approve before use (consent gate)
- ✅ Listed in marketplace for discovery
- ❌ Cannot declare own trust or make privilege claims
- ❌ Cannot be auto-loaded without operator action

```yaml
origin: "community"
```

### `boot_layer`

**Type:** String (enum)  
**Required:** No  
**Default:** `"installed"`  
**Allowed:** `"compliance"`, `"core"`, `"bundled"`, `"installed"`  
**Constraint:** Community plugins MUST be `"installed"` (only allowed value)

Determines when plugin loads in boot sequence (ADR-0243):

- **`compliance`** — loads first, before core, non-disableable (core compliance plugins only)
- **`core`** — loads after compliance, before bundled (core only)
- **`bundled`** — bundled with install but can be disabled (builtin or vetted)
- **`installed`** — loads last, can be disabled (community plugins, user-declared)

Community plugins can only use `installed` to prevent:
- Replacing core functionality (`compliance`/`core`)
- Disabling without operator awareness (`bundled`)

```yaml
boot_layer: "installed"
```

### `tier`

**Type:** String (enum)  
**Required:** No  
**Default:** Auto-inferred from `origin`  
**Allowed:** `"a"`, `"b"`, `"c"`  
**Constraint:** Determined by `origin` field

Capability tier for licensing (ADR-0156):

- **`"a"`** — core/premium capability (requires paid license, maintainer-only)
- **`"b"`** — vetted community (requires community source, may require tier-b license)
- **`"c"`** — user-owned (free, no license)

Inferred from `origin`:
- `origin: builtin` → `tier: a`
- `origin: vetted` → `tier: b`
- `origin: community` → `tier: c`

Usually omit this field and let it auto-infer.

```yaml
# Do NOT manually set tier; omit it and let origin determine tier
```

### `min_corvin_version` & `max_corvin_version`

**Type:** String (SemVer format) or `null`  
**Required:** No  
**Default:** None (no constraints)

Version constraints for CorvinOS compatibility. Prevents installation on incompatible versions.

```yaml
min_corvin_version: "0.10.0"      # Requires CorvinOS >= 0.10.0
max_corvin_version: "1.0.0"       # Requires CorvinOS < 1.0.0
# max_corvin_version: null        # null = no upper bound
```

### `dependencies`

**Type:** Array of objects  
**Required:** No  
**Default:** `[]` (no dependencies)  
**Constraint:** Circular dependencies detected at validation time

List of other plugins required by this plugin.

```yaml
dependencies:
  - id: "com.example.postgres-lib"
    version: ">=1.0.0,<2.0.0"
  - id: "com.other.base-router"
    version: "^1.5.0"
```

**Version constraints (PEP 440 compatible):**
- `>=1.0.0` — at least 1.0.0
- `>=1.0.0,<2.0.0` — range
- `^1.5.0` — caret (compatible with 1.5.0, e.g., 1.x.y)
- `~1.5.0` — tilde (approximately 1.5.0, e.g., 1.5.x)
- `1.0.0` — exact version

**Circular dependency detection:** Validator checks for A→B→C→A cycles and rejects them.

### `permissions`

**Type:** Object  
**Required:** No  
**Default:** Safe defaults  
**Important:** Informational only, not enforced at runtime

Permission and risk disclosures to inform operator review (governance surface). These are hints for console governance UI, **not** security boundaries.

```yaml
permissions:
  # Network access declaration
  network_egress: []                              # [] = no network
    # or ["db.example.com", "api.example.com"]    # Allowed hosts

  # PII handling risk level
  pii_risk: "low"                                 # none, low, medium, high

  # Data processing locality
  data_locality: "local"                          # local, remote, hybrid

  # Audit logging
  audit_logging: true                             # Always audit plugin invocation
```

**Fields:**

- **`network_egress`** — List of allowed hostnames for outbound network access
  - `[]` (default) → plugin does not access network
  - `["api.example.com"]` → plugin contacts only api.example.com
  - **Note:** This is declarative. Runtime does NOT enforce it.

- **`pii_risk`** — Estimated risk of PII exposure
  - `none` → no PII access
  - `low` → optional PII, encrypted or anonymized
  - `medium` → selective PII access (e.g., email, name)
  - `high` → full PII access (e.g., transcript, raw messages)

- **`data_locality`** — Where data is processed
  - `local` → in-process, in ~/.corvin/
  - `remote` → sent to external service
  - `hybrid` → both local and remote

- **`audit_logging`** — Whether plugin invocations are logged (default: true)

Example:

```yaml
permissions:
  network_egress: ["slack.com"]                   # Sends to Slack
  pii_risk: "medium"                              # May access user names/emails
  data_locality: "remote"                         # Processes in Slack, not locally
  audit_logging: true                             # Every invocation logged
```

### `requires`

**Type:** Array of strings (Python package specs)  
**Required:** No  
**Default:** `[]`

Python package dependencies (requirements.txt format).

```yaml
requires:
  - "psycopg2>=3.0"
  - "requests>=2.28"
  - "pydantic[email]>=1.9"
```

These are also specified in `pyproject.toml` and/or `requirements.txt`, but `requires` in manifest provides a quick reference.

### `keywords`

**Type:** Array of strings  
**Required:** No  
**Default:** `[]`  
**Max Items:** 10  
**Max Length per Keyword:** 50

Search keywords for plugin discovery (marketplace search, voice intent matching).

```yaml
keywords:
  - "postgres"
  - "database"
  - "routing"
  - "sql"
```

### `categories`

**Type:** Array of strings (enum)  
**Required:** No  
**Default:** `[]`  
**Allowed:** `productivity`, `communication`, `data`, `integration`, `security`, `utility`

Plugin categories for browsing in Marketplace and console governance UI.

```yaml
categories:
  - "data"
  - "integration"
```

### `supports_auto_update`

**Type:** Boolean  
**Required:** No  
**Default:** `false`

Whether plugin supports automatic updates (security patches, feature updates).

- `false` (default) → Operator must manually approve updates
- `true` → Updates can be applied automatically after operator opts-in

```yaml
supports_auto_update: true
```

### `health_check_interval`

**Type:** Integer  
**Required:** No  
**Default:** `60`  
**Range:** 1–3600 seconds

Health check polling interval. CorvinOS periodically calls `health_check()` to verify plugin is still responsive.

```yaml
health_check_interval: 30        # Check every 30 seconds
```

### `signature`

**Type:** Object (Ed25519 signature)  
**Required:** No (only for vetted plugins)  
**Default:** None  
**Constraint:** Community plugins must NOT include signature

Optional Ed25519 signature over manifest digest (ADR-0249 Stage 6). Only used for `origin: vetted` plugins to prove authenticity.

**Not for community submission.** Signatures are generated out-of-band by the maintainer after review.

```yaml
# Example (maintainer-generated only)
signature:
  algorithm: "ed25519"
  public_key: "MCowBQYDK2VwAyEA..."  # Base64url-encoded Ed25519 public key
  value: "VVrqNSKd6..."               # Base64url-encoded signature
```

---

## Examples

### Minimal Router Backend

```yaml
plugin: "1.0"
id: "com.example.my-router"
name: "My Router"
version: "1.0.0"
description: "Routes messages based on keywords."
author: "Jane Doe"
license: "Apache-2.0"
entry_point: "plugin.py::MyRouter"
plugin_type: "router_backend"
```

### Full-Featured Audit Backend

```yaml
plugin: "1.0"
id: "com.acme.siem-audit"
name: "ACME SIEM Audit Backend"
version: "2.1.3"
description: |
  Forwards CorvinOS audit trail to ACME SIEM platform.
  Supports real-time streaming, batch sync, and offline queuing.

author: "ACME Security Team"
email: "security@acme.com"
license: "Apache-2.0"
homepage: "https://acme.com/siem/corvin-plugin"
repository: "https://github.com/acme/corvin-siem-plugin"

entry_point: "plugin.py::AcmeSIEMAuditBackend"
plugin_type: "audit_backend"

origin: "community"
boot_layer: "installed"

min_corvin_version: "0.10.0"
max_corvin_version: null

dependencies:
  - id: "com.acme.base-connector"
    version: ">=1.0.0,<2.0.0"

permissions:
  network_egress: ["siem.acme.com"]
  pii_risk: "high"                          # Handles audit events with PII
  data_locality: "remote"                   # Sends to ACME SIEM
  audit_logging: true

requires:
  - "acme-siem-sdk>=3.0"
  - "requests>=2.28"

keywords:
  - "siem"
  - "audit"
  - "acme"
  - "security"

categories:
  - "security"
  - "integration"

supports_auto_update: true
health_check_interval: 60
```

---

## Validation Rules

### Schema Validation

1. **Required fields present:** `plugin`, `id`, `name`, `version`, `description`, `author`, `license`, `entry_point`
2. **Field types correct:** Strings are strings, booleans are booleans, etc.
3. **Enum constraints:** Fields like `plugin_type`, `origin`, `boot_layer` must be from allowed values
4. **Pattern constraints:**
   - `id`: `^[a-z][a-z0-9-]*(\\.[a-z][a-z0-9-]*)+$`
   - `version`: Semantic versioning (X.Y.Z)
   - `license`: SPDX identifier
5. **Length constraints:** Strings within min/max length

### Semantic Validation

1. **Entry point exists:** Class at `entry_point` must be importable and found in `plugin.py`
2. **Plugin type is live:** Type must be actively invoked (not in dead list)
3. **Origin/boot layer consistency:**
   - `origin: community` must have `boot_layer: installed`
   - `origin: builtin` must have `boot_layer: compliance|core|bundled`
4. **Dependency resolution:**
   - All dependencies exist in registry
   - Version constraints are satisfiable
   - No circular dependencies (A→B→C→A)
5. **Signature validity (vetted only):**
   - Signature algorithm must be `ed25519`
   - Public key must be valid base64url
   - Signature must match manifest digest

### Running Validation

```bash
# Local validation
./scripts/register-plugin.sh --validate ./plugins/my-plugin

# Or via CorvinOS CLI
corvin plugin check ./plugins/my-plugin --manifest-path manifest.yaml
```

---

## Version Management

### Versioning Strategy

Follow [semantic versioning](https://semver.org/):

- **Patch (1.0.0 → 1.0.1):** Bug fixes, no breaking changes
- **Minor (1.0.0 → 1.1.0):** New features, backward compatible
- **Major (1.0.0 → 2.0.0):** Breaking changes to API or behavior

### Updating Your Plugin

1. **Increment version** in `manifest.yaml`
2. **Update `pyproject.toml`** and other version refs
3. **Document changes** in `docs/EXAMPLES.md` or `TROUBLESHOOTING.md`
4. **Run tests** to ensure nothing broke
5. **Submit PR** with updated manifest and code

### Deprecation Path

If introducing a breaking change:

1. **v1.0.0** — Original behavior
2. **v1.1.0** — Add new behavior, keep old (deprecation notice)
3. **v2.0.0** — Remove old behavior, require new (breaking change)

Communicate deprecations in `TROUBLESHOOTING.md` and release notes.

---

## References

- **[Plugin Development Guide](PLUGIN_DEVELOPMENT.md)** — How to build and test
- **[JSON Schema](../schema/plugin-manifest.v1.json)** — Machine-readable specification
- **[ADR-0233](https://github.com/CorvinLabs/Corvin-ADR/blob/main/decisions/ADR-0233-plugin-consolidation.md)** — Plugin System
- **[ADR-0243](https://github.com/CorvinLabs/Corvin-ADR/blob/main/decisions/ADR-0243-plugin-boot-layers.md)** — Boot Layers
- **[ADR-0249](https://github.com/CorvinLabs/Corvin-ADR/blob/main/decisions/ADR-0249-plugin-trust-anchor.md)** — Trust Anchor

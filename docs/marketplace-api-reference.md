# Marketplace API Reference (ADR-0511)

**Version:** 2.0 (ADR-0511 Plugin-First Architecture)  
**Base URL:** `https://corvin-marketplace.example.com/api/v1`  
**Status:** Production Ready (Phase 2)

---

## Overview

The Corvin Marketplace API enables external consumers and integrations to discover, query, and manage plugins programmatically. This reference covers all available endpoints for Plugin discovery (Phase 2). Plugin installation is covered in Phase 4.

**Authentication:** Optional (some endpoints may require API key for rate-limit lifting)  
**Rate Limits:** 100 requests/minute (unauthenticated), 1000 requests/minute (authenticated)

---

## Table of Contents

1. [Plugins Endpoints](#plugins-endpoints)
   - [List Plugins](#get-plugins) (`GET /plugins`)
   - [Get Plugin](#get-plugin-details) (`GET /plugins/{id}`)
   - [Plugin Stats](#get-stats) (`GET /stats`)
2. [Filter & Search](#filtering-and-search)
3. [Response Schema](#response-schema)
4. [Plugin Manifest Schema](#plugin-manifest-schema)
5. [Error Codes](#error-codes)
6. [Authentication](#authentication)
7. [Rate Limiting](#rate-limiting)
8. [Examples](#examples)

---

## Plugins Endpoints

### GET /plugins

List all marketplace plugins with optional filtering and pagination.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `category` | string | No | Filter by category: `memory`, `security_compliance`, `integration`, `data_processing`, `observability` |
| `tier` | string | No | Filter by tier: `buildin` or `contributor` |
| `limit` | integer | No | Max results per page (default: 100, max: 1000) |
| `offset` | integer | No | Pagination offset (default: 0) |

**Example Request:**

```bash
curl -X GET "https://corvin-marketplace.example.com/api/v1/plugins?category=memory&tier=buildin&limit=20"
```

**Response (200 OK):**

```json
{
  "plugins": [
    {
      "id": "plugin:buildin-memory-recall_backend",
      "type": "plugin",
      "name": "CEL Session Recall",
      "version": "1.0.0",
      "author": "Anthropic PBC",
      "license": "Apache-2.0",
      "tier": "buildin",
      "category": "memory",
      "description": "Session recall backend providing memory persistence and retrieval.",
      "distribution": {
        "supports_source": true,
        "supports_wheel": true,
        "source_url": "https://github.com/anthropics/CorvinOS/tree/main/core/plugins/corvin_plugins/providers/recall_backend.py",
        "wheel_url": "https://releases.corvinlabs.com/plugins/buildin-memory-recall_backend-1.0.0-py3-none-any.whl"
      },
      "boot_layer": "bundled",
      "sla_level": "buildin"
    }
  ],
  "count": 4,
  "total": 4
}
```

**Status Codes:**

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Invalid query parameters |
| 429 | Rate limit exceeded |

---

### GET /plugins/{id}

Get detailed information about a single plugin.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | Yes | Plugin ID (e.g., `plugin:buildin-memory-recall_backend`) |

**Example Request:**

```bash
curl -X GET "https://corvin-marketplace.example.com/api/v1/plugins/plugin:buildin-memory-recall_backend"
```

**Response (200 OK):**

```json
{
  "id": "plugin:buildin-memory-recall_backend",
  "type": "plugin",
  "name": "CEL Session Recall",
  "version": "1.0.0",
  "author": "Anthropic PBC",
  "license": "Apache-2.0",
  "tier": "buildin",
  "category": "memory",
  "description": "Session recall backend providing memory persistence and retrieval. Implements ADR-0314 learning infrastructure.",
  "readme_url": "https://github.com/anthropics/CorvinOS/blob/main/docs/plugin-developer-guide.md#recall_backend",
  "distribution": {
    "supports_source": true,
    "supports_wheel": true,
    "source_url": "https://github.com/anthropics/CorvinOS/tree/main/core/plugins/corvin_plugins/providers/recall_backend.py",
    "wheel_url": "https://releases.corvinlabs.com/plugins/buildin-memory-recall_backend-1.0.0-py3-none-any.whl",
    "wheel_checksum": "sha256:..."
  },
  "dependencies": [],
  "boot_layer": "bundled",
  "sla_level": "buildin",
  "security_audit": {
    "last_audit_date": "2026-08-31",
    "auditor": "CorvinOS Security Team",
    "findings": 0
  }
}
```

**Status Codes:**

| Code | Description |
|------|-------------|
| 200 | Success |
| 404 | Plugin not found |
| 429 | Rate limit exceeded |

---

### GET /stats

Get marketplace statistics (total plugins, breakdown by category/tier).

**Example Request:**

```bash
curl -X GET "https://corvin-marketplace.example.com/api/v1/stats"
```

**Response (200 OK):**

```json
{
  "total_plugins": 27,
  "by_category": {
    "memory": 4,
    "security_compliance": 6,
    "integration": 5,
    "data_processing": 7,
    "observability": 5
  },
  "by_tier": {
    "buildin": 27,
    "contributor": 3
  },
  "schema_version": "2.0",
  "generated_at": "2026-09-01T00:37:16.023562Z"
}
```

**Status Codes:**

| Code | Description |
|------|-------------|
| 200 | Success |
| 429 | Rate limit exceeded |

---

## Filtering and Search

### Category Filter

Supported categories (per ADR-0511):

| Category | Description | Buildin Count |
|----------|-------------|---------------|
| `memory` | Session memory, user modeling, learning | 4 |
| `security_compliance` | Auth, audit, consent, flow guard | 6 |
| `integration` | Hooks, bridges, cowork hub | 5 |
| `data_processing` | Data classification, PII detection, anonymization | 7 |
| `observability` | Telemetry, heartbeat, diagnostics | 5 |

### Tier Filter

| Tier | Description | License | SLA |
|------|-------------|---------|-----|
| `buildin` | Anthropic-maintained plugins | Apache-2.0 + CLA | 48h bugfix, 24h security |
| `contributor` | Community-maintained plugins | MIT | None (community-driven) |

### Example: Filter by Category and Tier

```bash
curl -X GET "https://corvin-marketplace.example.com/api/v1/plugins?category=security_compliance&tier=buildin"
```

---

## Response Schema

### Plugin Object

```json
{
  "id": "plugin:tier-category-slug",
  "type": "plugin",
  "name": "Display Name",
  "version": "X.Y.Z",
  "author": "Author Name",
  "license": "Apache-2.0 | MIT",
  "tier": "buildin | contributor",
  "category": "memory | security_compliance | integration | data_processing | observability",
  "description": "Human-readable description",
  "readme_url": "https://...",
  "distribution": {
    "supports_source": boolean,
    "supports_wheel": boolean,
    "source_url": "https://...",
    "wheel_url": "https://...",
    "wheel_checksum": "sha256:..."
  },
  "dependencies": ["dep1", "dep2"],
  "boot_layer": "compliance | core | bundled | installed",
  "sla_level": "buildin | community",
  "security_audit": {
    "last_audit_date": "YYYY-MM-DD",
    "auditor": "CorvinOS Security Team",
    "findings": 0,
    "audit_report_url": "https://..."
  },
  "maintainer_url": "mailto:... | https://..."
}
```

### List Response

```json
{
  "plugins": [Plugin, Plugin, ...],
  "count": N,
  "total": N,
  "filtered_by": {
    "category": "string",
    "tier": "string"
  }
}
```

---

## Plugin Manifest Schema

Each plugin must include a `plugin.json` manifest conforming to this schema:

**Required Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique plugin ID (`plugin:tier-category-slug`) |
| `name` | string | Display name |
| `version` | string | Semantic version (X.Y.Z) |
| `author` | string | Author name or org |
| `license` | string | License identifier (`Apache-2.0`, `MIT`) |
| `tier` | string | `buildin` or `contributor` |
| `category` | string | One of 5 categories |
| `description` | string | Short description |

**Optional Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `boot_layer` | string | `compliance`, `core`, `bundled`, `installed` |
| `sla_level` | string | `buildin`, `community` |
| `security_audit` | object | Audit metadata |
| `dependencies` | array | Python package dependencies |
| `distribution` | object | Source & wheel distribution options |

**Validation:**

- Schema validated via `plugin-schema.json` (JSONSchema v7)
- All plugins must pass CI/CD schema validation before indexing

---

## Error Codes

| Code | Description |
|------|-------------|
| 400 | Bad Request (invalid query params) |
| 401 | Unauthorized (invalid API key) |
| 404 | Not Found (plugin does not exist) |
| 429 | Rate Limit Exceeded |
| 500 | Server Error |

**Error Response Format:**

```json
{
  "error": "error_code",
  "message": "Human-readable error message",
  "request_id": "req_xxx"
}
```

---

## Authentication

**Unauthenticated:** 100 requests/minute  
**Authenticated:** 1000 requests/minute

To authenticate, include an `Authorization` header:

```bash
curl -X GET "https://corvin-marketplace.example.com/api/v1/plugins" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

## Rate Limiting

Rate limit status is returned in response headers:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1693458600
```

---

## Examples

### Example 1: Browse All Plugins

```bash
curl -s https://corvin-marketplace.example.com/api/v1/plugins | jq .
```

### Example 2: Find Memory Plugins

```bash
curl -s "https://corvin-marketplace.example.com/api/v1/plugins?category=memory" | jq .plugins[].name
```

### Example 3: Get Plugin Details

```bash
curl -s "https://corvin-marketplace.example.com/api/v1/plugins/plugin:buildin-memory-recall_backend" | jq .
```

### Example 4: Get Marketplace Stats

```bash
curl -s https://corvin-marketplace.example.com/api/v1/stats | jq .by_category
```

### Example 5: Python Integration

```python
import requests

# Fetch all plugins
resp = requests.get('https://corvin-marketplace.example.com/api/v1/plugins')
plugins = resp.json()['plugins']

# Filter by category
security_plugins = [p for p in plugins if p['category'] == 'security_compliance']
print(f"Found {len(security_plugins)} security plugins")

# Get plugin details
plugin_id = security_plugins[0]['id']
details = requests.get(f'https://corvin-marketplace.example.com/api/v1/plugins/{plugin_id}')
print(details.json()['name'])
```

---

## Quick Start

**1. List available plugins:**

```bash
curl -s https://corvin-marketplace.example.com/api/v1/plugins | jq .
```

**2. Filter by category:**

```bash
curl -s "https://corvin-marketplace.example.com/api/v1/plugins?category=memory" | jq .
```

**3. Get plugin details:**

```bash
curl -s "https://corvin-marketplace.example.com/api/v1/plugins/plugin:buildin-memory-recall_backend" | jq .
```

**4. Check marketplace stats:**

```bash
curl -s https://corvin-marketplace.example.com/api/v1/stats | jq .
```

---

## Support & Feedback

- **Issues:** https://github.com/anthropics/CorvinOS/issues
- **Documentation:** https://docs.corvin.io/marketplace
- **API Roadmap:** Phase 3 (Installation), Phase 4 (Full Management)

---

**Last Updated:** 2026-09-01  
**API Version:** 2.0 (ADR-0511)

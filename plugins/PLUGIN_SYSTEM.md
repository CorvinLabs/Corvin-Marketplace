# CorvinOS Plugin System — Architecture & Marketplace

**Last Updated:** 2026-07-27  
**Status:** Production (ADR-0244–0251, ADR-0253, ADR-0254)

---

## 🎯 What is a CorvinOS Plugin?

A **plugin** is an autonomous extension to CorvinOS that adds capabilities without modifying core code.

Plugins integrate through:
- **MCP-Servers** (external tools via Claude Protocol)
- **Skills** (reusable prompt templates, LDD-optimized)
- **Hooks** (event-driven automation)
- **Providers** (storage, auth, user backends)
- **Integrations** (workflow packages, bridge adapters)

---

## 🏗️ Plugin Architecture

### Plugin Capsule (ADR-0254)

Every plugin is a **Capsule** — a self-contained, self-describing unit:

```
my-plugin/
├── plugin.manifest.yaml          ← Plugin Identity
├── voice-commands.yaml           ← Voice Intent Mapping
├── implementation/
│   ├── mcp_server.py             (if MCP-Server type)
│   ├── skill.md                  (if Skill type)
│   ├── hook_handler.py           (if Hook type)
│   ├── requirements.txt
│   └── tests/
├── docs/
│   ├── README.md
│   ├── examples.md
│   └── troubleshooting.md
└── LICENSE (Apache-2.0 or MIT)
```

### Plugin Manifest (`plugin.manifest.yaml`)

```yaml
name: postgres-mcp
version: 1.0.0
type: mcp-server
tier: tier-c
author: jane-doe
license: apache-2.0

# Natural language description (used by Voice-Discovery)
voice_description: |
  PostgreSQL Integration Plugin. Query any Postgres database
  in natural language. Ask "Show me all users" or
  "How many orders this week?"

voice_keywords:
  - postgres
  - database
  - sql
  - query

# Installation requirements
requires:
  - psycopg2>=3.0
  - sqlalchemy

# Auto-discovery metadata
tier_a_review_required: false
audit_logging: true
gdpr_compliant: true

# Plugin health
supports_auto_update: true
support_contact: jane@example.com
```

---

## 📚 Plugin Types (Tier System)

### Tier-A: Core Compliance Plugins
- Written by CorvinOS Team
- Bundled with installation
- Cannot be disabled
- Examples: bot-disclosure, audit-chain, consent-gate

**Discovery:** Always available, auto-loaded

### Tier-B: Vetted Community Plugins
- Community-written, reviewed + signed by CorvinOS
- Marketplace visibility
- Optional; users install explicitly
- Examples: postgres-mcp, slack-adapter, github-skill

**Discovery:** Discoverable via semantic search + ratings

### Tier-C: User-Owned Custom Plugins
- Written by users for their own tenants
- No review required
- Consent-gated in voice/chat
- Examples: internal-reporting-hook, customer-db-integration

**Discovery:** Auto-indexed locally; ask-first when invoked

---

## 🔍 Auto-Discovery (ADR-0254)

### Registry Sync

CorvinOS instances sync daily:
```
corvin-labs.com/plugins/registry.json
  ↓
~/.corvin/plugins/registry.json (local cache)
  ↓
Plugin-Index (semantic embeddings)
```

### Voice Discovery

When user says: `"Query my database"`
```
1. Transcript → CorvinOS Chat-Runtime
2. Voice-Plugin-Index.semantic_search("Query my database")
3. Returns: [postgres-mcp (0.95 similarity), mysql-mcp (0.71)]
4. Tier-C Gate: "Should I use postgres-mcp?"
5. Invoke tool
```

---

## 🛠️ Building Plugins

### Method 1: Plugin-Builder Skill (ADR-0253)

Interactive guided creation:
```
User: /plugin-builder
  ↓
Interview (Problem → Solution → Scope)
  ↓
Auto-Classification
  ↓
Generate: Idea + Architecture + ADRs + Plan + Scaffold
  ↓
Ready to code
```

### Method 2: Template Clone

Clone a template matching your plugin type:
```bash
git clone https://github.com/CorvinLabs/korvin-plugin-template-mcp.git
cd korvin-plugin-template-mcp
# Edit plugin.manifest.yaml + implementation/
# Write tests
# Submit PR to Corvin-Marketplace
```

### Method 3: Manual

Write plugin following ADR-0244–0251 taxonomy. Must include:
- `plugin.manifest.yaml` (self-describing)
- `voice-commands.yaml` (intent mapping)
- Tests (unit + integration)
- Docs (README + examples)
- CLA signature

---

## 🚀 Publishing to Marketplace

### Step 1: Create Repository

```bash
git init my-plugin
cd my-plugin

# Create structure (use Plugin-Builder or clone template)
mkdir implementation docs tests
touch plugin.manifest.yaml voice-commands.yaml
```

### Step 2: Write Plugin

Implement `implementation/` code matching your type:
- **MCP-Server**: `mcp_server.py` + tool definitions
- **Skill**: `skill.md` (markdown prompt template)
- **Hook**: `hook_handler.py` + event subscriptions
- **Provider**: Backend implementation

### Step 3: Test

```bash
pytest tests/
ruff check .
```

### Step 4: Sign CLA

Visit `https://corvin-labs.com/cla` and sign (one-time, per author).

### Step 5: Submit to Marketplace

```bash
cd /home/shumway/projects/Corvin-Marketplace/plugins/
cp -r ~/my-plugin ./my-plugin
git add my-plugin/
git commit -m "Add plugin: my-plugin"
git push origin main
```

Marketplace automation:
1. Validates `plugin.manifest.yaml`
2. Runs plugin tests
3. Checks CLA signature
4. Publishes to registry (24h)
5. Indexes for voice discovery

---

## 📦 Plugin Registry

### What's Published

```json
{
  "my-plugin": {
    "name": "my-plugin",
    "version": "1.0.0",
    "type": "mcp-server",
    "tier": "tier-c",
    "author": "jane-doe",
    "voice_description": "...",
    "voice_keywords": [...],
    "repository": "https://github.com/...",
    "license": "apache-2.0",
    "requires": [...],
    "status": "healthy",
    "installs_30d": 247,
    "rating": 4.8,
    "last_updated": "2026-07-27T14:00Z"
  }
}
```

### Discovery Ranking

Plugins ranked by:
1. **Relevance** (semantic similarity to user query)
2. **Health** (zero failures in last 30d)
3. **Adoption** (installs, ratings, updates)
4. **Recency** (actively maintained)

---

## 🎙️ Voice Integration

Plugins automatically work in voice + all bridges:

```
Discord User: "Show me PostgreSQL data"
  ↓
Bridge: Transcript + Intent
  ↓
CorvinOS: Finds postgres-mcp via semantic search
  ↓
Invokes: /postgres-mcp query_database
  ↓
Result: Text + Voice summary
  ↓
Discord: "Postgres zeigt 2347 Benutzer..."
```

No per-bridge registration needed. One plugin = all bridges.

---

## 🔐 Security & Compliance

### Tier-Based Trust

| Action | Tier-A | Tier-B | Tier-C |
|--------|--------|--------|--------|
| Auto-load | ✅ | ❌ | ❌ |
| Voice auto-invoke | ✅ | ✅ | ⚠️ Ask |
| Audit logged | ✅ | ✅ | ✅ |
| Update auto | ✅ | ⚠️ Warn | ⚠️ Warn |

### Audit Logging (ADR-0232)

Every plugin invocation logged:
```json
{
  "type": "plugin_invoked",
  "plugin_name": "postgres-mcp",
  "plugin_tier": "tier-c",
  "user_consent": true,
  "timestamp": "2026-07-27T14:30:00Z"
}
```

### GDPR Compliance

- Plugin manifests validated (no PII)
- Output redaction (logs never store raw results)
- Consent gating (Tier-C always asks first)
- Erasure on request (ADR-0036 orchestration)

---

## 📊 Marketplace Structure

```
Corvin-Marketplace/
├── plugins/
│   ├── postgres-mcp/
│   │   ├── plugin.manifest.yaml
│   │   ├── voice-commands.yaml
│   │   ├── implementation/
│   │   ├── docs/
│   │   ├── tests/
│   │   └── README.md
│   ├── slack-adapter/
│   ├── github-skill/
│   └── PLUGIN_SYSTEM.md (this file)
├── skills/
│   ├── code-review-skill/
│   └── ...
├── bridge-adapters/
├── forge-tools/
└── README.md
```

---

## 🔗 Related Documentation

- **ADR-0244–0251** — Plugin taxonomy, boot layers, security model
- **ADR-0253** — Plugin-Builder Framework (guided creation)
- **ADR-0254** — Plugin Capsules & Voice Discovery (auto-integration)
- **ADR-0156** — Tier-A/B/C licensing boundaries
- **ADR-0232/0233** — Audit logging + compliance

---

## 🚀 Quick Start

### Publish Your First Plugin

```bash
# 1. Use Plugin-Builder
/plugin-builder
  → Interview
  → Scaffold generated

# 2. Implement
cd ~/my-plugin
# Write implementation/ code
# Write tests/
# Update docs/

# 3. Test locally
pytest tests/
corvin plugin install ~/my-plugin

# 4. Sign CLA (one-time)
# https://corvin-labs.com/cla

# 5. Submit
cp -r ~/my-plugin /home/shumway/projects/Corvin-Marketplace/plugins/
cd /home/shumway/projects/Corvin-Marketplace
git add plugins/my-plugin
git commit -m "Add plugin: my-plugin (Tier-C, MCP-Server)"
git push
```

Discovery + voice integration happens **automatically** within 24h.

---

**Questions?** See `CONTRIBUTING.md` or open an issue in Corvin-ADR.


# Corvin-Knowledge Plugin — Marketplace Registration

**Plugin ID:** `corvin-knowledge`  
**Version:** 1.0.0  
**Status:** Production Ready  
**Category:** knowledge-management  
**License:** Apache-2.0

---

## Overview

**Corvin-Knowledge for Claude Code** is a distributed knowledge management plugin that enables agents and teams to query, sync, and propose knowledge across Git-backed repositories.

**Primary Use Cases:**
1. Query architectural decisions (ADRs) across projects
2. Sync knowledge bases across distributed teams
3. Propose new ideas/concepts via GitHub PRs
4. Multi-team knowledge management with Git-based conflict resolution

---

## Installation

### One-Click (From Marketplace)

```bash
claude code --marketplace install corvin-knowledge@1.0.0
```

### From GitHub Release

```bash
claude code --install-plugin https://github.com/CorvinLabs/Corvin-Knowledge/releases/download/v1.0.0/corvin-knowledge-plugin.zip
```

### From Local

```bash
git clone https://github.com/CorvinLabs/Corvin-Knowledge.git
cd Corvin-Knowledge/sync
claude code --install-plugin .
```

---

## Quick Start

### 1. Configure

```bash
# Use canonical Corvin-Knowledge repo (default)
mesh config

# Or: Use your team's repo
mesh config --repo-path ~/my-team-knowledge --remote-url https://github.com/my-org/knowledge.git
```

### 2. Query

```bash
# Find skills
mesh query --tag=skills

# Find accepted decisions
mesh query --status=accepted

# Find your project's knowledge
mesh query --project=MyProject
```

### 3. Sync

```bash
# Pull latest changes
mesh sync --pull

# Pull + push to remote
mesh sync --pull --push
```

### 4. Propose

```bash
# Submit new idea for review
mesh propose --type=idea \
  --title="My Idea" \
  --body="Detailed description..." \
  --project=CorvinOS
```

---

## Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `mesh query` | Search knowledge | `mesh query --tag=skills --status=accepted` |
| `mesh sync` | Sync with remote | `mesh sync --pull --consistency=strict` |
| `mesh propose` | Submit entity | `mesh propose --type=idea --title="..." --body="..."` |
| `mesh config` | Configure paths | `mesh config --repo-path ~/.my-knowledge` |

---

## Configuration

### Default

```json
{
  "repo_path": "~/.corvin-knowledge/",
  "remote_url": "https://github.com/CorvinLabs/Corvin-Knowledge.git",
  "auto_sync_on_query": true,
  "consistency_level": "warn"
}
```

### Per-Team

```bash
mesh config \
  --repo-path ~/team-a-knowledge \
  --remote-url https://github.com/teams/knowledge.git
```

---

## Architecture

### Three-Layer Design

```
Claude Code Runtime
    ↓
Manifest (manifest.json)
    ↓ Discovery & Command Registration
Plugin Entry (plugin.py::execute)
    ↓ Async Execution
KnowledgeMeshSDK
    ↓ Real Operations
Git + Filesystem
```

### Data Model

- **Entities:** ADRs, Concepts, Ideas, Implementations
- **Storage:** Git repository + JSON Lines index
- **Index:** `~/.corvin-knowledge/graph/entities.jsonl`
- **Sync:** Git 3-way merge with conflict detection

---

## Safety Features

### Consistency Checks (Fail-Closed)

- ✅ Duplicate entity ID detection
- ✅ Circular dependency detection
- ✅ JSON parse validation
- ✅ PII detection (prepared via ADR-0297)

### Consistency Levels

```bash
--consistency=strict  # Abort on any error
--consistency=warn    # Log but continue (default)
--consistency=ignore  # Skip validation (dev only)
```

---

## Troubleshooting

### Plugin Not Found

```bash
# Verify installation
claude code --list-plugins | grep corvin-knowledge

# Reinstall if missing
claude code --uninstall-plugin corvin-knowledge
claude code --install-plugin https://github.com/CorvinLabs/Corvin-Knowledge/releases/download/v1.0.0/corvin-knowledge-plugin.zip
```

### Query Returns Nothing

```bash
# Check configuration
cat ~/.claude/plugins/corvin-knowledge.json

# Force sync to clone/update repo
mesh sync --pull

# Retry query
mesh query
```

### Sync Blocked by Errors

```bash
# See warnings (don't fail)
mesh sync --consistency=warn

# Or ignore validation (dev only)
mesh sync --consistency=ignore
```

---

## Advanced Usage

### Multi-Tenant Deployment

Each team/tenant configures independently:

```bash
# Team A
mesh config --repo-path ~/teams/a-knowledge --remote-url https://github.com/teams/a/knowledge.git

# Team B (different user/machine)
mesh config --repo-path ~/teams/b-knowledge --remote-url https://github.com/teams/b/knowledge.git

# Both sync independently without interference
mesh sync --pull --push
```

### Offline Mode

1. Clone repo once with `mesh sync --pull`
2. Go offline (network disabled)
3. `mesh query` works without network
4. When back online: `mesh sync --pull --push`

### Custom Knowledge Repository

```bash
# Create your repo
mkdir my-team-knowledge
cd my-team-knowledge
git init

# Create structure
mkdir -p graph
echo '[]' > graph/entities.jsonl
echo '[]' > graph/relations.jsonl
echo '{"version": "1.0.0"}' > graph/graph-meta.json

# Commit & push to GitHub
git add .
git commit -m "Initial knowledge repo"
git remote add origin https://github.com/my-org/knowledge.git
git push -u origin main

# Configure plugin
mesh config --repo-path ~/my-team-knowledge --remote-url https://github.com/my-org/knowledge.git
```

---

## System Requirements

- **Claude Code** (latest version)
- **Python 3.9+**
- **Git 2.25+**

---

## Testing

### Unit Tests

```bash
cd /path/to/plugin
pytest tests/test_plugin_corvin_knowledge_wiring.py -v
# Expected: 15 passed
```

### E2E Tests

- Plugin reachability (Claude Code discovery)
- Query from real entities.jsonl
- Sync with real Git operations
- Consistency validation (fail-closed)
- Multi-command workflows

---

## Performance

| Operation | Time | Notes |
|-----------|------|-------|
| Query | <100ms | JSON Lines scan |
| Sync | 2-5s | Full pull + merge + rebuild |
| Propose | <1s | Creates local branch (GitHub PR async) |
| Config | <1ms | File I/O |

---

## Roadmap

### v1.1 (Planned)

- [ ] Real GitHub API (create PRs programmatically)
- [ ] Full PII detection + quarantine (ADR-0297)
- [ ] Full-text search command

### v1.2 (Planned)

- [ ] Web dashboard (visualize knowledge graph)
- [ ] Real-time sync (WebSocket support)
- [ ] Merge conflict auto-resolver (ML-assisted)

### v2.0 (Roadmap)

- [ ] MCP tool integration
- [ ] Slack/Discord integration
- [ ] GitHub Actions workflow
- [ ] Offline mode improvements

---

## Support

- **GitHub Issues:** https://github.com/CorvinLabs/Corvin-Knowledge/issues
- **Discussions:** https://github.com/CorvinLabs/Corvin-Knowledge/discussions
- **Documentation:** https://github.com/CorvinLabs/Corvin-Knowledge/blob/main/README.md

---

## Related ADRs

- **ADR-0884** — Claude Code Plugin Integration (CorvinOS)
- **ADR-MESH-002** — Plugin Contract & Distribution (canonical)
- **ADR-0262/0263** — Plugin-Builder v2 (how to author plugins)
- **ADR-0671** — Knowledge Graph Builder (tenant isolation)
- **ADR-0519** — Self-Extending Knowledge Graph (learning loop)

---

## License

Apache-2.0 (same as Corvin-Knowledge)

**Source:** https://github.com/CorvinLabs/Corvin-Knowledge  
**Plugin Repository:** https://github.com/CorvinLabs/Corvin-Marketplace/tree/main/plugins/knowledge-management/corvin-knowledge

---

**Status:** ✅ Production Ready (v1.0.0)  
**Last Updated:** 2026-09-18  
**Maintainer:** Shumway + Claude Haiku 4.5

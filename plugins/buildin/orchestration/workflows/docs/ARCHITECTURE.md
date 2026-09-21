# Workflows Plugin Architecture

**Status:** Phase 1 Complete (2026-09-21)  
**Scope:** Extract `/core/console/corvin_console/routes/workflows.py` → Standalone Plugin  
**Related:** ADR-0039 (Workflow Builder), ADR-0648 (Prompt Guard), ADR-0233 (Plugin System)

---

## Overview

The Workflows Plugin provides orchestration and automation capabilities for CorvinOS. It enables users to:
- Design multi-step workflows using YAML-based AWP (Agentic Workflow Protocol)
- Execute workflows with multiple node types (Claude, delegation, fan-out, deliver)
- Manage workflow runs with approval gates, pausing, and resumption
- Schedule workflows via cron (Phase 4)
- Export/import workflows as AWPKG bundles (Phase 5)
- Design workflows interactively via chat assistant (Phase 7)

---

## Architecture Layers

### Layer 1: Adapter Layer (Decoupling Console Dependencies)

**Purpose:** Isolate plugin from CorvinOS console-specific imports. Enables plugin to function standalone while optionally integrating with console.

| Adapter | Console Dependency | Plugin Wrapper | Graceful Fallback |
|---------|-------------------|-----------------|-------------------|
| `audit.py` | `corvin_console.audit` | `audit_backend: AuditBackend` | No-op logger |
| `session.py` | `corvin_console.auth` + `session_auth` | `session_record: SessionRecord` | Deny (no auth) |
| `spawn_gates.py` | `corvin_console._spawn_gates` | `prompt_guard: PromptGuard` | Pass-through (unsafe, logged) |
| `license.py` | `corvin_operator.license.validator` | `license_backend: LicenseBackend` | FREE_TIER defaults |
| `scheduler.py` | `corvin_operator.bridges.shared.scheduler` (Phase 4) | `scheduler_backend: SchedulerBackend` | No-op (unscheduled) |
| `storage.py` | `forge.paths.tenant_home()` | `storage_backend: StorageBackend` | Memory (per-session, no persistence) |

**Implementation Pattern:**
```python
# adapters/audit.py
class AuditBackend(Protocol):
    def log_event(self, event_type: str, **payload) -> None: ...

class ConsoleAuditBackend(AuditBackend):
    """Wraps console_audit.log_event()"""
    
class NoOpAuditBackend(AuditBackend):
    """When console_audit unavailable"""
```

### Layer 2: Routes Modularization

**Purpose:** Split monolithic `workflows.py` (4541 lines) into 7 focused modules.

| Module | Handlers | LOC |
|--------|----------|-----|
| `routes/crud.py` | GET/POST /workflows, GET/PATCH/DELETE /workflows/{wid} | ~600 |
| `routes/yaml.py` | GET/PUT /workflows/{wid}/yaml | ~300 |
| `routes/runs.py` | POST/GET/DELETE /workflows/{wid}/runs{,/{rid}} | ~800 |
| `routes/schedule.py` | GET/PUT/DELETE /workflows/{wid}/schedule (Phase 4) | ~200 |
| `routes/export.py` | GET /workflows/{wid}/export.awpkg (Phase 5) | ~150 |
| `routes/import_workflows.py` | POST /workflows/import (Phase 5) | ~250 |
| `routes/chat.py` | WS /workflows/{wid}/chat (Phase 7) | ~300 |

**Module Dependencies:**
```
crud.py → (depends on) storage.py + audit.py
yaml.py → crud.py + corvin_workflows.validator
runs.py → crud.py + execution/node_runner.py + approval logic
schedule.py → crud.py + scheduler.py (soft)
export.py → crud.py + awpkg/exporter.py (soft)
import_workflows.py → crud.py + awpkg/importer.py (soft)
chat.py → crud.py + corvin_skills (LLM-guided design)
```

### Layer 3: Execution Engine

**Purpose:** Abstract workflow execution from route handlers.

| Module | Responsibility |
|--------|-----------------|
| `execution/node_runner.py` | Single-node execution (Claude, delegation, fan-out, deliver) |
| `execution/delegation_loop.py` | Delegation node with LLM-loop coordination |
| `execution/fan_out.py` | Fan-out node (parallel task dispatch) |
| `execution/deliver.py` | Deliver node (voice + webhook output) |
| `execution/checkpoint.py` | State persistence + resumption |

### Layer 4: AWP Stack Integration

**Purpose:** Thin wrappers around `corvin_workflows` (hard dependency).

| Module | Wraps | Purpose |
|--------|-------|---------|
| `graph/parser.py` | `corvin_workflows.load_workflow()` | YAML → WorkflowDoc |
| `graph/topology.py` | Kahn's algorithm | DAG validation + topological sort |
| `graph/ascii_renderer.py` | Graphviz/ASCII rendering | Console output for flow visualization |
| `engines/claude_engine.py` | `ClaudeCliEngine` | Spawn `claude -p` with prompt guard |

### Layer 5: Data Model

**File Layout (per tenant):**
```
~/.corvin/tenants/_default/workflows/
  ├── <wid>.awp.yaml              # Workflow YAML (WorkflowDoc)
  ├── <wid>.meta.json             # Metadata: title, description, created_at, updated_at
  ├── <wid>.chat.jsonl            # Design session history (APPEND-ONLY)
  ├── <wid>/runs/
  │   ├── <rid>.meta.json         # Run metadata: status, started_at, node_checkpoints
  │   ├── <rid>.jsonl             # Run event log (NOT in audit chain per ADR-0039)
  │   └── <rid>.approval.json     # HITL approval state per node
  ├── <wid>.schedule.json         # Cron config (Phase 4)
  └── <wid>.lock                  # Bounded file lock (LOCK_EX, 2s timeout)
```

**Metadata Schema (`.meta.json`):**
```json
{
  "title": "My Workflow",
  "description": "What it does",
  "status": "DRAFT|ACTIVE|PAUSED",
  "created_at": "2026-09-01T12:00:00Z",
  "updated_at": "2026-09-01T12:00:00Z",
  "phase": "Phase 1|2|3|4|5|6|7",
  "node_count": 5,
  "license_tier": "pro|enterprise"
}
```

---

## Security & Compliance

### ADR-0648: Prompt Guard (Mandatory)

**All Claude node payloads** pass through `_guard_prompt_head()` before spawn:
- Blocks `/`, `!`, `#` at byte 0
- Blocks `@<path>` ANYWHERE
- Fails CLOSED: guard unavailable → RuntimeError (no bypass)

**Integration:** `execution/claude_engine.py` wraps every spawn.

### ADR-0232/0233: Audit Trail

**Workflow Events Audited:**
- `workflow.created`, `workflow.updated`, `workflow.deleted`
- `workflow.run.started`, `workflow.run.completed`, `workflow.run.failed`
- `workflow.run.approved`, `workflow.run.paused`, `workflow.run.resumed`
- `workflow.yaml.updated`

**Non-Audited** (per ADR-0039):
- Run event log (`.jsonl`) — for performance, not audit trail

### Tenant Isolation (GDPR Art. 5, 6, 32)

**All operations scoped by `tenant_id`:**
- Storage: `<tenant_home>/workflows/` (via `storage_backend`)
- Audit: `tenant_id` in every audit event
- Session: `SessionRecord.tenant_id` mandatory (fail-closed if missing)

---

## Soft Dependencies & Graceful Degradation

| Module | Feature | Fallback | Status |
|--------|---------|----------|--------|
| `yaml` (PyYAML) | YAML parsing | Empty graph `[]` (graphs unavailable) | Phase 1 |
| `corvin_workflows` (AWP) | Execution engine | Return 503 (workflows unavailable) | Hard dep actually |
| `license.validator` | License gating | FREE_TIER: limit workflows_concurrent | Phase 2 |
| `scheduler` | Cron scheduling | Log warning, return 400 (scheduling unavailable) | Phase 4 |
| `awpkg.builder` | AWPKG export | Return 503 (export unavailable) | Phase 5 |
| `voice/scripts` | TTS on chat WS | Omit audio, return text only | Phase 7 |

---

## Plugin Manifest (`plugin.json`)

```json
{
  "id": "orchestration.workflows",
  "version": "1.0.0",
  "name": "Workflow Builder",
  "description": "Design and execute multi-step automation workflows",
  "boot_layer": "bundled",
  "entry_point": "plugin_workflows:WorkflowsPlugin",
  "web_routes": [
    "GET /workflows",
    "POST /workflows",
    "GET /workflows/{wid}",
    "PATCH /workflows/{wid}",
    "DELETE /workflows/{wid}",
    "GET /workflows/{wid}/yaml",
    "PUT /workflows/{wid}/yaml",
    "POST /workflows/{wid}/runs",
    "GET /workflows/{wid}/runs",
    "GET /workflows/{wid}/runs/{rid}",
    "DELETE /workflows/{wid}/runs/{rid}",
    "GET /workflows/{wid}/schedule",
    "PUT /workflows/{wid}/schedule",
    "DELETE /workflows/{wid}/schedule",
    "GET /workflows/{wid}/export.awpkg",
    "POST /workflows/import",
    "WS /workflows/{wid}/chat"
  ],
  "ui_navigation": [
    {
      "label": "Workflows",
      "path": "/app/workflows",
      "icon": "workflow"
    }
  ],
  "audit_events": [
    "workflow.created",
    "workflow.updated",
    "workflow.deleted",
    "workflow.run.started",
    "workflow.run.completed",
    "workflow.run.failed"
  ],
  "feature_flags": [
    "workflows_enabled",
    "workflows_export_enabled",
    "workflows_scheduling_enabled"
  ],
  "dependencies": {
    "hard": ["corvin_workflows", "fastapi", "pydantic", "forge"],
    "soft": ["yaml", "scheduler", "awpkg", "skill-forge", "voice"]
  }
}
```

---

## Migration Path

**Phase 6 (Cutover):**
1. Plugin routes mounted alongside console routes (dual-running)
2. Console routes forward to plugin via HTTP client
3. Validation: Both paths return identical results
4. Switch: Remove console routes, keep plugin-only

**Rollback:** Revert to console routes if plugin fails to load.

---

## Testing Strategy (Phase 5)

| Level | Coverage | Count |
|-------|----------|-------|
| Unit | Adapters, parsers, validators | 25 tests |
| Integration | CRUD workflows, run lifecycle | 20 tests |
| E2E | Create → Edit → Run → Approve | 10 tests |
| Regression | Ensure console routes unchanged | 15 tests |
| **Total** | **≥85% coverage on critical paths** | **≥70 tests** |

---

## Phase Roadmap

| Phase | Focus | Duration | Status |
|-------|-------|----------|--------|
| **1** | Architecture + adapters | Day 1 | ✅ In Progress |
| **2–3** | Backend extraction + modularization | Days 1–2 | 🟡 Blocked on Phase 1 |
| **4** | Frontend extraction | Day 3 | 🔴 Blocked |
| **5** | Testing (unit, integration, E2E) | Days 3–4 | 🔴 Blocked |
| **6** | Cutover (dual-running, migration) | Day 4 | 🔴 Blocked |
| **7** | Stabilization (perf, security, deps) | Day 5 | 🔴 Blocked |
| **8** | Sign-off (checklists, ADR, deployment) | Day 5 | 🔴 Blocked |

---

**Next:** Phase 2–3 → Implement adapters and extract backend routes.

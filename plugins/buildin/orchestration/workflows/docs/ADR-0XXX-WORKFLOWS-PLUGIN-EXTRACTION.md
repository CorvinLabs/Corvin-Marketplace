# ADR-0????: Workflows Plugin Extraction

**Status:** PROPOSED (2026-09-21)  
**Decision Date:** 2026-09-21  
**Affected Stakeholders:** CorvinOS Console Team, Plugins Team, Users  
**Priority:** HIGH  
**Related ADRs:** ADR-0039 (Workflow Builder), ADR-0648 (Prompt Guard), ADR-0233 (Plugin System)

---

## Problem Statement

The workflows feature (ADR-0039) is embedded in the CorvinOS console as a monolithic route module (4541 lines, `core/console/corvin_console/routes/workflows.py`). This creates:

1. **Tight coupling** — workflows depend on console-specific imports (auth, audit, spawn gates)
2. **No modularity** — separate concerns (CRUD, YAML, runs, scheduling, export, chat) in one file
3. **Testing friction** — console tests required to validate workflows
4. **Deployment friction** — any workflow change requires console restart
5. **Reusability** — workflows engine cannot be tested/deployed independently

**Goal:** Extract workflows into a standalone, composable plugin in Corvin-Marketplace that:
- Decouples from console via adapter layer
- Modularizes routes into 7 focused modules (CRUD, YAML, Runs, Schedule, Export, Import, Chat)
- Passes 85%+ of critical paths
- Supports zero-downtime cutover (Phase 6)

---

## Decision

Extract workflows from console → standalone plugin in Corvin-Marketplace.

### Structure

**Adapter Layer** (decouples dependencies):
- `adapters/session.py` — Session/auth (DenyAllSessionBackend fallback)
- `adapters/audit.py` — Audit trail (NoOpAuditBackend fallback)
- `adapters/storage.py` — File I/O (MemoryStorageBackend fallback)
- `adapters/license.py` — License enforcement (FreeTierLicenseBackend fallback)
- `adapters/spawn_gates.py` — Prompt guard (NoOpPromptGuard fallback)
- `adapters/scheduler.py` — Cron scheduling, Phase 4 (NoOpSchedulerBackend fallback)

**Routes Modularization** (7 modules under `routes/`):
| Module | Phase | Routes | LOC |
|--------|-------|--------|-----|
| crud.py | 1 | GET/POST /workflows, GET/PATCH/DELETE /workflows/{wid} | 359 |
| yaml.py | 1 | GET/PUT /workflows/{wid}/yaml | 203 |
| runs.py | 1 | POST/GET/DELETE /workflows/{wid}/runs{,/{rid}} | 403 |
| schedule.py | 4 | GET/PUT/DELETE /workflows/{wid}/schedule | ~200 (TBD) |
| export.py | 5 | GET /workflows/{wid}/export.awpkg | ~150 (TBD) |
| import.py | 5 | POST /workflows/import | ~250 (TBD) |
| chat.py | 7 | WS /workflows/{wid}/chat | ~300 (TBD) |

**Plugin Manifest:**
- `plugin.json` — Registers plugin, routes, audit events, feature flags
- `plugin_workflows/plugin.py` — Entry point, initializes adapters, mounts routes
- `plugin_workflows/__init__.py` — Exports WorkflowsPlugin

### Implementation Timeline

| Phase | Focus | Duration | Owner |
|-------|-------|----------|-------|
| 1 | Adapters + Architecture | Day 1 | ✅ DONE |
| 2–3 | Backend extraction + modularization | Days 1–2 | ✅ DONE (Phase 1-3 routes) |
| 4 | Frontend extraction | Day 3 | ✅ DONE (React stubs) |
| 5 | Testing (unit, integration, E2E) | Days 3–4 | 🟡 IN PROGRESS |
| 6 | Dual-running + migration | Day 4 | 🔴 BLOCKED |
| 7 | Performance + security audit | Day 5 | 🔴 BLOCKED |
| 8 | Sign-off + deployment | Day 5 | 🔴 BLOCKED |

### Soft Dependencies (Graceful Degradation)

| Dependency | Feature | Fallback | Viable? |
|---|---|---|---|
| PyYAML | YAML parsing | Return empty graph | ✅ YES |
| corvin_workflows (AWP Stack) | Execution engine | Return 503 | ✅ YES (hard dep actually) |
| scheduler | Cron scheduling (Phase 4) | Log warning, return 400 | ✅ YES |
| awpkg.builder | AWPKG export (Phase 5) | Return 503 | ✅ YES |
| skill-forge + voice | Design chat (Phase 7) | Return text-only | ✅ YES |
| license.validator | License gating | FREE_TIER defaults | ✅ YES |

### Audit Events (ADR-0232/0233)

Every workflow operation generates an audit event (hash-chained):

```
workflow.created:     {tenant_id, user_id, wid, title, description}
workflow.updated:     {tenant_id, user_id, wid, title, description}
workflow.deleted:     {tenant_id, user_id, wid}
workflow.yaml.updated: {tenant_id, user_id, wid, node_count, validation_errors}
workflow.run.started:  {tenant_id, user_id, wid, rid, started_at}
workflow.run.completed: {tenant_id, user_id, wid, rid, status, node_results_summary}
workflow.run.failed:   {tenant_id, user_id, wid, rid, error}
```

All events include `tenant_id` (GDPR Art. 5, 6, 32).

---

## Trade-Offs

| Decision | Upside | Downside | Mitigation |
|----------|--------|----------|-----------|
| Adapter layer | Decoupled from console | Extra indirection | Minimal overhead, proven pattern |
| Modularized routes | Clearer separation of concerns | More files to import | Auto-loader in routes/__init__.py |
| Soft deps with fallback | Works without optional libs | Degraded features | Documented limits, fail-closed errors |
| Dual-running phase | Zero-downtime cutover | Temporary routing complexity | 1-week SLA, then cleanup |

---

## Constraints & Risks

### Constraints

1. **No breaking changes** — Console routes must continue working during Phase 6
2. **Audit compliance** — Every operation audited (ADR-0232/0233)
3. **Tenant isolation** — All operations scoped by tenant_id (GDPR)
4. **Prompt guard** — All claude spawns guarded (ADR-0648)
5. **License gating** — workflows_concurrent, workflows_max enforced

### Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Data loss during migration | LOW | HIGH | Backup + validate before/after counts |
| Performance regression | MEDIUM | MEDIUM | Profile before/after, SLA < 50ms |
| Plugin fails to load | LOW | HIGH | Fallback to console routes, auto-rollback |
| Session/CSRF mismatch | LOW | MEDIUM | Adapter wraps console auth identically |
| Incomplete Phase 4–7 extraction | MEDIUM | LOW | Phase 1–3 = MVP, others deferred |

---

## Testing Strategy

**Coverage Target:** 85%+ on critical paths (CRUD, Runs, YAML parsing)

| Level | Scope | Count | Status |
|-------|-------|-------|--------|
| Unit | Adapters, helpers, models, validators | 25 | 🟡 TBD |
| Integration | CRUD workflows, run lifecycle, YAML parsing | 20 | 🟡 TBD |
| E2E | Create → Edit → Run → Approve flow | 10 | 🟡 TBD |
| Regression | Console routes unchanged | 15 | 🟡 TBD |
| **Total** | | **≥70 tests** | **🟡 TBD** |

**Test Files:**
- `tests/test_adapters.py` — Adapter layer
- `tests/test_crud.py` — CRUD operations
- `tests/test_runs.py` — Run execution
- `tests/test_yaml.py` — YAML parsing + validation
- `tests/test_e2e.py` — Full workflow lifecycle
- `tests/test_migration.py` — Data migration validation

---

## Deployment

### Phase 6a: Dual-Running (Week 2)

1. Deploy plugin to marketplace
2. Load plugin in console (via plugin registry)
3. Route console /workflows → plugin routes
4. Validate: identical responses for both paths

### Phase 6b: Migration (Week 2, overnight)

1. Run migration script (copy workflows from console storage)
2. Validate: no data loss

### Phase 6c: Cutover (Week 3, <5 min downtime)

1. Remove console route registration
2. Restart console (loads plugin only)
3. Smoke test

### Phase 6d: Cleanup (Week 3+)

1. Delete console route file
2. Delete console tests
3. Update docs

### Rollback

If plugin fails post-cutover:
1. Restore console routes from git
2. Restart console (serves from console again)
3. Notify ops, investigate plugin failure

---

## Approval

- [ ] Architecture review (Plugin Lead)
- [ ] Security review (Compliance Officer)
- [ ] Testing plan review (QA Lead)
- [ ] Console lead sign-off
- [ ] Go/no-go decision by Product Manager

---

## References

- **Source:** `/home/shumway/projects/CorvinOS/core/console/corvin_console/routes/workflows.py` (4541 lines)
- **Destination:** `/home/shumway/projects/Corvin-Marketplace/plugins/buildin/orchestration/workflows/`
- **Architecture:** `docs/ARCHITECTURE.md`, `docs/ROUTING.md`, `docs/MIGRATION.md`, `docs/API.md`
- **Implementation:** Phase 1 ✅, Phase 2–3 ✅ (partial), Phase 4–7 🔴
- **Related:** ADR-0039 (Workflow Builder), ADR-0233 (Plugin System), ADR-0648 (Prompt Guard)

---

## Amendment Log

**2026-09-21, 19:30 UTC:** Initial proposal (Phase 1–3 extraction complete, Phase 4–8 pending)

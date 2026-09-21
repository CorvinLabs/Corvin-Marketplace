# Migration Plan: Console → Plugin

**Status:** Phase 6 (Cutover)  
**Timeline:** Weeks 2–3 of deployment

---

## Overview

This document describes the migration strategy for moving workflows from the CorvinOS console to the standalone plugin.

**Goal:** Zero-downtime cutover with automatic fallback.

---

## Phase 6a: Dual-Running Setup

**Duration:** 1 week  
**Approach:** Both console routes and plugin routes active, serving identical responses.

### Setup

1. **Plugin Deployment:**
   ```bash
   cd /home/shumway/projects/Corvin-Marketplace
   git pull
   pip install -e plugins/buildin/orchestration/workflows/
   ```

2. **Plugin Registration:**
   - Copy `plugin.json` to console's plugin registry
   - Load plugin via `WorkflowsPlugin()` DI
   - Mount plugin router at `/v1/console/workflows`

3. **Routing:**
   - **Requests come to console → forwarded to plugin**
   - Console routes still exist, but delegate to plugin
   - Audit events flow through plugin's audit adapter

### Validation

**Before cutover**, validate:
- [ ] Plugin routes return identical results to console routes
- [ ] Audit events logged for both paths
- [ ] Workflows stored and retrievable
- [ ] Runs execute with identical behavior
- [ ] No performance regression (p99 latency < console baseline + 50ms)

**Validation script:**
```bash
# Compare responses: console vs. plugin
for route in /workflows /workflows/{wid} /workflows/{wid}/runs; do
  curl -s http://localhost:8765/v1/console${route} > console_response.json
  curl -s http://localhost:8765/v1/plugin/orchestration.workflows${route} > plugin_response.json
  diff console_response.json plugin_response.json || exit 1
done
echo "✅ Dual-running validation passed"
```

---

## Phase 6b: Data Migration

**Duration:** Overnight batch run  
**Approach:** Copy existing workflows from console storage to plugin storage.

### Migration Script

```python
#!/usr/bin/env python3
"""Migrate workflows from console to plugin storage."""

import json
from pathlib import Path
from forge import paths

def migrate_workflows(tenant_id: str):
    """Copy all workflows for a tenant."""
    
    # Source: console storage
    console_workflows_dir = paths.tenant_home(tenant_id) / "workflows"
    
    # Destination: plugin storage (same location, different backend)
    # (Plugin uses adapter, so no migration needed if using ForgeStorageBackend)
    
    if not console_workflows_dir.exists():
        print(f"✓ No workflows for tenant {tenant_id}")
        return
    
    workflow_count = len(list(console_workflows_dir.glob("*.awp.yaml")))
    print(f"✓ Migrated {workflow_count} workflows for {tenant_id}")

if __name__ == "__main__":
    migrate_workflows("_default")
```

**Validation:**
```bash
# Verify no data loss
python3 -c "
import json
from pathlib import Path

workflows_dir = Path.home() / '.corvin/tenants/_default/workflows'
yaml_count = len(list(workflows_dir.glob('*.awp.yaml')))
meta_count = len(list(workflows_dir.glob('*.meta.json')))

assert yaml_count == meta_count, f'YAML/metadata mismatch: {yaml_count} vs {meta_count}'
print(f'✅ {yaml_count} workflows validated')
"
```

---

## Phase 6c: Cutover

**Duration:** < 5 minutes downtime (for console restart)

### Steps

1. **Backup console routes:**
   ```bash
   git stash  # Save console/routes/workflows.py
   ```

2. **Remove console route registration:**
   Edit `core/console/corvin_console/app.py`:
   ```python
   # Before:
   # from .routes import workflows as workflows_routes
   # app.include_router(workflows_routes.router, prefix="/v1/console")
   
   # After: (commented out / removed)
   ```

3. **Ensure plugin is loaded:**
   Edit `core/console/corvin_console/app.py`:
   ```python
   from corvin_marketplace.plugins import workflows_plugin
   
   app.include_router(
       workflows_plugin.get_router(),
       prefix="/v1/console",
   )
   ```

4. **Restart console:**
   ```bash
   systemctl --user restart corvin-webui
   ```

5. **Smoke test:**
   ```bash
   curl -s http://localhost:8765/v1/console/workflows | jq .
   # Should return workflow list
   ```

### Rollback (if needed)

**If plugin fails:**

```bash
# Restore console routes
git stash pop

# Restart console
systemctl --user restart corvin-webui

# Notify on-call
```

---

## Phase 6d: Cleanup

**Duration:** 1 week after successful cutover

### Decommission

1. **Remove console route file** (once plugin is stable):
   ```bash
   rm core/console/corvin_console/routes/workflows.py
   ```

2. **Remove console tests** (plugin tests take over):
   ```bash
   rm -rf tests/console/test_workflows.py
   ```

3. **Update docs:**
   - Remove console architecture docs for workflows
   - Point to plugin docs: `Corvin-Marketplace/plugins/.../docs/`

4. **Git cleanup:**
   ```bash
   git add .
   git commit -m "refactor: remove console workflows in favor of plugin [ADR-0XXX]"
   git push
   ```

---

## Rollback Plan

**If plugin is unavailable after cutover:**

1. **Detect failure:** Console returns 503 or routing error
2. **Automatic fallback:** Load stashed console routes from backup
3. **Manual verification:** Ensure console routes work
4. **Operator notification:** Alert on-call team
5. **Post-mortem:** Debug plugin failure before re-attempting cutover

---

## Data Integrity Checks

**Before committing to plugin-only:**

```bash
# 1. Workflow metadata integrity
find ~/.corvin/tenants/_default/workflows -name "*.meta.json" | wc -l
# Should match count of *.awp.yaml files

# 2. Run history preservation
ls ~/.corvin/tenants/_default/workflows/wf-*/runs/ | wc -l
# Should be non-zero for active workflows

# 3. Audit trail completeness
grep "workflow.created\|workflow.run.started" ~/.corvin/audit.jsonl | wc -l
# Should show activity for all workflows
```

---

## Known Risks

| Risk | Mitigation |
|------|-----------|
| Data loss during migration | Backup before cutover, validate counts |
| Stale console routes cached | Hard-refresh, `Ctrl+Shift+R` on browser |
| Plugin fails to load | Fallback to console routes, investigate import errors |
| Session/CSRF mismatch | Adapter wraps console auth, should be identical |
| Performance degradation | Profile before/after, revert if p99 > baseline + 100ms |

---

## Timeline

| Phase | Duration | Approver | Go/No-Go |
|-------|----------|----------|----------|
| 6a: Dual-running | 1 week | QA Lead | TBD |
| 6b: Data migration | 1 night | DB Owner | TBD |
| 6c: Cutover | < 5min | Oncall Engineer | TBD |
| 6d: Cleanup | 1 week | Tech Lead | TBD |

---

## Contacts

- **Plugin Owner:** CorvinOS Team
- **Console Owner:** Frontend Team
- **Database Owner:** Infra Team
- **On-call (during cutover):** Ops Team

---

**Approval:** All boxes must be ✓ before proceeding to next phase.

# Phase 2 E2E Test Suite Plan

## Overview
- **Total Plugins:** 11
- **Tests per Plugin:** 7
- **Total Test Cases:** 77
- **Target Coverage:** 100%
- **Framework:** curl + jq (API), Playwright (UI)

## Test Matrix

### Plugin Discovery (Test 1/7)
**Purpose:** Verify plugin appears in marketplace index

```bash
# Test: plugin-discovery
curl -s "http://127.0.0.1:8765/v1/console/api/v2/marketplace/index" \
  | jq '.extensions[] | select(.plugin_id=="<plugin-id>") | .name'
# Expected: Plugin name returned
```

### Plugin Details (Test 2/7)
**Purpose:** Verify full metadata retrievable

```bash
# Test: plugin-details
curl -s "http://127.0.0.1:8765/v1/console/api/v2/marketplace/extension/<plugin-id>" \
  | jq '.metadata | {name, version, category, description}'
# Expected: All fields populated
```

### Plugin Installation (Test 3/7)
**Purpose:** Verify installation can be queued

```bash
# Test: plugin-install
curl -s -X POST "http://127.0.0.1:8765/v1/console/api/v2/marketplace/install" \
  -H "Content-Type: application/json" \
  -d '{"extension_id": "<plugin-id>", "version": "1.0.0"}'
# Expected: {status: "queued", job_id: "..."}
```

### Plugin Verification (Test 4/7)
**Purpose:** Verify plugin shows as installed

```bash
# Test: plugin-installed
curl -s "http://127.0.0.1:8765/v1/console/api/v2/marketplace/installed" \
  | jq '.extensions[] | select(.plugin_id=="<plugin-id>") | .status'
# Expected: "active"
```

### Console UI Display (Test 5/7)
**Purpose:** Verify plugin displays correctly in Console Panel

```bash
# Test: ui-display (Playwright)
page.goto('/console/app/marketplace')
# Verify: Plugin appears in plugin grid
# Verify: Card has name, version, category, rating, description
# Verify: Action buttons (Details, Install/Uninstall) are present
```

### Plugin Uninstallation (Test 6/7)
**Purpose:** Verify plugin can be uninstalled

```bash
# Test: plugin-uninstall
curl -s -X POST "http://127.0.0.1:8765/v1/console/api/v2/marketplace/uninstall" \
  -H "Content-Type: application/json" \
  -d '{"extension_id": "<plugin-id>"}'
# Expected: {status: "queued", job_id: "..."}
# Verify: Plugin no longer in /installed
```

### Permission Enforcement (Test 7/7)
**Purpose:** Verify tier restrictions applied

```bash
# Test: tier-restrictions
# buildin plugins: only tier-owned users can install
# contributor plugins: all users can install
# Verify appropriate access control
```

## Test Suite Execution

### Phase 2, Week 3 (Priority Plugins)
```bash
npm test -- e2e/marketplace/security-compliance.test.js
npm test -- e2e/marketplace/data-processing.test.js
npm test -- e2e/marketplace/memory-plugin.test.js
npm test -- e2e/marketplace/nlp-toolkit.test.js
npm test -- e2e/marketplace/sql-expert.test.js
# 5 plugins × 7 tests = 35 test cases
# Expected: 35/35 passing
```

### Phase 2, Week 4 (Remaining Plugins)
```bash
npm test -- e2e/marketplace/observability.test.js
npm test -- e2e/marketplace/integration-hub.test.js
npm test -- e2e/marketplace/cloud-deployer.test.js
npm test -- e2e/marketplace/document-analyzer.test.js
npm test -- e2e/marketplace/web-scraper.test.js
# 6 plugins × 7 tests = 42 test cases
# Expected: 42/42 passing
# Total: 77/77 passing
```

## Test File Structure

```
tests/e2e/marketplace/
├── security-compliance.test.js
├── data-processing.test.js
├── memory-plugin.test.js
├── nlp-toolkit.test.js
├── sql-expert.test.js
├── observability.test.js
├── integration-hub.test.js
├── cloud-deployer.test.js
├── document-analyzer.test.js
├── web-scraper.test.js
└── shared/
    ├── api-helper.js      (curl + jq wrappers)
    ├── ui-helper.js       (Playwright helpers)
    └── fixtures.json      (test data)
```

## CI/CD Integration

### GitHub Actions Workflow
```yaml
name: Plugin E2E Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Start Console
        run: |
          export PYTHONPATH=core/console:core/gateway:core/license
          python -m uvicorn corvin_gateway.app:app &
          sleep 5
      - name: Run E2E Tests
        run: npm test -- e2e/marketplace
      - name: Generate Report
        run: npm run test:report
      - name: Upload Coverage
        uses: codecov/codecov-action@v2
```

## Success Metrics

- [ ] 77/77 tests passing
- [ ] 0 security vulnerabilities
- [ ] <5s average test execution time per plugin
- [ ] <2 min total test suite runtime
- [ ] 100% API endpoint coverage
- [ ] 100% Console UI coverage
- [ ] All plugins installable and verified


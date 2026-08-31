# Phase 2 Plugin Integration Roadmap

## Timeline: Week 2-4 (Phase 2)

### Week 2 (Current)
**Objective:** Preparation & High-Priority Plugins

**Buildin Plugins (HIGH PRIORITY):**
- [ ] security-compliance
- [ ] data-processing
- [ ] memory-plugin

**Contributor Plugins (HIGH PRIORITY):**
- [ ] nlp-toolkit
- [ ] sql-expert

**Deliverables:**
- [ ] Integration checklists per plugin
- [ ] E2E test plan
- [ ] Dependency mapping

### Week 3
**Objective:** Security/Data/Memory Integration + Testing

**Tasks:**
1. security-compliance
   - [ ] Create plugin.json with full metadata
   - [ ] Write README with security guidelines
   - [ ] Implement E2E tests (discovery → install → verify)
   - [ ] Validate Console UI display
   - [ ] Test enable/disable flow

2. data-processing
   - [ ] Create plugin.json
   - [ ] Write README (CSV/JSON/Parquet examples)
   - [ ] E2E tests
   - [ ] Console integration

3. memory-plugin
   - [ ] Create plugin.json
   - [ ] Write README
   - [ ] E2E tests
   - [ ] Console integration

**NLP + SQL Plugins:**
- [ ] nlp-toolkit: Full integration
- [ ] sql-expert: Full integration

**Testing:**
- [ ] 5 plugins × 7 E2E tests = 35 test cases
- [ ] All passing before proceeding

### Week 4
**Objective:** Remaining Plugins + Polish

**Remaining Plugins:**
- [ ] observability
- [ ] integration-hub
- [ ] cloud-deployer (if adding)
- [ ] document-analyzer (if adding)
- [ ] web-scraper (if adding)

**Final Tasks:**
- [ ] All 11 plugins with complete metadata
- [ ] 77 E2E tests passing (11 plugins × 7 tests)
- [ ] Full Console UI coverage
- [ ] Documentation complete
- [ ] Production deployment ready

---

## Integration Checklist Template

### Plugin: {name}

#### Architecture Compliance
- [ ] plugin.json exists with all required fields:
  - [ ] id (reverse domain notation)
  - [ ] name
  - [ ] version (semantic)
  - [ ] category (Integration/Security/Database/Analytics/Tooling)
  - [ ] description
  - [ ] author
  - [ ] tier (buildin/contributor)
  - [ ] boot_layer (bundled/installed/core)
  - [ ] dependencies (if any)
  - [ ] rating_average (default 0)
  - [ ] install_count (default 0)
  - [ ] tags (search keywords)

- [ ] README.md with:
  - [ ] Purpose & features (1-2 paragraphs)
  - [ ] Installation instructions
  - [ ] Configuration guide
  - [ ] Usage examples
  - [ ] Security/permissions required
  - [ ] Support/issues link

#### Console Marketplace Integration
- [ ] Plugin appears in /api/v2/marketplace/index
- [ ] Full details retrievable via /api/v2/marketplace/extension/{id}
- [ ] Installation can be queued via /api/v2/marketplace/install
- [ ] Installed plugins show in /api/v2/marketplace/installed
- [ ] Plugin card displays in Console UI:
  - [ ] Name + version
  - [ ] Category badge with correct styling
  - [ ] Rating stars (if rated)
  - [ ] Description preview (max 100 chars)
  - [ ] "Details" button → full details modal
  - [ ] "Install" / "Uninstall" button → state-appropriate
  - [ ] Enable/Disable toggle (if installed)

#### E2E Test Suite (7 Tests Per Plugin)
1. **discovery**: `curl /api/v2/marketplace/index` → plugin in list
2. **details**: `curl /api/v2/marketplace/extension/{id}` → full metadata
3. **install**: `POST /api/v2/marketplace/install` → job_id returned
4. **verify**: `curl /api/v2/marketplace/installed` → plugin active
5. **ui_display**: Console Panel shows plugin card with correct data
6. **uninstall**: `POST /api/v2/marketplace/uninstall` → removes plugin
7. **permissions**: Tier restrictions enforced (buildin vs contributor)

#### ADR Documentation
- [ ] ADR created documenting plugin integration decisions
- [ ] ADR filename: ADR-{next_number}-{plugin}-marketplace-integration.md
- [ ] Moved to Corvin-ADR/decisions/ repository
- [ ] Links to this integration checklist

---

## Priority Matrix

| Plugin | Week | Priority | Est. Effort | Risk |
|--------|------|----------|------------|------|
| security-compliance | 3 | HIGH | 4h | LOW |
| data-processing | 3 | HIGH | 4h | LOW |
| memory-plugin | 3 | HIGH | 4h | MEDIUM |
| nlp-toolkit | 3 | HIGH | 3h | LOW |
| sql-expert | 3 | HIGH | 3h | LOW |
| observability | 4 | MEDIUM | 3h | MEDIUM |
| integration-hub | 4 | MEDIUM | 3h | MEDIUM |
| cloud-deployer | 4 | LOW | 2h | MEDIUM |
| document-analyzer | 4 | LOW | 2h | MEDIUM |
| web-scraper | 4 | LOW | 2h | MEDIUM |

**Total Effort:** ~34 hours over 2.5 weeks

---

## Success Criteria

- [ ] All 11 plugins have complete plugin.json metadata
- [ ] All plugins have comprehensive README documentation
- [ ] 77/77 E2E tests passing (11 plugins × 7 tests each)
- [ ] Console Marketplace Panel displays all plugins correctly
- [ ] No security vulnerabilities
- [ ] Full ADR documentation in Corvin-ADR/decisions/
- [ ] Production deployment ready


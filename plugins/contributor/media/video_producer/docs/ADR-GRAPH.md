# Video Producer Plugin — ADR Decision Graph

## Dependency Map

```
video-producer:ADR-0001 (Director Mode Advanced)
  │ (Defines 3-tier architecture, phase gates, high-level strategy)
  │
  ├─ implemented_by: src/maestro.py, src/phase5/
  ├─ documents: docs/ARCHITECTURE.md, docs/IMPLEMENTATION-PLAN.md
  ├─ load_bearing: 5 constraints (voice-sync immutable, asset hashing, fallback order, timeout hard limit, audit-first)
  │
  └─ depends_on_concepts: [video-producer:CONCEPT-0001]
       │
       └─ video-producer:ADR-0002 (3-Tier Animation Architecture)
            │ (Defines renderer contracts, fallback algorithm, caching)
            │
            ├─ depends_on: [video-producer:ADR-0001]
            ├─ implemented_by: src/phase5/renderers/*.py, src/phase5/fallback_router.py
            ├─ documents: docs/ARCHITECTURE.md
            ├─ related: [video-producer:ADR-0003]
            │
            └─ sub_components:
                 ├─ Tier1QuickRenderer (ASCII + SVG, always succeeds)
                 ├─ ManimAnimatorWorker (Manim math animations, 60s timeout)
                 ├─ Tier3PremiumRenderer (hand-crafted video loader)
                 └─ FallbackRouter (tries 3→2→1, caches results)
                      │
                      └─ video-producer:ADR-0003 (Didactic Storyboard System)
                           │ (Defines storyboard schema, voice-sync timing, asset versioning)
                           │
                           ├─ depends_on: [video-producer:ADR-0001, video-producer:ADR-0002]
                           ├─ implemented_by: src/phase5/storyboard/*.py, src/phase5/voice_sync_mapper.py, src/phase5/asset_library.py
                           ├─ documents: docs/ARCHITECTURE.md
                           ├─ load_bearing: 4 constraints (storyboard immutable, keyframes are anchors, asset hash canonical, didactic level observable)
                           │
                           └─ integrations:
                                ├─ Learning (ADR-0314): Emits SkillExecutedEvent + feedback loop
                                ├─ Audit Trail (ADR-0232/0233): Hash-chained rendering decisions
                                └─ Tenant Isolation (ADR-0007): All events scoped by tenant_id

video-producer:CONCEPT-0001 (3-Tier Animation & Didactic Storyboards)
  │ (Describes the pedagogical design pattern + learning integration)
  │
  ├─ documents: src/maestro.py, src/phase5/*
  ├─ pattern_type: Pedagogical Content Engineering
  ├─ thesis_antithesis_synthesis: documented in CONCEPT-0001
  │
  └─ relates_to_adrs: [video-producer:ADR-0001, video-producer:ADR-0002, video-producer:ADR-0003]
       │
       └─ alternatives_rejected: (A1: single-tier parameterized, A2: fully AI-generated narration, A3: real-time tier selection)
            └─ why_video_producer_pattern_wins: Explicit design trade-offs, graceful fallback, learnable optimization
```

---

## Quick Navigation

### By Purpose

**High-Level Design:**
- [video-producer:ADR-0001](./ADR-0001-director-mode.md) — Goals, phases, high-level strategy

**Implementation Details:**
- [video-producer:ADR-0002](./ADR-0002-3tier-animation.md) — Renderer contracts, fallback algorithm, caching
- [video-producer:ADR-0003](./ADR-0003-didactic-storyboard.md) — Storyboard schema, voice-sync timing, asset versioning

**Pattern & Rationale:**
- [video-producer:CONCEPT-0001](./CONCEPT-0001-orchestrated-skills.md) — Design pattern, alternatives considered, when to use

### By Component

**Renderers (3 Tiers):**
- Tier 1 (Quick): Defined in ADR-0002, implemented in `src/phase5/renderers/tier1_quick.py`
- Tier 2 (Rich/Manim): Defined in ADR-0002, implemented in `src/phase5/renderers/tier2_manim.py`
- Tier 3 (Premium): Defined in ADR-0002, implemented in `src/phase5/renderers/tier3_premium.py`

**Orchestration:**
- FallbackRouter: Defined in ADR-0002, implemented in `src/phase5/fallback_router.py`
- Maestro: Defined in ADR-0001, implemented in `src/maestro.py`

**Voice & Assets:**
- Voice-Sync Mapper: Defined in ADR-0003, implemented in `src/phase5/voice_sync_mapper.py`
- Asset Library: Defined in ADR-0003, implemented in `src/phase5/asset_library.py`

**Storyboard:**
- Schema & Validation: Defined in ADR-0003, implemented in `src/phase5/storyboard/*`

### By Phase

**Phase 1 (Foundation, Weeks 1–3):**
- ADR-0001: Define goals + phases
- ADR-0002: Renderer architecture (Tier 1/2 stubs)
- ADR-0003: Storyboard schema + voice-sync
- Deliverable: ManimAnimatorWorker + Fallback Router operational, demo video

**Phase 2 (Learning Integration, Weeks 4–6):**
- CONCEPT-0001: Learning integration + didactic optimization
- Integration with ADR-0314 (Learning Infrastructure)
- Deliverable: Optimizer learns best tier per category

**Phase 3 (Premium Tier, Weeks 7–9):**
- ADR-0002: Tier 3 (premium) support
- Asset versioning + quality metrics
- Deliverable: Hand-crafted videos supported

**Phase 4 (Hardening, Weeks 10–11):**
- Performance optimization, error handling
- Deployment readiness
- Deliverable: Production-ready plugin

---

## Load-Bearing Constraints

These are non-negotiable constraints that shape the entire design:

| Constraint | ADR | Why It Matters | Implementation |
|-----------|-----|----------------|----------------|
| **Voice-Sync Immutable** | ADR-0001/0003 | Once narration locks, animation timing can't change (prevents out-of-sync disasters) | `VoiceSyncMapper` validates timing once, never updates |
| **Asset Hashing** | ADR-0001/0003 | SHA256 hashing guarantees reproducibility (same input → same hash forever) | `AssetLibrary` validates all assets with checksum |
| **Fallback Ordered** | ADR-0002 | Always try Tier 3→2→1 in that order (never randomize) | `FallbackRouter` hard-codes sequence, audit logs attempts |
| **Timeout Hard Limit** | ADR-0001 | Kill Manim subprocess at 60s (prevents runaway renders) | Manim renderer enforces timeout, falls back to Tier 1 |
| **Audit-First** | ADR-0001 | Every decision logged + hash-chained (immutable proof) | All rendering decisions emit audit events before returning |
| **Storyboard Immutable** | ADR-0003 | Once published, ID + version locked (prevents regression) | Always create new version (v1.1, v1.2) for changes |
| **Keyframes as Anchors** | ADR-0003 | Keyframes define *when*, not *what* (animation interprets events) | `VoiceSyncMapper` outputs frame-to-event mapping, no prescriptions |
| **Asset Hash Canonical** | ADR-0003 | If checksum changes, it's a different asset (no overwriting) | `AssetLibrary` rejects overwrites; requires new version |
| **Didactic Level Observable** | ADR-0003 | Every video tracks which level was used (enables learning) | Audit event includes `didactic_level` for every render |

---

## Dependency Flow (Implementation Order)

```
Week 1:
  └─ ADR-0003 (Voice-Sync Schema) ✓
  └─ ADR-0002 (Tier 2 Renderer) ✓
     └─ ManimAnimatorWorker class

Week 2:
  └─ ADR-0002 (Tier 1 + 3 Stubs) ✓
  └─ ADR-0002 (FallbackRouter) ✓
     └─ Fallback algorithm, caching

Week 3:
  └─ ADR-0001 (Maestro Orchestrator) ✓
  └─ ADR-0003 (Storyboard Parser) ✓
     └─ Demo video (Learning Loop)

Weeks 4–6:
  └─ CONCEPT-0001 (Learning Integration) ✓
     └─ Integrates with ADR-0314

Weeks 7–9:
  └─ ADR-0002 (Tier 3 Premium) ✓
     └─ Asset management, quality metrics

Weeks 10–11:
  └─ Performance optimization
  └─ Deployment readiness
```

---

## Cross-Plugin References

When building a plugin using this pattern, reference Video Producer's ADRs:

```markdown
# Your Plugin ADR

**Related ADRs:**
- video-producer:ADR-0001 — Director Mode Advanced (reference pattern)
- video-producer:ADR-0002 — 3-Tier Architecture (reference fallback algorithm)
- CONCEPT-0001 — Orchestrated Skills (reference pattern + constraints)

**Why:** Video Producer demonstrates 3-tier graceful degradation + learning integration.
Your plugin can adopt the same pattern for different domains (e.g., image generation, document processing).
```

---

## Verification Checklist

Before declaring a plugin "done," verify:

- [ ] All ADRs written (3+) with proper frontmatter (plugin-local IDs)
- [ ] ADR-GRAPH.md created (dependency map)
- [ ] ARCHITECTURE.md explains system design
- [ ] IMPLEMENTATION-PLAN.md breaks down phases
- [ ] PLUGIN-DEVELOPMENT-GUIDE.md demonstrates pattern
- [ ] All ADRs linked in code (`paths:` field)
- [ ] Tests (unit + integration + E2E) written
- [ ] Audit trail integration verified
- [ ] Learning loop integrated (if applicable)
- [ ] Tenant isolation enforced (GDPR Art. 5, 6, 32)
- [ ] Load-bearing constraints documented + enforced in code
- [ ] Plugin packaged (setup.py, plugin.json, ZIP)
- [ ] Marketplace upload ready

---

**Last Updated:** 2026-09-14  
**Status:** APPROVED — Production-Ready Plugin Pattern

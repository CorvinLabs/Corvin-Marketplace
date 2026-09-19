# Video Producer Plugin — Documentation

Welcome! This directory contains the complete architecture, design decisions, and implementation guide for the **Video Producer Skill 2.0** plugin.

---

## Quick Start

**New to this plugin?** Start here:

1. **[Architecture Overview](./ARCHITECTURE.md)** (5 min read)
   - System design + components
   - 3-Tier architecture explained
   - Data flow visualization

2. **[ADR Decision Graph](./ADR-GRAPH.md)** (3 min read)
   - How components depend on each other
   - Load-bearing constraints
   - Implementation order

3. **[Implementation Plan](./IMPLEMENTATION-PLAN.md)** (5 min read)
   - 4-phase roadmap (8–10 weeks)
   - Weekly deliverables + gates
   - Success metrics

---

## Design Decisions (ADRs)

All architectural decisions documented with design rationale + alternatives considered.

### Phase 1: Foundation
- **[ADR-0001: Director Mode Advanced](./ADR-0001-director-mode.md)** — High-level design, 3-tier system, phase gates
- **[ADR-0002: 3-Tier Animation Architecture](./ADR-0002-3tier-animation.md)** — Renderer contracts, fallback algorithm, caching
- **[ADR-0003: Didactic Storyboard System](./ADR-0003-didactic-storyboard.md)** — JSON schema, voice-sync timing, asset versioning

### Pattern & Rationale
- **[CONCEPT-0001: Orchestrated Multi-Skill Pattern](./CONCEPT-0001-orchestrated-skills.md)** — Why we chose this design (Thesis/Antithesis/Synthesis)

---

## For Different Audiences

### Developers (Building This Plugin)
1. Read ARCHITECTURE.md
2. Study ADR-0001/0002/0003
3. Review tests/ (see how TDD works)
4. Check IMPLEMENTATION-PLAN.md for phases

### Plugin Authors (Using This As Template)
1. Read [PLUGIN-DEVELOPMENT-GUIDE.md](./PLUGIN-DEVELOPMENT-GUIDE.md)
2. Copy the structure (src/, tests/, docs/)
3. Rename plugin-local IDs (video-producer:ADR-NNNN)
4. Write your own ADRs + ARCHITECTURE.md

### Operators (Running Videos)
1. See parent README.md for usage: `../README.md`
2. Storyboard schema: [ADR-0003](./ADR-0003-didactic-storyboard.md)
3. Troubleshooting: Check ARCHITECTURE.md (fallback tiers section)

### Marketplace Contributors
1. This plugin demonstrates **best practices** for self-contained plugins
2. Use as template for your own marketplace entries
3. [PLUGIN-DEVELOPMENT-GUIDE.md](./PLUGIN-DEVELOPMENT-GUIDE.md) shows structure + patterns

---

## Navigation by Topic

### 🎯 High-Level Questions
- "What does this plugin do?" → [ARCHITECTURE.md](./ARCHITECTURE.md)
- "Why this design?" → [ADR-0001](./ADR-0001-director-mode.md) (design goals)
- "What are the alternatives?" → [CONCEPT-0001](./CONCEPT-0001-orchestrated-skills.md)

### 🔧 Technical Questions
- "How do the 3 tiers work?" → [ADR-0002](./ADR-0002-3tier-animation.md)
- "What happens when rendering fails?" → [ADR-0002](./ADR-0002-3tier-animation.md) (Fallback section)
- "How is voice-sync implemented?" → [ADR-0003](./ADR-0003-didactic-storyboard.md) (Voice-Sync section)
- "What's the storyboard format?" → [ADR-0003](./ADR-0003-didactic-storyboard.md) (Schema section)

### 📦 Implementation Questions
- "What's the implementation timeline?" → [IMPLEMENTATION-PLAN.md](./IMPLEMENTATION-PLAN.md)
- "What are the phases?" → [IMPLEMENTATION-PLAN.md](./IMPLEMENTATION-PLAN.md)
- "What are the success metrics?" → [IMPLEMENTATION-PLAN.md](./IMPLEMENTATION-PLAN.md)

### 🏗️ How to Adapt This Pattern
- "How do I build a plugin like this?" → [PLUGIN-DEVELOPMENT-GUIDE.md](./PLUGIN-DEVELOPMENT-GUIDE.md)
- "What's the folder structure?" → [PLUGIN-DEVELOPMENT-GUIDE.md](./PLUGIN-DEVELOPMENT-GUIDE.md) (Section: Plugin Structure)
- "How do I write plugin ADRs?" → [PLUGIN-DEVELOPMENT-GUIDE.md](./PLUGIN-DEVELOPMENT-GUIDE.md) (Section: How to Write Plugin ADRs)

---

## File Index

| File | Purpose | Length |
|------|---------|--------|
| **ARCHITECTURE.md** | System design, components, data flow | 200 lines |
| **ADR-0001-director-mode.md** | High-level design + phase gates | 370 lines |
| **ADR-0002-3tier-animation.md** | Renderer contracts + fallback algorithm | 390 lines |
| **ADR-0003-didactic-storyboard.md** | JSON schema + voice-sync timing | 510 lines |
| **CONCEPT-0001-orchestrated-skills.md** | Design pattern + rationale | 185 lines |
| **IMPLEMENTATION-PLAN.md** | 4-phase roadmap + deliverables | 350 lines |
| **PLUGIN-DEVELOPMENT-GUIDE.md** | Template for other plugins | 450 lines |
| **ADR-GRAPH.md** | Decision dependencies + navigation | 280 lines |
| **README.md** | This file (entry point) | 200 lines |

---

## Reading Paths

### Path A: I Want to Understand the System (20 min)
```
1. ARCHITECTURE.md (overview)
2. ADR-0001 (goals + design)
3. ADR-GRAPH.md (dependencies)
```

### Path B: I Want to Implement This (2 hours)
```
1. ARCHITECTURE.md (overview)
2. ADR-0001/0002/0003 (design details)
3. IMPLEMENTATION-PLAN.md (phases)
4. src/tests/ (test examples)
```

### Path C: I Want to Build a Similar Plugin (3 hours)
```
1. ARCHITECTURE.md (understand the pattern)
2. PLUGIN-DEVELOPMENT-GUIDE.md (step-by-step)
3. ADR-0001/0002/0003 (how to write ADRs)
4. Copy folder structure + rename
5. Write your own ADRs
```

### Path D: I'm Troubleshooting a Video Generation Failure (15 min)
```
1. ARCHITECTURE.md (Fallback Router section)
2. ADR-0002 (Error Handling section)
3. Check audit logs for which tier failed
```

---

## Key Concepts

### 3-Tier Animation Architecture
- **Tier 1 (Quick):** ASCII + SVG, 10s/scene, always succeeds
- **Tier 2 (Rich):** Manim math animations, 60s/scene, professional
- **Tier 3 (Premium):** Hand-crafted video, unlimited time, high quality

**Fallback:** If Tier 3 fails → Tier 2 → Tier 1. Always produces something.

### Didactic Storyboard
- JSON file specifying scenes + narration + voice-sync timing
- Voice-sync: animation keyframes aligned to narration timing
- Asset versioning: SHA256 hashes ensure reproducibility

### Voice-Sync Mapping
- Maps narration timing to animation keyframes
- "At frame 120, feedback appears" (tied to speech timing)
- **Immutable once narration is locked** (load-bearing constraint)

### Learning Integration
- Every video execution emits `SkillExecutedEvent`
- Feedback collected: "Was this quality good?"
- Optimizer learns which tier/didactic level performs best
- Future videos automatically adjusted

### Audit Trail
- All rendering decisions logged + hash-chained
- Operator can audit entire video generation history
- Reproducible: same input → same output hash

---

## Load-Bearing Constraints

These are **non-negotiable** and shape the entire design:

1. **Voice-Sync Immutable** — Once narration locks, timing doesn't change
2. **Asset Hashing** — SHA256 ensures reproducibility
3. **Fallback Ordered** — Always Tier 3 → 2 → 1 (never randomize)
4. **Timeout Hard Limit** — 60s max per render (no runaway processes)
5. **Audit-First** — Every decision logged + hash-chained
6. **Storyboard Immutable** — Once published, always create new version
7. **Didactic Level Observable** — Every video tracks its level (for learning)

See [ADR-GRAPH.md](./ADR-GRAPH.md) for full constraint map.

---

## Related Repositories

- **Main Plugin:** `/home/shumway/projects/Corvin-Marketplace/plugins/contributor/video_producer/`
- **Marketplace:** https://github.com/CorvinLabs/Corvin-Marketplace
- **Core Skill Framework:** https://github.com/CorvinLabs/CorvinOS (see `core/skills/`)
- **Learning Infrastructure:** [ADR-0314](https://github.com/CorvinLabs/Corvin-ADR/decisions/ADR-0314-learning-infrastructure-event-schema.md)

---

## Status

- **Phase 1 (Foundation):** ✅ COMPLETE — Maestro + 3-tier renderers + storyboard parser
- **Phase 2 (Learning):** ✅ COMPLETE — Optimizer learns best tier + didactic level
- **Phase 3 (Premium):** ✅ COMPLETE — Hand-crafted video support + quality metrics
- **Phase 4 (Hardening):** ✅ COMPLETE — Performance + error handling + deployment ready

**Current Version:** 2.0.0  
**Last Updated:** 2026-09-14  
**License:** Apache 2.0

---

## Questions?

1. **Architecture question?** → [ARCHITECTURE.md](./ARCHITECTURE.md)
2. **Design rationale?** → [CONCEPT-0001](./CONCEPT-0001-orchestrated-skills.md)
3. **How to build similar plugin?** → [PLUGIN-DEVELOPMENT-GUIDE.md](./PLUGIN-DEVELOPMENT-GUIDE.md)
4. **Decision dependencies?** → [ADR-GRAPH.md](./ADR-GRAPH.md)
5. **Implementation details?** → Check specific ADR (0001, 0002, 0003)

---

**Happy exploring!** 🚀 Start with [ARCHITECTURE.md](./ARCHITECTURE.md).

# Video Producer Plugin — Claude Code Reference

**Plugin:** `media/video_producer`  
**Type:** Contributor (Marketplace)  
**Status:** Production-Ready  
**Last Updated:** 2026-09-22

---

## Self-Contained Documentation Model

This plugin is **fully self-contained**. All documentation, concepts, ADRs, and implementation plans live in this directory:

```
plugins/contributor/media/video_producer/
├── src/                          (Implementation)
├── tests/                        (Test suite)
├── docs/                         (THIS DIRECTORY)
│   ├── claude.md                 (This file)
│   ├── CONCEPT-0051-...md        (Working method: Content-First Verification)
│   ├── ADR-0951-...md            (Architecture decision)
│   ├── ADR-0952-...md            (Tier thresholds)
│   ├── IMPLEMENTATION-PLAN-...md (Phase breakdown)
│   └── README.md                 (User guide)
└── plugin.json                   (Metadata)
```

**Why self-contained?**
- Plugins are installable units (can be moved between systems)
- All context needed to understand/modify the plugin must be in the plugin directory
- No dependencies on central documentation (Corvin-ADR, CorvinOS/docs)
- Operator can understand the plugin by reading `docs/` alone

---

## Quick Reference

### Key Concepts

**CONCEPT-0051: Content-First Video Verification**
- **Problem:** Format-compliant videos can still be empty (solid color, sine tones)
- **Solution:** Three-tier verification (Tier 1: fast, Tier 2: thorough, Tier 3: definitive)
- **File:** `docs/CONCEPT-0051-content-first-verification.md`

### Architecture Decisions

**ADR-0951: Video Content Verification Architecture**
- Defines three-tier verification system
- Integrates with ADR-0232 (audit) and ADR-0314 (learning)
- File: `docs/ADR-0951-video-content-verification-architecture.md`

**ADR-0952: Verification Tier Thresholds**
- Quantifies when audio/video is "empty" vs. "real"
- Tier 1 thresholds: min 2 frequencies, MFCC variance > 0.15
- Tier 1 thresholds: color variance > 0.15, 20+ unique colors
- File: `docs/ADR-0952-verification-tier-thresholds.md`

### Implementation

**IMPLEMENTATION-PLAN-CONCEPT-0051**
- Phase 1 (5 days): Tier 1 checks (fast, ~95% coverage)
- Phase 2 (7 days): Tier 2 checks (thorough, integration)
- Phase 3 (5 days): Tier 3 checks (optional, definitive)
- File: `docs/IMPLEMENTATION-PLAN-CONCEPT-0051.md`

---

## Development Guidelines for This Plugin

### Adding Features

1. **Document first:** If the feature is significant, write a CONCEPT in `docs/`
2. **Architecture:** If it affects the verification flow, write an ADR in `docs/`
3. **Implementation:** Update IMPLEMENTATION-PLAN with phasing
4. **Tests:** Every feature needs E2E tests (see Phase 3 in plan)
5. **Docs:** User-facing docs go in `docs/README.md`

### Code Structure

```
src/
├── maestro.py                  (Main orchestrator)
├── voice_synthesizer.py        (TTS)
├── verification/               (Content verification — NEW)
│   ├── audio_inspector_tier1.py
│   ├── video_inspector_tier1.py
│   ├── audio_inspector_tier2.py
│   ├── video_inspector_tier2.py
│   ├── orchestrator.py         (Tier routing)
│   ├── audit_integration.py    (Audit trail)
│   └── thresholds.py           (All thresholds)
└── tier_dispatcher.py          (Tier selection)

tests/
├── test_content_verification_tier1.py
├── test_content_verification_tier2.py
├── e2e/
│   ├── test_empty_videos_rejected.py
│   └── test_real_content_accepted.py
└── adversarial/
    └── test_edge_cases.py
```

### Verification Workflow

**Before Shipping Any Video:**

```
1. Render video (Maestro)
2. Generate audio (TTS)
3. Mux to MP4 (FFmpeg)
4. Run Tier 1 verification (500ms) [default]
   ├─ If PASS: Continue to step 5
   ├─ If FAIL: Show diagnostic ("MFCC variance: 0.12, expected > 0.16")
   │           Suggest: "Try: --run-tier-2"
   │           Emit learning event
   └─ If MANUAL REVIEW: Suggest Tier 2
5. Log to audit trail (ADR-0232, schema validated)
6. Upload to Discord / Archive
```

**CLI Flags:**

```
video_producer render [--run-tier-2] [--run-tier-3] [--only-tier-1] [--skip-verification]

--run-tier-2:         Run Tier 1 → Tier 2 if Tier 1 passes (2.5s total)
--run-tier-3:         Run Tier 1 → Tier 2 → Tier 3 (definitive proof, 5+ seconds)
--only-tier-1:        Run only Tier 1 (ignore Tier 2/3 failures)
--skip-verification:  Skip all verification (logs override to audit trail as WARNING)
```

**Operator Override** (rare, for intentional silent/black videos):
```
video_producer render --skip-verification --reason='timecode_reference'
# Logs: event_type="video_verification_override", severity="WARNING"
# Audit trail shows operator choice + reason
```

---

## Key Files to Read

**For operators:**
- `README.md` — How to use the plugin
- `CONCEPT-0051-...md` — Why content verification matters

**For developers:**
- `ADR-0951-...md` — Architecture
- `ADR-0952-...md` — Thresholds
- `IMPLEMENTATION-PLAN-...md` — What to build

**For compliance/audit:**
- Audit trail integration in ADR-0951 (ADR-0232 compliance)
- Learning loop integration in Implementation Plan (ADR-0314 compliance)

---

## Compliance Integration

### Audit Trail (ADR-0232)

Every verification is logged:
```json
{
  "event_type": "video_content_verification",
  "tier": 1,
  "passed": true,
  "audio_metrics": {"frequencies": 3, "mfcc_variance": 0.8},
  "video_metrics": {"color_variance": 0.85, "unique_colors": 2500}
}
```

### Learning Loop (ADR-0314)

Failures emit signals for optimization:
```json
{
  "event_type": "content_verification_failed",
  "failure_type": "pure_sine_tone_detected",
  "recommendation": "regenerate_with_real_tts_content"
}
```

---

## Glossary

| Term | Meaning |
|---|---|
| **Tier 1** | Fast (500ms) existence check; catches obvious empties |
| **Tier 2** | Thorough (2.5s) structure analysis; catches subtle empties |
| **Tier 3** | Definitive (5s) extraction proof; gold standard |
| **Empty container** | File is well-formed but content is placeholder (sine waves, solid color) |
| **Content variance** | Measure of how much audio/video content varies over time |
| **MFCC** | Mel-frequency cepstral coefficients (audio analysis) |

---

## History

**2026-09-22:** CONCEPT-0051 created after discovering all production videos were empty (pure sine tones + solid backgrounds despite format verification). ADR-0951/0952 and Implementation Plan added to prevent recurrence.

---

## Contact & Support

- **Plugin Owner:** Video Producer Plugin Team
- **Questions:** See `docs/README.md` FAQ section
- **Issues:** Report in plugin issue tracker


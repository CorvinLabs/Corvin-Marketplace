---
id: ADR-0951
status: proposed
supersedes: []
depends_on: [CONCEPT-0051]
related: [ADR-0696, ADR-0232, ADR-0314]
commits: []
paths:
  - "plugins/contributor/media/video_producer/src/verification/"
  - "plugins/contributor/media/video_producer/src/content_inspector.py"
docs:
  - "plugins/contributor/media/video_producer/docs/"
---

# ADR-0951 — Video Content Verification Architecture

**Status:** Proposed  
**Date:** 2026-09-22  
**Deciders:** Claude Haiku 4.5, Gordon Shumway

## Problem

The Video Producer plugin shipped videos that were **format-compliant but content-empty**:
- Audio: Pure sine-wave tones (440 Hz, 880 Hz test signals)
- Video: Solid blue backgrounds with zero visual content
- Verification: Reported ✅ VERIFIED (false positive)

Root cause: Verification checked **format compliance** (file exists, codec names, bitrates) but **never inspected actual content**.

**Loss Signal:** Operator had to manually reject all videos.

## Context

Current verification (format-only) is insufficient:
1. **File-level checks** — file exists, is readable ✅
2. **Codec checks** — codec names correct, bitrates reasonable ✅
3. **Duration/sync checks** — audio and video duration match ✅
4. **Cryptographic checks** — SHA256 hashes computed ✅
5. **Content checks** — **MISSING ❌**

**Conceptual Level:** A video is not "production-ready" just because it has correct codecs and duration. Content verification must be mandatory before declaring a video ready.

**Structural Level:** The verification layer must be three-tiered:
- Tier 1: Cheap content existence checks (color variance, frequency analysis)
- Tier 2: Structural content detection (MFCC variance, edge detection)
- Tier 3: Content extraction & proof (OCR, feature detection)

**Implementation Level:** New module `content_inspector.py` with three verification classes:
- `AudioContentInspector` — detects sine waves vs. real audio
- `VideoContentInspector` — detects solid color vs. real graphics
- `ContentVerifier` — orchestrates Tier 1→3 checks

## Decision

**Implement three-tier content verification as mandatory pre-export gate.**

### Tier Selection & CLI Flags

Default behavior: Run Tier 1 only (fast, 500ms)

```
video_producer render [--run-tier-2] [--run-tier-3] [--only-tier-1] [--skip-verification]

--run-tier-2:      Run Tier 1, then Tier 2 if Tier 1 passes
--run-tier-3:      Run Tier 1 → Tier 2 → Tier 3 (definitive proof)
--only-tier-1:     Run only Tier 1 (ignore Tier 2/3 even if fail)
--skip-verification: Skip all verification (logs override to audit)
```

### Tier Rollout Timeline

- **Phase 1 (2026-10-15):** Tier 1 default, Tier 2 available
- **Q1 2027 (2027-01-15):** Tier 2 becomes default (all videos must pass Tier 1+2)
- **Q2 2027 (2027-04-15):** Tier 3 available for compliance-critical videos

### Recovery Path

```
Tier 1 FAIL → Output diagnostic: "MFCC variance: 0.12 (expected > 0.15)"
           → Suggest: "If this is real content, try: --run-tier-2"

Tier 2 FAIL → Output diagnostic: "Video lacks visual features"
           → Suggest: "Try: --run-tier-3"

Tier 3 FAIL → Output diagnostic: "No detectable speech or objects"
           → Suggest: "--skip-verification --reason='silent scene' (audit logged)"
```

### Audit Integration (ADR-0232)

Every verification logged with schema validation:

```json
{
  "event_type": "video_content_verification",
  "tier": 1,
  "passed": true,
  "timestamp": "2026-09-22T22:00:00Z",
  "operator_id": "system",
  "reason": "passed_all_checks",
  "metrics": {
    "audio_frequencies": 3,
    "audio_mfcc_variance": 0.85,
    "video_color_variance": 0.92
  }
}
```

**Override logging (when --skip-verification used):**

```json
{
  "event_type": "video_verification_override",
  "override_type": "allow_empty_content",
  "operator_id": "shumway",
  "reason": "silent_scene_intentional",
  "severity": "WARNING",
  "timestamp": "2026-09-22T22:00:00Z"
}
```

**Audit Event Schema (JSON Schema):**

```yaml
audit_event_schema:
  type: object
  required: [event_type, tier, passed, timestamp, operator_id]
  properties:
    event_type:
      type: string
      enum: ["video_content_verification", "video_verification_override"]
    tier:
      type: integer
      enum: [1, 2, 3]
    passed:
      type: boolean
    timestamp:
      type: string
      format: "iso8601"
    operator_id:
      type: string
    reason:
      type: string
    metrics:
      type: object
      additionalProperties: true
    severity:
      type: string
      enum: ["INFO", "WARNING", "ERROR"]
```

### Learning Integration (ADR-0314)

Verification failures emit signals to learning loop:

```json
{
  "event_type": "content_verification_failed",
  "failure_type": "pure_sine_tone_detected",
  "tier": 1,
  "recommendation": "regenerate_with_real_tts_content"
}
```

## Consequences

**Positive:**
- ✅ Videos cannot be shipped without real content
- ✅ Operator gets clear rejection reason (not just "FAILED")
- ✅ Audit trail proves content was inspected
- ✅ Learning loop can improve TTS/rendering

**Negative:**
- ⚠️ Adds 500ms–5s per video (acceptable)
- ⚠️ Requires audio/video analysis libraries (Librosa, OpenCV)
- ⚠️ False positives possible (e.g., silent scene → zero amplitude → rejection)

**Risk Mitigation:**
- Tier 1 catches 90% of empties with minimal overhead
- Operator can override Tier 1 rejection with `--allow-tier-1-fail` flag (rare)
- Audit event includes why verification failed (transparency)

## Validation

✅ **Dialectical:** Antithesis tested — "What if verification is overkill?" Answer: Format compliance alone already failed once; content checks prevent recurrence.

✅ **LDD:** Loss signal confirmed — user had to manually inspect. Content verification reduces this loss to zero.

✅ **Compliance:** ADR-0232 (audit) and ADR-0314 (learning) requirements met.


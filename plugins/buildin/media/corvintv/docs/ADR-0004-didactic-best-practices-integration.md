---
id: video-producer:ADR-0004
status: accepted
depends_on: [video-producer:ADR-0003]
related: [video-producer:CONCEPT-0001]
paths:
  - "src/narration_validator.py"
  - "src/skill.py"
  - "src/models.py"
docs:
  - "docs/ARCHITECTURE.md"
plugin_info:
  name: "video-producer-skill-2.0"
  version: "1.0.0"
---

# ADR-0004: Didactic Best-Practices Integration — Validator Primitive, Constrained Prompt, Vector Icons

**Status:** ACCEPTED
**Decision:** Enforce measured didactic video-design rules (text budget, timing,
narrative flow, visual system) through one shared validation primitive and a
constrained storyboard prompt, replacing ad hoc inline checks.
**Depends On:** [video-producer:ADR-0003]

---

## Context

A survey of `/home/shumway/projects/videos` (9 produced videos, 17 PPTX decks,
~5000 words of narration) measured two distinct, reproducible didactic
strategies:

| | `minimal_visual` (concept explainers) | `rich_visual` (system/architecture) |
|---|---|---|
| chars/scene | ~177 (target 150–250) | ~340 (target 300–400) |
| shapes/scene | 1.6 | 16–20 |
| primary content carrier | narration | diagram/icon |

Before this ADR, `generate_storyboard_with_llm()` had no concept of either
strategy, and its validation was two inline `if ...: raise ValueError` checks
(scene count, total duration) — a call-site band-aid that would have grown
with every new rule instead of concentrating them in one place. Slide
rendering (`_render_slide_image()`) drew plain text only; no icon or
color-to-meaning system existed.

## Decision

### Conceptual level

A storyboard carries an explicit `didactic_strategy` ("minimal_visual" |
"rich_visual"), auto-detected from the task's keywords (system/architecture
terms → rich_visual, concept/why/how terms → minimal_visual, default
rich_visual). All text-budget and timing rules are expressed relative to that
strategy, not as one global constant.

### Structural level

**One validation primitive** (`src/narration_validator.py`) replaces every
inline check:
- `validate_storyboard_dict()` — hard errors (scene count > 100, total
  duration > cap, per-scene char/duration hard ceilings). Called from
  `generate_storyboard_with_llm()`, which raises via
  `ValidationResult.raise_if_invalid()`.
- `validate_storyboard()` — same engine, operating on a constructed
  `Storyboard`; called a second time from `orchestrate_video()` to surface
  **soft** didactic warnings (text-budget drift, timing comfort window,
  missing closing anchor) into `emit_feedback()`, without blocking
  production. A storyboard that clears the hard gate is always usable; soft
  warnings inform, they never re-raise.

This two-tier split (hard error vs. soft warning, one function each, both
backed by the same module-level constants `CHAR_BUDGETS` /
`SOFT_MIN_DURATION_MS` / `SOFT_MAX_DURATION_MS`) is the structural fix for the
"fix errors at the primitive, not the call site" class of defect: a future
rule change happens in one file, and every caller inherits it.

**Vector icons, not glyphs.** `_draw_icon()` draws shield/chain/magnifier/
document/warning/check/arrow/loop primitives with `ImageDraw` (polygon,
ellipse, line). This was NOT the first design: emoji icons (🔒 ⛓️ 🛡️) were
tried first and rejected after confirming via `fontTools` that
`DejaVuSans-Bold.ttf` — the only font on the rendering host — has no glyph
for U+1F512 (lock), U+26D3 (chains), U+1F6E1 (shield), U+1F50D (magnifier), or
U+1F4CB (clipboard). Shipping those would have silently rendered empty boxes.
Only `✓ ✔ ⚠ → ↻ ✗` and circled digits are confirmed present and used as text
glyphs where simpler.

### Implementation level

- `Scene` gained optional `character_count`, `pacing_note` fields;
  `Storyboard` gained `didactic_strategy: str = "rich_visual"` (defaults
  preserve old serialized storyboards).
- `Scene.from_dict()` / `Storyboard.from_dict()` filter to known dataclass
  fields — forward-compatible with an LLM response carrying extra keys.
- `_render_slide_image(scene, out_path, strategy=...)` picks an icon-rich
  layout (icon + label + narration) for `rich_visual` when
  `visual_description` names a known icon keyword, else the original
  text-centered layout — so a `minimal_visual` storyboard (or one without a
  recognized icon keyword) renders exactly as before this ADR.
- Kind-to-accent-color mapping (`_KIND_ACCENT`): problem=risk-red,
  solution/summary/anchor=trust-teal, opening=warn-amber — matching the
  color-to-meaning system measured in the Compliance video series.

## Alternatives Considered

**A. Keep validation inline per call site, add new checks as needed.**
Rejected — this is the exact pattern the session's own testing feedback
flagged ("Fehlerbehandlung auf Primitive-Ebene adressieren, nicht
Callsite-Band-Aid"): every new rule would duplicate logic at N call sites
instead of 1.

**B. Emoji icons via a bundled color-emoji font (e.g. Noto Color Emoji).**
Deferred — adds a font dependency + FreeType color-glyph support path not
verified on the target host; vector primitives have zero new dependencies and
render identically everywhere Pillow runs.

**C. Hard-fail production on any didactic warning (strict mode).**
Rejected — the local Ollama fallback (`qwen3:1.7b`, CPU-only) measurably
under-shoots the character budget on this host (see E2E evidence below); a
hard failure there would make the pipeline unusable on exactly the
no-API-key, no-GPU configuration ADR-0711/ADR-0953 chose as the default
fallback. Soft warnings preserve "always produces a usable video" (ADR-0711's
own fallback invariant) while still making budget drift visible.

## E2E-Wiring-Proof

`tests/test_e2e_didactic_corvin_compliance.py`:

1. **Call-site-wiring proof** (dead-mechanism class) — greps `skill.py` to
   assert `validate_storyboard_dict()`/`validate_storyboard()`/`_detect_icon()`/
   `_draw_icon()`/`detect_didactic_strategy()` are referenced from
   `generate_storyboard_with_llm()` / `orchestrate_video()` / `_render_slide_image()`,
   and that no inline `if len(scenes) > N` or `if total_duration > max_ms`
   check has been reintroduced at any call site.
2. **Primitive unit proof** — `validate_storyboard_dict()` rejects 101 scenes,
   rejects a storyboard exceeding its duration cap, and warns (without
   failing) on a `minimal_visual` scene that blows through its character
   budget.
3. **Icon rendering proof** — `_detect_icon()` parses known keywords;
   `_render_slide_image()` produces a real PNG (magic-byte checked) whose
   pixels contain the expected kind-accent RGB triple (not just "a file
   exists").
4. **Full pipeline E2E** (`@pytest.mark.e2e`) — runs the REAL pipeline
   (Ollama `qwen3:1.7b` storyboard generation, real gTTS synthesis, real
   Pillow rendering, real ffmpeg mux) against the task *"Erkläre, wie
   CorvinOS Compliance für autonome KI-Agenten sicherstellt"*, then asserts:
   - the produced `output.mp4` is a real H.264+AAC mux (ffprobe `-show_streams`)
   - the **ffprobe-measured** duration matches the worker's **self-reported**
     sum within 2 seconds (the "miss die Summe, nicht das Backend einzeln"
     feedback: an independent measurement of the aggregate artifact, not
     trusting any one worker's report)
   - SRT cue count equals scene count (sum check)
   - the generated narration (not the task string) actually mentions a
     compliance/Corvin domain term — proving the LLM produced on-topic
     content, not a generic placeholder

**Measured result (this host, 2026-10-06):** 6 scenes, `rich_visual`
strategy (correctly auto-detected from "Compliance"/"Architektur"
keywords), 687,237-byte `output.mp4`, ffprobe duration 36.9s (worker-reported
36s — within tolerance), real narration covering identity verification,
multi-factor authentication, and zero-trust architecture. Validator correctly
flagged all 6 scenes as `scenes_under_budget` (qwen3:1.7b's narration
averaged 74 chars/scene against the rich_visual 200–400ch target) — a real,
honest soft-warning, not a fabricated pass. 13/13 new tests pass; 76/80
pre-existing plugin tests pass unchanged (4 pre-existing `test_api_routes.py`
failures are a validation-ordering bug unrelated to this ADR's scope, present
before and after).

## Consequences

### Positive
- One rule-change surface (`narration_validator.py`) instead of N call sites.
- Icons render correctly on a host with no emoji font coverage.
- Soft warnings are audited (`emit_feedback`) without narrowing the
  "pipeline always produces something" invariant from ADR-0711.

### Negative / Risk
- The local Ollama fallback does not reliably hit the rich_visual character
  target — mitigated by treating budget as a warning, not a gate; a future
  ADR may tune the prompt further or accept the gap as a known CPU-model
  limitation.
- `detect_didactic_strategy()` is a keyword heuristic, not learned — a task
  with no system/concept keyword defaults to `rich_visual`, which may not
  always be right. Acceptable for v1; a learning-loop-tuned classifier is
  future work (see ADR-0003 §Future Enhancements).

## Related Decisions

- **ADR-0003** (Didactic Storyboard System): this ADR implements its
  `didactic_level` concept concretely as `didactic_strategy`, scoped to text
  budget + visual system rather than ADR-0003's broader voice-sync/animation-tier
  schema (no animation-tier infrastructure exists in this plugin's actual
  code path — ADR-0003's schema describes a design later superseded by the
  simpler real pipeline in `src/skill.py`).

---

**Status: ACCEPTED — integrated, E2E-proven on 2026-10-06.**

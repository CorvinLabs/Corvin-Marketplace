---
id: ADR-0953
status: proposed
supersedes: []
depends_on: []
related: [ADR-0001, ADR-0002, ADR-0003, ADR-0951, ADR-0952, ADR-0698]
commits: []
paths:
  - "plugins/contributor/media/video_producer/src/"
  - "plugins/contributor/media/video_producer/tests/"
  - "plugins/contributor/media/video_producer/README.md"
docs:
  - "plugins/contributor/media/video_producer/docs/"
---

# ADR-0953 — Consolidation: one Video Producer, not eleven dead clusters

**Status:** Proposed
**Date:** 2026-10-03
**Deciders:** Claude Sonnet 5, Gordon Shumway

## Problem

An operator-requested adversarial review of the CorvinOS console's Video Producer
surface (`core/console/corvin_console/routes/video_producer_api.py`) found and hardened
the plugin modules that are actually loaded: `src/__init__.py`, `src/models.py`,
`src/storage.py`, `src/skill.py`, `src/async_runner.py` (~850 LoC). A follow-up full
reachability audit of the rest of `src/` (28 top-level files, 11 sub-packages, ~16 800
LoC) found that **none of it has a production caller** — not the console route, not
`async_runner.py`, not `skill.py`. Verified by import-chain tracing from all three live
entry files plus a repo-wide reverse search (`grep -rl "import <name>"`) that found zero
importers for `director/`, `verification/`, `executor_skill_2_0/`,
`llm_synthesis_skill_2_0/`, `renderers_skill_2_0/` anywhere, including tests.

This is not a new problem this ADR introduces — it is the one `ADR-0001`/`ADR-0002`/
`ADR-0003`/`ADR-0951`/`ADR-0952` and every status document in this repo root
(`DEPLOYMENT_STATUS.md`: "✅ PRODUCTION READY", "78+ tests passing", "ALL CONSTRAINTS
PASSED") describe and build on. All of that documents the **same dead architecture** —
the 3-tier renderer (`maestro.py` → `phase5/` → Blender/Three.js/Manim), none of which
the live console path ever calls.

**Two files are actively misleading, not just stale:** `video_assembler_real.py` and
`voice_worker_real.py` claim to be the "real" (non-stub) implementation by name, but
both literally return a fixed byte string (`b"MP4_STUB_DATA"`, `b"AUDIO_STUB"`) instead
of doing any encoding or synthesis.

## Context — what the audit found (full detail: the review transcript this ADR follows)

- **11 duplicate/competing clusters**, 0 of them live: TTS (4 implementations —
  `voice_worker.py`, `voice_worker_real.py`, `voice_synthesizer.py`, `voice_openai.py`),
  video assembly (3 — `video_assembler.py`, `video_assembler_real.py`,
  `video_ffmpeg.py`), asset analysis (2), screenshot capture (2), YouTube upload (2),
  three independent "Maestro" orchestrators (this plugin's `maestro.py`, this plugin's
  `src/video_producer/orchestrator.py`, and CorvinOS core's own
  `core/skills/video_producer/maestro.py`), a complete renderer-tier subsystem
  (`tier_dispatcher.py`, `threejs_renderer.py`, `blender_async_executor.py`,
  `phase5/*`), a complete content-verification subsystem, a complete "Skill 2.0"
  generation (`llm_synthesis_skill_2_0/`, `renderers_skill_2_0/`,
  `executor_skill_2_0/`) that is not merely unreachable but **internally broken** —
  `executor_skill_2_0/orchestrator.py` imports `..llm_synthesis.spec_schema` and
  `..renderers.frame_renderer`, packages that don't exist under those names (the real
  directories are suffixed `_skill_2_0`) — and several learning/quality/settings
  side-modules.
- **`src/video_producer/`** is a second, complete, self-contained package (own
  `__init__.py`, `orchestrator.py`, `types.py`, `__main__.py`) with its own
  `Storyboard`/`Scene` types that **collide by name** with `models.py`'s. Its
  `learning_optimizer.py` imports `core.learning.learning_events` — a CorvinOS core
  path that should not be resolvable from inside a marketplace plugin sandbox at all;
  this is itself a plugin-isolation question independent of consolidation.
- **Two of the four upstream ADRs this ADR references two out-of-date plugin paths**:
  `ADR-0698`'s `paths:` says `plugins/contributor/video_producer/` (no `media/`);
  `DEPLOYMENT_STATUS.md`'s deployment command says the same. The live code is at
  `plugins/contributor/media/video_producer/` — a third path segment variant. This path
  drift is why `video_producer_api.py` on the CorvinOS side carries a 7-entry fallback
  search list instead of one fixed location.

## Decision

Consolidate on the verified live cluster (`models.py`/`storage.py`/`skill.py`/
`async_runner.py`/`__init__.py`) as the one Video Producer implementation. Four phases,
executed as separate, individually revertible commits:

**Phase A — Documentation truth (this ADR, now):**
`README.md` rewritten to describe the live path only; this ADR filed as the canonical
record; `DEPLOYMENT_STATUS.md` / `docs/ARCHITECTURE.md` / `PHASE-1-STATUS.md` /
`PHASE1_IMPLEMENTATION_REPORT.md` / `PRODUCTION_VERIFICATION_REPORT.md` /
`WAVE6_COMPLETE.md` marked with a pointer to this ADR (kept, not deleted — they are
accurate records of design intent, just never-activated ones); `ADR-0001`/`0002`/`0003`/
`0951`/`0952` cross-linked here as describing the same dead design, not superseded
outright (they document real design work; the record stays, the status claim does not);
a `pre-consolidation-2026-10-03` git tag as the rollback anchor.

**Phase B — Value extraction (before any deletion):** four candidates evaluated for
whether to fold into the live path before their cluster is removed:
`voice_openai.py` (real OpenAI TTS with SHA256 caching — gTTS is an unofficial,
no-SLA endpoint) as a TTS upgrade; `video_ffmpeg.py` ("Week 11", tuned H.264/CRF
settings) compared against the inline ffmpeg call in `skill.py`; `screenshot_puppeteer.py`
and `asset_analyzer.py` as closers for two real feature gaps the live path has today
(no screenshot capture, no PPT/asset deep-read) — each needs its own task with an E2E
proof before integration, not a blind copy.

**Phase C — Removal**, staged by risk, smallest commits first: (1) the three
provably-dead and internally-broken clusters (`*_skill_2_0/`, `verification/`,
`maestro_verification_integration.py`) — zero risk, they never ran; (2) the duplicate
pairs per the Phase B decision; (3) the two dead Maestro orchestrators and
`src/video_producer/` — only after Phase A's README correction is live, since that is
what currently points at them; (4) the now-dead tests (13 files identified that import
only dead modules).

**Phase D — Verification:** the five live-path test files
(`test_models.py`/`test_storage.py`/`test_skill.py`/`test_api_routes.py`/
`test_review_2026_10_03.py`) plus CorvinOS's own
`core/console/tests/test_video_producer_routes_e2e.py` stay green throughout; a
post-removal `grep -rl` sweep for each removed module's name (not just its import form)
guards against a dynamic/string-based loader this audit's static analysis would miss.

## Alternatives considered

**Keep everything, document which parts are dead.** Rejected: this is the state the
repo was already in (`DEPLOYMENT_STATUS.md` claims production-ready for dead code) —
documentation alone did not prevent the drift and won't prevent the next one.

**Activate the 3-tier renderer instead of deleting it.** Rejected as this ADR's scope:
CorvinOS's own video-producer work independently reached the same conclusion for its
own diagram-rendering needs (`ADR-2207`/`CONCEPT-0089` in Corvin-Knowledge: prefer the
already-working Playwright/HTML/CSS/SVG path over Blender/Manim's render-time and
integration cost). Re-opening Blender/Three.js/Manim here would fight that decision, not
align with it. If a future task genuinely needs premium rendering, it is a fresh
decision, not a resurrection of this dead code.

**Delete now, skip Phase B.** Rejected: `voice_openai.py` and `screenshot_puppeteer.py`
contain real, never-wired functionality (OpenAI TTS with caching; working Puppeteer
capture) that closes gaps `ADR-0693`/`ADR-0694` actually asked for. Deleting first and
re-deriving later is strictly more expensive than evaluating first.

## Consequences

- `src/` shrinks from ~17 600 LoC / ~40 files to roughly 850–1 500 LoC (depending on
  Phase B outcomes), one orchestration path, one TTS path, one assembly path.
- The plugin's own `docs/ADR-0001`/`0002`/`0003`/`0951`/`0952` remain on disk as design
  history but are no longer citable as "what this plugin does" — only this ADR and the
  corrected README are.
- Screenshot capture and asset deep-read remain **absent** until a Phase B follow-up
  task ships them — this ADR does not claim to close ADR-0693/ADR-0694's gaps, only to
  stop the duplicate-implementation drift.
- `src/video_producer/`'s cross-boundary import of `core.learning.learning_events` is
  removed as a side effect of deleting the package, not independently investigated —
  flagged here in case the same pattern exists elsewhere in the marketplace.

## Operator Notes

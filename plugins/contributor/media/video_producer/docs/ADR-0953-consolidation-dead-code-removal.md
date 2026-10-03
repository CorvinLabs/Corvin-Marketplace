---
id: ADR-0953
status: accepted
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

**Status:** Accepted (Phases A–D executed and verified 2026-10-03; see "Phase B — resolved" / "Phase C/D — resolved" below)
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

## Phase B — resolved (2026-10-03)

All four extraction candidates evaluated by reading the code, not the surrounding
docstrings' claims:

- **`voice_openai.py`** — real OpenAI `tts-1-hd` call with SHA256 caching, but its
  `execute()` interface aggregates every scene's narration into **one** TTS call
  (`" ".join(s["narration"] for s in scenes)`), while the live path needs one audio file
  per scene (variable per-scene durations feed the concat pipeline). Worse, it
  *estimates* duration from word count (`words / 2.5`) instead of measuring it — the
  live path already measures via `ffprobe`, so adopting this as-is would be a quality
  **regression** against ADR-0694's "no estimates, all measured" constraint. **Not
  integrated.** If OpenAI TTS is wanted over gTTS later, treat the API-call shape here
  as a reference, not a drop-in.
- **`video_ffmpeg.py`** — the only real yield: `-crf 18 -preset slow` is a genuine
  quality improvement over the live path's unset (ffmpeg-default) values. Its own
  architecture (PNG-sequence + one shared audio track) was not adopted — the live path's
  per-scene-clip-then-concat design is the better fit for variable scene durations, which
  a single shared audio track cannot represent. **Extracted:** the two flags were added
  to `skill.py::_assemble_scene_clip` (alongside the existing `-tune stillimage`, which
  `video_ffmpeg.py` lacks and the live path's still-image-per-scene case needs). Verified
  with a real `ffmpeg`+`ffprobe` round trip (H.264 High profile, AAC-LC, correct
  duration) — not just a syntax check — plus the full live-path test suite unchanged at
  60/64 passing (the 4 pre-existing `test_api_routes.py` failures predate this review and
  are unrelated: they exercise a different, non-console route shape).
- **`screenshot_puppeteer.py`** — depends on a console "scene" query-parameter API
  (`{console_url}?scene=${id}`) that does not exist anywhere in CorvinOS, plus an
  undeclared Node/Puppeteer dependency. **Not integrated.** CorvinOS already has a real,
  previously-verified alternative for this exact gap:
  `core/skills/video_producer/workers/screenshot_capturer.py` (Playwright, Python-native,
  no new runtime dependency) — closing the screenshot-capture gap (ADR-0694) should start
  there, as a separate task, not from this dead file.
- **`asset_analyzer.py`** — its own docstring admits it: `_extract_ppt_sections()` is "a
  stub: hardcoded for testing" and always returns the same 3 fixed sections regardless of
  the input PPT. **Not integrated** — there is no extractable logic here, only an
  interface shape; closing the asset-analysis gap (ADR-0693) means writing the
  `python-pptx` reader from scratch, as a separate task.

**Net result:** of ~16 800 dead LoC, exactly two flags (`-crf 18 -preset slow`) were
worth keeping. Phase C can proceed against the full dead-cluster list in the Decision
section above without further extraction review.

## Phase C/D — resolved (2026-10-03)

Removal executed in four staged commits (smallest-risk first, each independently
revertible against the `pre-consolidation-2026-10-03` tag), verified with a
full test run after every commit:

- **C.1** — the three never-reachable, internally-broken clusters
  (`executor_skill_2_0/`, `llm_synthesis_skill_2_0/`, `renderers_skill_2_0/`,
  `verification/`, `maestro_verification_integration.py`) plus the four tests
  that imported them. Also corrected `plugin.json`'s `entry_points.renderers`
  block, which named four of the just-deleted modules by Python path —
  confirmed via CorvinOS source that no loader reads this JSON field at all
  (`importlib.metadata.entry_points()` reads packaging metadata, not this
  key). A path-spec error in the first attempt's multi-path `git add`
  silently dropped the `plugin.json` fix from that commit; caught by `git
  diff` against the committed tree (not just the staged one) and corrected
  in a dedicated follow-up commit — logged here because the same class of
  error recurred twice more below, and is worth watching for in any `git
  rm`/`git add` with multiple paths in one invocation: a single
  already-gone or nonexistent path aborts the ENTIRE command before any of
  the other paths are processed.
- **C.2** — the duplicate TTS (4 implementations)/assembly (3)/screenshot
  (2)/YouTube (2) clusters and the full Blender/Manim/Three.js tier-render
  system (`tier_dispatcher.py`, `threejs_renderer.py`,
  `blender_async_executor.py`, `phase5/`), plus `src/workers/` (3 more TTS
  variants the original audit's `src/`-only sweep had already covered but
  worth naming explicitly) and the tests that imported them.
- **C.3** — the second orchestrator package (`src/video_producer/`,
  `src/maestro.py`) and the remaining side-modules (learning/quality/settings
  helpers, `director/`, `web/`, the two Phase-B-rejected asset-analyzer
  files). `tests/test_plugin_registration.py` was rewritten rather than
  deleted — it mixed legitimate manifest/structure assertions with five
  tests requiring `src/video_producer/` to exist; removing only the latter
  also fixed a pre-existing, unrelated bug (a class-local pytest fixture
  `TestPluginIntegration` could never see, now module-scoped).
- **C.4** — the last 9 dead test files, leaving exactly the 8 files that
  import only the live cluster.
- **D (verification)** — a full reachability re-sweep after C.4 turned up
  two items the original `src/`-focused audit had not covered because they
  live at the plugin root, not under `src/`: a second, independently-read
  manifest (`plugin.yaml`, confirmed live via
  `core/plugins/corvin_plugins/manifest.py`'s `console_panel` field) with
  the same stale TTS/YouTube claims as the now-fixed `plugin.json`, and a
  second ADR directory (`docs/ADRs/`, plural — distinct from `docs/ADR-NNNN-
  *.md`) holding 5 proposed ADRs + 1 concept describing exactly the modules
  removed in C.3. Both corrected with the same pattern as Phase A. `provider.py`
  (the actual `corvin_plugins` loader entry point) was read and needed no
  change — it only declares plugin lifecycle, never imports from the removed
  clusters.

**Final numbers:** `src/` went from ~40 files/~17,600 LoC to 5 files/999 LoC.
Test suite: 58 failed + 23 errors at the start of Phase C → 4 failed + 0
errors at the end (the 4 are the pre-existing, review-independent
`test_api_routes.py` mismatches identified before any Phase C change — zero
new failures introduced). CorvinOS's own
`core/console/tests/test_video_producer_routes_e2e.py` — the hardened,
tenant-isolated path this entire plugin now exists to serve — stayed 9/9
passing throughout, confirming the deletions never touched what the console
actually calls.

## Operator Notes

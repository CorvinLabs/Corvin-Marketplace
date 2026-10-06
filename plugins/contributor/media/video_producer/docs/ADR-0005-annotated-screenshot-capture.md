---
id: video-producer:ADR-0005
status: accepted
depends_on: [video-producer:ADR-0004]
related: [CONCEPT-0095, ADR-0694]
paths:
  - "src/screenshot_capturer.py"
  - "src/screenshot_annotator.py"
  - "src/models.py"
  - "src/skill.py"
  - "requirements.txt"
docs: []
plugin_info:
  name: "video-producer-skill-2.0"
  version: "1.0.0"
---

# ADR-0005: Annotated Screenshot Capture — Playwright Worker, Allowlist, Spotlight Annotation

**Status:** ACCEPTED
**Decision:** Implement CONCEPT-0095 (annotated screenshot capture for UI
walkthrough videos) as two new modules — a Playwright-based capturer and a
pure-PIL annotator — wired into `orchestrate_video()`'s per-scene loop for
`kind=="screenshot"`, with a hard-coded localhost-only URL allowlist.
**Depends On:** [video-producer:ADR-0004]

---

## Context

CONCEPT-0095 specified closing a real gap: `Scene.kind=="screenshot"` existed
in the data model and `skill.py` branched on it, but the body was a literal
placeholder string — nothing in the live plugin ever captured a real
screenshot. The concept named three structural requirements: (1) a
CSS-selector-driven highlight, never guessed pixel coordinates, (2) a
localhost-only egress allowlist as a load-bearing security boundary, not a
default-open convenience, and (3) reuse of the plugin's existing
vector-primitive/kind-accent-color vocabulary (ADR-0004) for the annotation
itself.

## Decision

### Conceptual level

A screenshot scene now carries two new optional fields on `Scene`
(`screenshot_url`, `highlight_selector`) instead of a new `Scene.kind` value
— the existing `"screenshot"` kind already meant "capture something real";
these fields say *what* and *where to point*. A selector that doesn't
resolve, or a URL outside the allowlist, is a hard error: this plugin never
ships an un-annotated or wrong-page screenshot silently.

### Structural level

**Two modules, matching the plugin's existing separation of concerns**
(narration validation is separate from rendering; CONCEPT-0095 asked for the
same split between capture and annotation):

- `src/screenshot_capturer.py` — `async def capture_screenshot(url, out_path,
  highlight_selector=None, ...)`. Three fail-closed gates: URL allowlist
  (`validate_screenshot_url`), selector-resolution, and a ported
  Visual-Content-Spec check (`_validate_screenshot_content`) rejecting
  placeholder/solid-color captures.
- `src/screenshot_annotator.py` — `def annotate_screenshot(image_path,
  bounding_box, out_path, color=...)`. Pure PIL `ImageDraw.rounded_rectangle`
  spotlight outline, default color `(224, 160, 50)` — the same `_COLOR_WARN`
  `skill.py` already uses for "opening" scenes, reusing the existing
  kind-to-accent semantic map rather than inventing a fourth meaning.

**Call-site wiring:** `orchestrate_video()`'s per-scene loop now branches
`if scene.kind == "screenshot": await _render_screenshot_scene(scene,
image_path) else: _render_slide_image(...)`. `_render_screenshot_scene` is a
new async helper in `skill.py` that calls `capture_screenshot()` then, if a
bounding box was resolved, `annotate_screenshot()` into a temp file and
`os.replace()`s it onto `image_path` — an atomic swap, never a partial write
a concurrent reader could observe.

**Deviation from CONCEPT-0095's suggested implementation shape:** the
concept suggested `screenshot_capturer.py` wrap its own
`asyncio.new_event_loop()` + `run_until_complete()`, matching the dead
reference implementation's sync-wrapper shape, reasoning that
"`orchestrate_video()` is not fully async-native end-to-end." Reading the
actual call site showed `orchestrate_video()` IS `async def` and the
per-scene loop body already runs inside that coroutine between `await`
points — so `capture_screenshot()` is a plain `async def`, awaited directly,
with no internal event loop. Nesting a second `run_until_complete()` inside
an already-executing coroutine is a real hazard (loop-identity confusion,
blocking the outer loop's thread) that the simpler direct-await avoids
entirely. This is a case of verifying the concept's implementation guess
against the real code before building it, not a disagreement with the
concept's actual design (allowlist, two-module split, annotation style) —
all three carried through unchanged.

### Implementation level — two things measured, not assumed, and fixed

**1. The ported Visual-Content-Spec threshold (0.95) was miscalibrated for
real console-style UIs — caught by testing against a real page, not by
trusting the reference implementation's comment that it was "already
proven."** A real local test page (dark flat background, one button)
measured `dominant_ratio=0.9913, unique_colors=158`. A genuinely blank page
(no elements) measured `dominant_ratio=1.0` EXACTLY, `unique_colors=1`. The
discriminating signal is `unique_colors` (158 vs. 1 — two orders of
magnitude), which `min_unique_colors=10` already catches independently;
`max_solid_color_ratio` is raised to **0.999** so it only fires on an
almost-exactly-blank frame, not on legitimately sparse real content (the
Corvin Console itself is a dark, mostly-flat-background UI by design — the
inherited 0.95 threshold would have rejected real Console screenshots as
"placeholders").

**2. Playwright's `Locator.bounding_box()` does NOT return `None` when a
selector never resolves** — it raises its own `TimeoutError` after waiting
up to the timeout. The first implementation only guarded `if box is None:`,
which that exception path never reaches; the fail-closed branch was
unreachable dead code until an actual missing-selector test exercised it and
surfaced a raw `playwright._impl._errors.TimeoutError` instead of
`ScreenshotCaptureError`. Fixed by catching Playwright's `Error` around the
`bounding_box()` call and translating it into `ScreenshotCaptureError`,
keeping the `if box is None:` check as a second, independent guard for the
(in-principle-reachable) detached-element case.

**3. Dependency:** `requirements.txt` gains `playwright>=1.40.0`, stated
plainly as a genuinely new runtime dependency (ADR-0953 Phase E's pruning
left none), with the required `playwright install chromium` post-install
step documented in a comment, matching the file's existing self-documenting
style.

**4. Allowlist:** `ALLOWED_SCREENSHOT_HOSTS = {"localhost", "127.0.0.1"}`,
hardcoded, not configurable via any scene field or job parameter — the
concept was explicit that relaxing this to arbitrary/configurable targets is
a separate ADR decision (new network-egress surface, CorvinOS L35 deny-by-
default model), not something to default open in this one.

## Alternatives Considered

**A. Sync-wrapper shape (asyncio.new_event_loop + run_until_complete),
matching the dead reference implementation exactly, as the concept
suggested.** Rejected after reading the real call site — see "Deviation"
above. Simpler and safer to await directly since the caller is already
async.

**B. Keep the inherited 0.95 Visual-Content-Spec threshold unchanged, since
the concept called it "a correct, already-proven pattern."** Rejected —
"already proven" described the reference implementation's original use
case (arbitrary website screenshots), not this plugin's actual target
(a dark, sparse admin console). Measuring against a real test page before
shipping caught a threshold that would have broken on real Console
captures; the concept's trust in the pattern was about the EXISTENCE of a
placeholder-rejection gate, not its exact calibration.

**C. Make the allowlist configurable (env var or scene field) from the
start, since a maintainer will likely want non-localhost targets
eventually.** Rejected per the concept's own explicit scoping — adding
configurability now would be exactly the "quietly default open" move the
concept warned against. A real need for non-localhost targets gets its own
ADR with its own threat model.

## Verification

- `tests/test_screenshot_capture_concept_0095.py`: 13 tests —
  3 call-site-wiring-proof (grep-based, asserting `_render_screenshot_scene`
  is actually called from `orchestrate_video` and actually calls
  `capture_screenshot`/`annotate_screenshot`), 4 allowlist-gate unit tests,
  2 annotation unit tests (real PIL pixel checks, source-image immutability),
  4 full E2E tests against a real local HTTP server + real Playwright
  Chromium (resolved bounding box, fail-closed on missing selector, capture
  without a selector, full capture→annotate pipeline). All 13 pass.
- Full plugin suite re-run after the change: 89 passed, 4 failed — the same
  4 pre-existing `test_api_routes.py` failures ADR-0004 already documented
  (unrelated route-shape mismatch, present before and after this change).
  Zero new regressions.
- Playwright + Chromium confirmed actually installed and working in this
  environment (`.venv-e2e`) before writing a single line of the worker code
  — a direct navigate→selector→bounding_box→screenshot round trip against a
  `data:` URL, verified real pixel dimensions and a real bounding box match.

## Consequences

### Positive
- `Scene.kind=="screenshot"` now does what it has always claimed to do —
  no more placeholder string shipped as if it were a real feature.
- Two real, measured bugs (threshold miscalibration, Playwright's
  TimeoutError-not-None behavior) caught by testing against a real target
  before they could ship, not by trusting prose claims about either the
  reference implementation or the concept's own implementation sketch.
- Allowlist boundary is a one-line, auditable constant — trivially greppable
  for a future security review, not buried in configuration.

### Negative / Risk
- Playwright + a Chromium binary (~200MB cached) is a materially heavier
  dependency than everything else in `requirements.txt`. Accepted per
  CONCEPT-0095's explicit framing: this is the cost of real capture, stated
  plainly rather than hidden.
- The allowlist is currently CorvinOS-Console-only in practice (hardcoded
  hostnames) — any future "screenshot a marketplace page" use case needs the
  follow-up ADR the concept already anticipated.

## Related Decisions

- **CONCEPT-0095** — the design this ADR implements.
- **video-producer:ADR-0004** — the validation-primitive, vector-icon, and
  kind-to-accent-color vocabulary this ADR's annotator reuses.
- **ADR-0694** (central Corvin-Knowledge) — original Voice + Screenshot
  worker design; this ADR is the closure of its screenshot half.

---

**Status: ACCEPTED — integrated, E2E-proven on 2026-10-06.**

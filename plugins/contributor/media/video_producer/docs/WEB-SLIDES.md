# Web slides

Scenes can be rendered as animated HTML slides in the visual language of
corvin-labs.com instead of the classic Pillow slide. Decision record: ADR-2238
(Corvin-Knowledge); implementation plan: PLAN-0940.

## How a scene becomes a web slide

A scene that carries a `template` is rendered as a web slide. Its `kind` keeps
its didactic meaning (title, problem, solution, ...). A scene without a
template renders on the Pillow path as before.

```json
{"id": "s2", "kind": "solution", "duration_ms": 12000,
 "narration_text": "...",
 "template": "diagram", "theme": "dark",
 "data": {"title": "Pipeline", "nodes": [{"label": "Storyboard"}, {"label": "MP4"}], "highlight": 1}}
```

Pipeline per web scene (`skill.orchestrate_video`):

1. `web_templates.build_document` validates `data` against the template's
   contract, escapes every string and builds one self-contained HTML document
   (fonts inlined, no script, no external URL).
2. `web_renderer.WebSlideRenderer` loads it in headless Chromium with
   JavaScript disabled and every network request aborted, waits until the
   bundled fonts have loaded (a font that fails stops the render instead of
   silently falling back), then pauses all Web Animations and steps
   `currentTime` frame by frame. Chromium runs with
   `--disable-threaded-animation --run-all-compositor-stages-before-draw`:
   without them the compositor thread could draw a frame that lagged the
   paused time (measured: up to 54 of 149 frames differing between two
   browser instances). With them, renders in separate browser instances were
   bit-identical in every run (tested per frame with SHA-256).
3. Frames always cover the complete entrance animation. If the narration is
   shorter, the audio is padded with silence, so a reveal (e.g. the rolling
   digits of `stat`) is never cut off mid-way (`_assemble_frames_clip`). If it
   is longer, the slide keeps moving when it has **ambient motion** (data
   pulses on `flow`/`diagram` edges, the orbit on `cycle`, the pulse ring on
   `line`/`timeline`, the shine on the highlighted `layers` slab): the renderer
   samples exactly one ambient period after everything has started
   (`FrameSequence.loop_start`) and the assembler repeats that period, via hard
   links, until the narration ends. Ambient animations loop with a duration
   that divides 4 s, so frame `loop_start + period` equals frame `loop_start`
   and the repeat has no jump (tested pixel-exact in `test_web_charts.py`).
   A slide without ambient motion holds its last frame. The frame directory is
   deleted as soon as the clip is encoded.

Every clip is 1920x1080, 30 fps, H.264 + AAC with identical parameters, so web,
classic and screenshot scenes concatenate without re-encoding. Reported
duration is measured on the encoded file. Videos carry no subtitles: no caption
file is written and the spoken text is never drawn on a slide (the classic slide
shows only its label and icon).

## Templates

All text is plain text. Limits are characters; `?` marks optional fields.
Every template accepts `eyebrow?` (40), a small mono label above the title.

| Template | Data | Motion |
|---|---|---|
| `hero` | `badge?` (60), `title` (70), `accent?` (60, italic amber line), `subtitle?` (220) | staggered rise, accent rule |
| `content` | `title` (80), `bullets` 1-5 (110 each) | bullets rise one by one |
| `stat` | `value` (number, below 1e9), `decimals?` 0-2, `prefix?` (4), `suffix?` (8), `label` (80), `caption?` (200), `locale?` de/en | rolling odometer digits |
| `diagram` | `title` (80), `nodes` 2-6 of `{label (28), sub? (48)}`, `highlight?` index | nodes appear, arrows draw |
| `chart` | `title` (80), `bars` 2-8 of `{label (24), value >= 0}`, `unit?` (8), `decimals?`, `highlight?`, `locale?` | bars grow |
| `compare` | `title` (80), `left`/`right` each `{title (40), points 1-4 (90)}` | cards rise; right card is accented |
| `quote` | `quote` (220), `attribution?` (80), `locale?` (typographic quotes) | rise |
| `code` | `title` (80), `language?` (24), `lines` 1-12 (90 each) | lines type in |
| `line` | `title` (80), `labels` 3-12 (12 each), `series` 1-3 of `{name (24, required with 2+ series), values: one number per label}`, `unit?`, `decimals?`, `highlight?` index, `locale?` | grid fades in, monotone curve draws, points pop along it, end values and a callout appear; ambient pulse ring on the last point |
| `donut` | `title` (80), `segments` 2-6 of `{label (28), value >= 0}`, `center_value?` (10), `center_label?` (28), `unit?`, `decimals?`, `highlight?`, `locale?` | segments sweep in one after another; the highlighted one is wider and glows; legend with shares (with `unit: "%"` the value column is dropped) |
| `flow` | `title` (80), `nodes` 2-8 of `{id ([a-z0-9_]{1,16}), label (24), sub? (36)}`, `edges` 1-12 of `{from, to, label? (18)}`, `highlight?` node id | layered left-to-right graph (no cycles, max 5 columns x 4 nodes); columns appear in order, curved edges draw; ambient data pulses travel every edge |
| `timeline` | `title` (80), `events` 2-6 of `{when (16), label (28), sub? (60)}`, `current?` index | progress line draws up to `current`, milestones pop; ambient pulse ring on `current` |
| `cycle` | `title` (60), `caption?` (180), `center?` (24), `steps` 3-6 of `{label (22), sub? (40)}`, `highlight?` | text left, loop right: numbered nodes pop, arcs with arrowheads draw; ambient orbit around the loop |
| `layers` | `title` (80), `layers` 2-6 of `{label (32), sub? (64), tag? (12)}` (first = top), `highlight?` | a slightly tilted stack builds from the bottom up; ambient shine sweeps the highlighted slab |

Unknown templates, unknown fields, wrong types and over-long text are
rejected. `stat`, `chart`, `line` and `donut` show numbers: the storyboard
prompt tells the LLM to use them only for figures that appear in the task.

The chart geometry is what D3 would compute — "nice" 1/2/5 axis ticks
(`web_geometry.nice_ticks`), monotone cubic interpolation without overshoot
(`monotone_path`, d3.curveMonotoneX), longest-path layering with one
barycentre sweep for graphs (`layer_dag`, `order_layers`) — computed in
Python, so a slide stays a static document and renders deterministically
with JavaScript disabled. D3 or Recharts in the page were rejected: both
animate with `requestAnimationFrame` timers that timeline seeking does not
control, and both would need script execution (and Recharts a React build).
Categorical colours (`c0`..`c5`: amber, slate, green, cream, light amber,
faint) are identities, not a value ramp.

Reveal timing follows the narration: entrance steps are spread so that
everything is on screen by about 55% of the scene's audio.

## Configuration (job config)

| Key | Default | Meaning |
|---|---|---|
| `web_slides` | `true` | `false` renders every scene on the Pillow path (configuration, not reported as a fallback) |
| `web_theme` | `dark` | default theme; a scene's own `theme` wins |
| `web_fps` | `30` | sampling rate of the animation (12-60) |
| `web_tokens_path` | bundled file | alternative design-token file, validated like the bundled one |
| `storyboard` | — | an operator-written storyboard; skips the LLM, same validation, web-slide contract enforced strictly (an invalid scene fails the job before any work) |
| `storyboard_backend` | `ollama` | where the storyboard LLM call goes: `claude_cli` (the host's Claude Code login, `claude -p` with no tools, no MCP, no settings, no saved session, prompt over stdin, run in an empty temp dir; binary from `CORVIN_CLAUDE_BIN` or PATH), `anthropic` (API key) or `ollama` (local `qwen3:1.7b`). A failed remote call falls back to Ollama; the job's `storyboard_llm` metadata names the backend that actually answered |
| `storyboard_model` | — | model id for `claude_cli` / `anthropic` (the console passes the newest Sonnet) |

These are plugin API keys, set by the host in the job config. The CorvinOS
console route passes only `storyboard_backend`/`storyboard_model`: the
Anthropic API with a key, else `claude_cli` when the CLI exists — both only
when L35 admits api.anthropic.com and L34 admits the task under the
`claude_code` engine — else `ollama`. Measured on the real prompt
(2026-10-08): qwen3:1.7b ~65 s with invalid or repeated templates, Sonnet 5.5
~14 s / ~$0.03 and Opus 5.5 ~17-42 s / ~$0.06 with 8 of 8 valid and 7-8
distinct templates — hence Sonnet. A remote model may write up to 8 scenes,
the local one 6. Everything else runs with the defaults (web slides on, dark
theme). A host
that starts passing `storyboard` must run its narration text through the same
pre-spawn gates as the task text (L44 acceptable use, L34 classification),
because that text is sent to the TTS service. `web_tokens_path` is a host-side
setting, never tenant input; it must be a regular JSON file of at most 64 KB.

LLM-written storyboards are untrusted: an invalid web-slide spec is removed
from that scene (it renders classic) and logged; it is never passed through.
Bidi overrides, zero-width characters and lone surrogates are stripped or
rejected, and any unexpected error in a web scene falls back to the classic
slide instead of failing the job.

## Fallback

If Playwright/Chromium is missing or cannot start, every web scene of the job
renders on the Pillow path. If a single render fails or times out (120 s),
that scene falls back. Each fallback is listed in the output metadata
(`web_render_fallbacks: [{scene, reason}]`), emitted as a `web_render_fallback`
feedback event and shown in the job's progress message. `renderers` lists the
renderer that produced each scene.

Requirement: `pip install playwright && playwright install chromium`
(already listed in `requirements.txt` for screenshot scenes).

## Design tokens

`src/web/design_tokens.json` holds both themes (colours taken from
corvin-labs.com), the three font families and the entrance timing. Values are
validated strictly before use, because they are written into CSS: colours
must be `#rrggbb` or `rgba(r, g, b, a)`, families must be one of the bundled
fonts (Newsreader, Instrument Sans, JetBrains Mono — OFL, licences in
`src/web/fonts/`), the easing must be a `cubic-bezier(...)`.

The older `video-producer-orchestrator/design_system.json` (blue, Inter) and
the colours in CONCEPT-0093 are not used by web slides.

## Figma

Figma is an optional token source, not a render dependency:

```bash
vault get figma_token | python -m src.figma_sync --file-key <FILE_KEY> --token-stdin --dry-run
vault get figma_token | python -m src.figma_sync --file-key <FILE_KEY> --token-stdin
```

It reads the file's local Variables (REST `GET /v1/files/:key/variables/local`),
maps them by name (see the module docstring: theme colours by mode name
light/dark, `heading_family`/`body_family`/`mono_family`, `rise_ms`),
resolves aliases, lists every variable it ignored, prints a diff and writes
the file atomically (keeping its file mode) only if the merged result passes
token validation. The token is read from stdin only, never printed, and HTTP
redirects are refused so the token header is never sent to another host. Exit codes: 0 ok, 2 usage,
3 refused by Figma (token scope or plan — the Variables API is plan-gated),
4 file not found, 5 network/HTTP, 6 result failed validation, 7 nothing
matched.

Not built: exporting Figma frames as illustrations into slides.
Not verified live: no Figma token exists on the development host (the vault
holds none), so the sync has only run against a local server that answers
like the Variables API. A live run needs a token with `file_variables:read`
on a plan that exposes the Variables REST API.

## Tests

```bash
pytest tests/test_web_templates.py tests/test_web_charts.py tests/test_web_renderer.py tests/test_figma_sync.py tests/test_web_slides_e2e.py
```

`test_web_slides_e2e.py` drives `start_video_production` (the function the
console's job runner calls) with real Chromium and ffmpeg and checks the MP4
with ffprobe; only the TTS cloud and, in one case, the storyboard LLM are
replaced; the `claude_cli` backend is driven through a stand-in executable
at the real process boundary (argv, stdin, cwd recorded). `test_web_charts.py`
checks the geometry, every refusal path, and — in real Chromium — that the
ambient period is pixel-seamless and actually moves. `test_figma_sync.py` runs the CLI as a subprocess against a local
server that answers like the Figma API; a live call needs a real token.

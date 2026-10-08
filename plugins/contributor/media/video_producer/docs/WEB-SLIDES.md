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
   longer, ffmpeg holds the last frame; if it is shorter, the audio is padded
   with silence, so a reveal (e.g. the rolling digits of `stat`) is never cut
   off mid-way (`_assemble_frames_clip`). The frame directory is deleted as
   soon as the clip is encoded.

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

Unknown templates, unknown fields, wrong types and over-long text are
rejected. `stat` and `chart` show numbers: the storyboard prompt tells the
LLM to use them only for figures that appear in the task.

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

These are plugin API keys, set by the host in the job config. The CorvinOS
console route passes none of them today: console jobs run with the defaults
(web slides on, dark theme) and the templates the storyboard LLM picks. A host
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

## Tests

```bash
pytest tests/test_web_templates.py tests/test_web_renderer.py tests/test_figma_sync.py tests/test_web_slides_e2e.py
```

`test_web_slides_e2e.py` drives `start_video_production` (the function the
console's job runner calls) with real Chromium and ffmpeg and checks the MP4
with ffprobe; only the TTS cloud and, in one case, the storyboard LLM are
replaced. `test_figma_sync.py` runs the CLI as a subprocess against a local
server that answers like the Figma API; a live call needs a real token.

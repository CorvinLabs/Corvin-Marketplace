# CorvinTV — Create Narrated Videos with Animated Slides

> **CorvinTV was called "Video Producer" until version 1.6.0.** Same plugin, new name: the registry id (`video_producer`), the console API (`/v1/console/video/...`), the tenant data folder and every audit event name are unchanged, so existing installs, videos and automations keep working. The marketplace listing moved from `buildin/media/corvintv` to `buildin/media/corvintv`; a tenant that still carries the old listing is upgraded at the next boot (CorvinOS `default_plugins.yaml`, `replaces:`).

**What ships live today: turn a task description into a professional narrated MP4 with animated slides and expressive diagrams in the corvin-labs.com design language.**

> **Version 1.7.2 — first-party (buildin) plugin, installed and enabled on every fresh CorvinOS installation.** New: the `board` template (an imported Penpot design revealed step by step while the narration speaks) and `bento` (a grid of two to six tiles); narration is OpenAI TTS with edge-tts as the fallback (Piper is gone: its quality was too poor); fixes found by an end-to-end tech demo. **No "production ready" claim:** the ready gate (ADR-2247) has not reported a full pass; what is measured is in the gate rows and `RELEASE-NOTES.md`. See [ADR-2249](../../../../Corvin-Knowledge/decisions/ADR-2249-video-producer-expressive-scenes-pen-drawn-canvas.md) (expressive scenes), [ADR-2238](../../../../Corvin-Knowledge/decisions/ADR-2238-video-producer-deterministic-web-slide-renderer-html-css.md) (web slides) and [ADR-2211](../../../../Corvin-Knowledge/decisions/ADR-2211-video-producer-openai-tts-default-and-layout-collision-resolution.md) (narration).

## How it works

**Pipeline (all four steps happen automatically):**

1. **Storyboard** → Claude writes scenes + narration text (Anthropic API with a key, else the host's Claude Code login; both gated by L35/L34; there is no local fallback — CorvinTV needs to be online with Claude Code available)
2. **Narration** → each scene is spoken by OpenAI TTS (`tts-1-hd`, voice `onyx`); when OpenAI declines (no key, invalid or exhausted key, rate limit, timeout) that scene is spoken by edge-tts instead and the job records `tts_tier_below`; if edge-tts declines too, gTTS (Google Translate voice, no key, needs network, the text goes to Google) is the last resort. If all decline the job fails with a named error — there is never a silent video. This chain is the default (`tts_engine: "auto"`); `openai` means OpenAI only, without a fallback
3. **Slides** → Animated web slides in **corvin-labs.com design** with 19 built-in templates whose reveals and focus follow the narration sentence by sentence (deterministic Chromium rendering, ambient loops, monotone curves, DAG graphs); fallback to Pillow if Chromium unavailable
4. **Assembly** → FFmpeg encodes MP4 at 1920×1080 / 30fps with audio synced to narration

**Result:** a professional 1–3 minute MP4 video ready to share. **No subtitles** (ADR-2211 design decision).

**Corvin explainers are grounded:** when the host passes a `grounding_pack` (the CorvinOS console builds one from Corvin-Knowledge decisions and the tracked code, for the knowledge base's own tenant, gated and audited), the storyboard may only state numbers, identifiers and paths from it, and can show real console screenshots (`console_still`) and a "you are here" layer strip (`map`). See [docs/WEB-SLIDES.md](docs/WEB-SLIDES.md#grounded-storyboards-adr-2240).

**Status per job:** stored in metadata (which TTS ran, which storyboard model, any rendering fallbacks, template repairs)

### Execution and deadlines (unreleased 1.5.0)

Each production runs in its own process; every external call (ffmpeg, ffprobe, the model, TTS, the browser) goes
through `src/deadline.py` and is stopped, with its process tree, when its deadline or the job's budget
(`min(3 x max_duration_minutes x 60, 2700)` s) runs out. The console can cancel a running job
(`POST /video/jobs/{id}/cancel`). A bare `subprocess.run` in `src/` fails `tests/test_deadline.py`.

## How to use it

**From the Console:** Open `/video-producer` panel, paste a task description, click "Create Video"

**Via API (if integrating into another system):**
```bash
# Start a video job
curl -X POST http://localhost:8765/v1/console/video/jobs \
  -H "Content-Type: application/json" \
  -d '{"task": "Create a video explaining how cumulative probability distributions work in statistics. Show examples with visualizations. End with a summary. Keep it 2 minutes."}'
# Response: {"job_id": "video_abc123", "status": "queued"}

# Check status
curl http://localhost:8765/v1/console/video/jobs/video_abc123
# Response: {"job_id": "...", "status": "in_progress", "progress": 45}

# Download finished video
curl -O http://localhost:8765/v1/console/video/videos/video_abc123/download

# Delete a finished video and all its files (unreleased 1.5.0; a running job answers 409)
curl -X DELETE http://localhost:8765/v1/console/video/jobs/video_abc123
```

**Storage (unreleased 1.5.0):** each workspace's video store has a quota, `spec.video_producer.storage_quota_gb` in
its `tenant.corvin.yaml` (default 5 GB); beyond it new videos are refused until you delete some. A GDPR erasure
request removes every video job the person created or that names them (see the guide in
CorvinOS `docs/skills/video-producer-guide.md`).

**Tenant isolation (unreleased 1.5.0):** the console loads this plugin only for a workspace that enabled it
(never at console start), and no storyboard can make the plugin fetch a page - a `screenshot` scene from any
source renders as an ordinary slide (since 1.4.1). Proofs are in CorvinOS `docs/skills/video-producer-guide.md`
("Tenant isolation").

**Quality signals (unreleased 1.5.0):** every job's `report.json` carries named signals, among them `still_time`
(share of the runtime in which the slide stands still). The cue-to-word alignment (`cue_alignment`, whisper-1) runs
only when the operator asks for it (CorvinOS `POST /v1/console/video/jobs/{id}/measure`, gated like the job's TTS).
Store a German/English pair in Corvin-Videos with `scripts/store_video_pair.py`: it refuses a pair whose two
versions differ in scenes, templates or numbers (`language_parity`) and writes the result into `sources.md`.
Before a release: `python scripts/release_lint.py` (versions, placeholders, named tests and paths; also run by the
Marketplace workflow `video-producer-release-lint.yml`).

## Configuration & Customization

### Environment (on the host running CorvinOS)

**Required for best quality:**
- `OPENAI_API_KEY` or `CORVIN_TTS_OPENAI_KEY` — OpenAI TTS key for narration (required for `openai` engine, default)

**Optional:**
- `ANTHROPIC_API_KEY` — fallback for storyboard generation. In the CorvinOS console the host's Claude Code login (the subscription CorvinOS itself runs on) always comes first and the CLI is started without this key; the key is used only when the host has no Claude Code CLI. If neither exists, the job is refused. A failing CLI call reports the CLI's own message in the job error.

### Settings

**In the CorvinOS console** only the narration engine is user-selectable (Settings panel); the panel also reports whether OpenAI and Chromium are available on the host. The other options below are plugin API keys for a host that calls the plugin directly — the console passes none of them, so console jobs always use web slides with the default theme.

| Setting | Default | Options | Purpose |
|---------|---------|---------|---------|
| `tts_engine` | `openai` | `openai` \| `auto` \| `gtts` | Which narrator to use (console + API; see [ADR-2211](../../Corvin-Knowledge/decisions/ADR-2211-video-producer-openai-tts-default-and-layout-collision-resolution.md)) |
| `web_slides` | `true` | boolean | API only: animated web slides (Chromium) vs. classic Pillow slides |
| `web_theme` | `dark` | `dark` \| `light` | API only: colour scheme of the web slides |
| `web_fps` | `30` | integer 12–60 | API only: render frame rate (higher = longer render time) |

### Your Own Look (Style Packs)

A *style* — palette, fonts, logo, wordmark, decoration — is a validated, per-workspace object created from a PowerPoint (`.pptx`/`.potx`) or a board exported from Penpot as SVG in the console panel. Without a style the CorvinOS look is used and its output is pinned byte-for-byte by golden tests. Details: [USER-GUIDE.md](USER-GUIDE.md) (Step 6). Logos are PNG-only (an SVG supplies colours and fonts, never a logo; a Penpot board can also be imported as an image, see [docs/PENPOT-IMPORT.md](docs/PENPOT-IMPORT.md)), the deck is never stored, and contrast rules are enforced when a style is saved.

### Web Slide Templates

The plugin ships with **19 built-in templates** (hero, content, line chart, donut, flow graph, timeline, cycle, layers, stat, diagram, compare, quote, code, chart, console still, canvas, still, bento, board). Each item of a slide appears when the narration names it and is highlighted while it is explained — see [docs/WEB-SLIDES.md](docs/WEB-SLIDES.md) for details. The storyboard LLM automatically picks templates based on the scene content; you don't need to specify them. Unreleased (1.6.0): a `canvas` template (hand-drawn sketch board, see [docs/WEB-SLIDES.md](docs/WEB-SLIDES.md)) is offered to the storyboard model for what no other template can show, and a scene can continue the board of an earlier one.

## Testing

**Live-path tests** (run these to verify the plugin works):
```bash
cd plugins/buildin/media/corvintv
# needs pytest, pytest-asyncio, playwright (+ `playwright install chromium`) and ffmpeg
python -m pytest tests/test_skill.py tests/test_models.py tests/test_storage.py \
        tests/test_web_charts.py tests/test_web_slides_e2e.py -q
```

Last run (2026-10-09, dev host): 91 passed in 160 s. `tests/test_web_slides_e2e.py` drives the real pipeline (fake `claude` binary, real Chromium, real ffmpeg) and is the end-to-end proof; there is no separate "job end to end" test.

Known red tests: none since the 1.5.0 baseline work (ADR-2247 R0, `974bf30`). The four red status-code tests of that run tested a copy of the routes written inside their own test file; that file was deleted (the real routes are tested in CorvinOS), and `test_icon_renderer_is_called_from_render_slide_image` was made a behavioural test.

## Documentation

### For Using This Plugin
- **[docs/PENPOT-IMPORT.md](docs/PENPOT-IMPORT.md)** — Penpot boards as styles and images: what is read, what is dropped, limits, audit
- **[docs/PENPOT-STACK-RUNBOOK.md](docs/PENPOT-STACK-RUNBOOK.md)** — Optional Penpot stack (strand B): start, stop, backup/restore, update path, failure patterns
- **[docs/PENPOT-STACK-RESULTS.md](docs/PENPOT-STACK-RESULTS.md)** — Measured results for the stack: setup time, RAM, UI text export, MCP verdict, CVE review
- **[docs/WEB-SLIDES.md](docs/WEB-SLIDES.md)** — All 15 slide templates, data contracts, narration-synced timing
- **[ADR-2238](../../Corvin-Knowledge/decisions/ADR-2238-video-producer-deterministic-web-slide-renderer-html-css.md)** — Web-slide renderer design (Chromium, deterministic frames, ambient loops)
- **[ADR-2211](../../Corvin-Knowledge/decisions/ADR-2211-video-producer-openai-tts-default-and-layout-collision-resolution.md)** — Narration quality (OpenAI TTS, fallback chain)

### For Developers / Contributing
- **[docs/PLUGIN-DEVELOPMENT-GUIDE.md](docs/PLUGIN-DEVELOPMENT-GUIDE.md)** — How to extend this plugin or build similar ones
- **[docs/README.md](docs/README.md)** — Navigation guide through all documentation

### Historical (not current)
- `docs/ADR-0001-director-mode.md` / `docs/ADR-0002-3tier-animation.md` / `docs/ADR-0003-didactic-storyboard.md` — 3-tier/director-mode architecture (never activated; kept for reference)

## License

Apache License 2.0

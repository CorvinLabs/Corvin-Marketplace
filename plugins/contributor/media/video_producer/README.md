# Video Producer Plugin — Create Narrated Videos with Animated Slides

**What ships live today: turn a task description into a professional narrated MP4 with animated slides in the corvin-labs.com design language.**

> **2026-10-09 — Production Ready.** This version documents the live implementation: LLM-written storyboard, OpenAI TTS narration, deterministic web-slide rendering, and ffmpeg assembly. All components are wired and tested. See [ADR-2238](../../Corvin-Knowledge/decisions/ADR-2238-video-producer-deterministic-web-slide-renderer-html-css.md) (web slides) and [ADR-2211](../../Corvin-Knowledge/decisions/ADR-2211-video-producer-openai-tts-default-and-layout-collision-resolution.md) (narration quality).

## How it works

**Pipeline (all four steps happen automatically):**

1. **Storyboard** → LLM writes scenes + narration text (Anthropic API by default; falls back to local Ollama if API forbidden by L35/L34 gates)
2. **Narration** → OpenAI TTS synthesizes audio for each scene (`tts-1-hd`, voice `onyx`) — clear error message if key missing; fallback chain via `tts_engine: "auto"`
3. **Slides** → Animated web slides in **corvin-labs.com design** with 14 built-in templates (deterministic Chromium rendering, ambient loops, monotone curves, DAG graphs); fallback to Pillow if Chromium unavailable
4. **Assembly** → FFmpeg encodes MP4 at 1920×1080 / 30fps with audio synced to narration

**Result:** a professional 1–3 minute MP4 video ready to share. **No subtitles** (ADR-2211 design decision).

**Status per job:** stored in metadata (which TTS ran, which storyboard model, any rendering fallbacks, template repairs)

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
```

## Configuration & Customization

### Environment (on the host running CorvinOS)

**Required for best quality:**
- `OPENAI_API_KEY` or `CORVIN_TTS_OPENAI_KEY` — OpenAI TTS key for narration (required for `openai` engine, default)

**Optional:**
- `ANTHROPIC_API_KEY` — for Anthropic storyboard generation (if absent, falls back to local Ollama)

### Settings

**In the CorvinOS console** only the narration engine is user-selectable (Settings panel); the panel also reports whether OpenAI and Chromium are available on the host. The other options below are plugin API keys for a host that calls the plugin directly — the console passes none of them, so console jobs always use web slides with the default theme.

| Setting | Default | Options | Purpose |
|---------|---------|---------|---------|
| `tts_engine` | `openai` | `openai` \| `auto` \| `gtts` | Which narrator to use (console + API; see [ADR-2211](../../Corvin-Knowledge/decisions/ADR-2211-video-producer-openai-tts-default-and-layout-collision-resolution.md)) |
| `web_slides` | `true` | boolean | API only: animated web slides (Chromium) vs. classic Pillow slides |
| `web_theme` | `dark` | `dark` \| `light` | API only: colour scheme of the web slides |
| `web_fps` | `30` | integer 12–60 | API only: render frame rate (higher = longer render time) |

### Web Slide Templates

The plugin ships with **14 built-in templates** (hero, content, line chart, donut, flow graph, timeline, cycle, layers, stat, diagram, compare, quote, code) — see [docs/WEB-SLIDES.md](docs/WEB-SLIDES.md) for details. The storyboard LLM automatically picks templates based on the scene content; you don't need to specify them.

## Testing

**Live-path tests** (run these to verify the plugin works):
```bash
cd plugins/contributor/media/video_producer
# needs pytest, pytest-asyncio, playwright (+ `playwright install chromium`) and ffmpeg
python -m pytest tests/test_skill.py tests/test_models.py tests/test_storage.py \
        tests/test_web_charts.py tests/test_web_slides_e2e.py -q
```

Last run (2026-10-09, dev host): 91 passed in 160 s. `tests/test_web_slides_e2e.py` drives the real pipeline (fake `claude` binary, real Chromium, real ffmpeg) and is the end-to-end proof; there is no separate "job end to end" test.

Known red tests, pre-existing and unrelated to the live path: four status-code tests in `tests/test_api_routes.py` and `test_icon_renderer_is_called_from_render_slide_image`.

## Documentation

### For Using This Plugin
- **[docs/WEB-SLIDES.md](docs/WEB-SLIDES.md)** — All 14 slide templates, data contracts, animation details
- **[ADR-2238](../../Corvin-Knowledge/decisions/ADR-2238-video-producer-deterministic-web-slide-renderer-html-css.md)** — Web-slide renderer design (Chromium, deterministic frames, ambient loops)
- **[ADR-2211](../../Corvin-Knowledge/decisions/ADR-2211-video-producer-openai-tts-default-and-layout-collision-resolution.md)** — Narration quality (OpenAI TTS, fallback chain)

### For Developers / Contributing
- **[docs/PLUGIN-DEVELOPMENT-GUIDE.md](docs/PLUGIN-DEVELOPMENT-GUIDE.md)** — How to extend this plugin or build similar ones
- **[docs/README.md](docs/README.md)** — Navigation guide through all documentation

### Historical (not current)
- `docs/ADR-0001` / `ADR-0002` / `ADR-0003` — 3-tier/director-mode architecture (never activated; kept for reference)

## License

Apache License 2.0

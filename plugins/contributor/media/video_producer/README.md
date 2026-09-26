# Video Producer Skill 2.0

**Orchestrated video production: PowerPoint → professional video**

Generate 2-minute CorvinOS demo videos from PowerPoint + console screenshots.

## Features

✨ **No Hallucinations**: Deep-read PPT assets, constrain narration to source  
🔄 **Orchestrated Workers**: 6 specialized workers (Voice, Screenshots, Video, Routing, YouTube)  
🎬 **Professional Quality**: H.264 (CRF 18), AAC audio, auto-subtitles  
🔐 **Audit-First**: SHA256 execution log, tenant isolation, GDPR-compliant  
🚀 **4-Tier Rendering**: Blender CYCLES, Manim, Three.js, SVG  
📺 **YouTube-Ready**: Async API v3 upload  
🧠 **Learning Loop**: Per-scene feedback (ADR-0314)  

## Installation

**System dependencies:**
```bash
brew install ffmpeg node  # macOS
# or apt-get install ffmpeg nodejs npm  # Ubuntu

**Python:**
```bash
pip install openai google-api-python-client google-auth-oauthlib
npm install puppeteer
```

## Quick Start

**CLI Usage:**
```bash
# Health check
python3 -m video_producer health --verbose

# Run full orchestration pipeline
python3 -m video_producer orchestrate \
  --assets "path/to/demo.pptx" \
  --project-dir "/tmp/video_project" \
  --output "result.json"
```

**Python API:**
```python
import asyncio
from video_producer import VideoProducerOrchestrator

async def main():
    orch = VideoProducerOrchestrator(project_dir="/tmp")
    result = await orch.orchestrate(
        asset_paths=["demo.pptx"],
        instructions={"style": "professional"}
    )
    print(f"Status: {result['status']}")
    print(f"Analysis: {result['analysis']}")

asyncio.run(main())
```

## Configuration

- `OPENAI_API_KEY` — OpenAI API key (required)
- `~/.corvin/youtube-credentials.json` — YouTube Service Account

## Blender Headless Rendering

`BlenderHeadlessOrchestrator` (`src/video_producer/blender_orchestrator.py`) renders a
`.blend` scene to a real playable video via a real, non-interactive `blender` subprocess
(no mocks): fps/frame range/resolution are read back from the scene itself, output is
copied to a durable path before the render's temp directory is cleaned up, and every
phase (`blender.render_start`, `blender.bpy_script_generated`, `blender.render_complete`)
is written to the tenant's hash-chained audit trail (GDPR Art. 30).

**CLI:**
```bash
python3 -m video_producer.blender_cli \
  --blend path/to/scene.blend \
  --output /tmp/my_video.mp4
```

**Requires:** a `blender` binary on `PATH`, plus `ffmpeg`/`ffprobe` and `ffmpeg-python`.

Scene-building helpers for authoring new `.blend` fixtures live in
`src/video_producer/blender_scene_kit.py` — importable ONLY from inside a running
Blender process (`blender --background --python <script>`), never from regular Python.

## Testing

```bash
# E2E test: Full orchestration pipeline
python3 tests/test_orchestrator_e2e.py

# All tests
python3 -m pytest tests/ -v

# Blender render E2E (skipped automatically if `blender` isn't on PATH)
python3 -m pytest tests/test_blender_orchestrator_e2e.py tests/test_blender_cli_e2e.py -v
```

## Documentation

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — Full design
- [ADR-0692](docs/ADR-0692-orchestration.md) — Orchestrator design
- [ADR-0693](docs/ADR-0693-asset-analyzer.md) — Asset analyzer
- [ADR-0694](docs/ADR-0694-voice-screenshot.md) — Voice + screenshots
- [ADR-0695](docs/ADR-0695-assembler-youtube.md) — Video assembly + YouTube

## Load-Bearing Constraints

✅ Phase 2 analysis mandatory  
✅ Preconditions hard (sequential)  
✅ Per-scene feedback (learning)  
✅ SHA256 audit trail  
✅ Tenant isolation  
✅ 4-tier fallback  

## License

Apache License 2.0

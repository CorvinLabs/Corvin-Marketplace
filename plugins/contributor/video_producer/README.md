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

```python
from video_producer.maestro import MaestroOrchestrator

orch = MaestroOrchestrator(project_dir="/tmp")
analysis = orch.call_worker("asset_analyzer", {"ppt_file": "demo.pptx", "output_dir": "/tmp"})
storyboard = orch._generate_storyboard(analysis)
video_result = orch.call_worker("voice_openai", {"storyboard": storyboard})
print(f"✅ Video: {video_result['audio_path']}")
```

## Configuration

- `OPENAI_API_KEY` — OpenAI API key (required)
- `~/.corvin/youtube-credentials.json` — YouTube Service Account

## Testing

```bash
pytest tests/test_orchestration_e2e_stub.py -v
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

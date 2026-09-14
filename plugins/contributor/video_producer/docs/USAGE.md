# Usage Guide — Video Producer Skill 2.0

How to use the Video Producer Skill to orchestrate video production from PowerPoint.

## Overview

The Video Producer Skill 2.0 orchestrates 6 specialized workers to produce professional videos from PowerPoint presentations:

1. **Asset Analyzer** — Deep-read PPT, extract facts
2. **Storyboard Generator** — LLM-constrained narration
3. **Voice Synthesizer** — OpenAI TTS
4. **Screenshot Capturer** — Puppeteer automation
5. **Video Assembler** — FFmpeg H.264 encoding
6. **YouTube Uploader** — API v3 async upload

## CLI Usage

### Basic Orchestration

```bash
python3 -m video_producer orchestrate \
  --assets "presentation.pptx" \
  --project-dir "./video_project" \
  --output "result.json"
```

**Arguments:**
- `--assets` (required) — Comma-separated file paths (PPT, images, etc.)
- `--project-dir` (optional, default: ".") — Working directory
- `--instructions` (optional) — JSON string with user guidance
- `--output` (optional, default: "orchestration_result.json") — Result file

**Example with instructions:**
```bash
python3 -m video_producer orchestrate \
  --assets "intro.pptx,screenshots/" \
  --project-dir "/tmp/video_out" \
  --instructions '{"style":"professional","duration_sec":60}' \
  --output "result.json"
```

### Health Check

```bash
python3 -m video_producer health --verbose
```

Output shows which components are available:
```
✅ Orchestrator — core component, always available
✅ Optimizer — learning loop component (optional)
✅ Console Panel — UI component (optional)
```

## Python API

### Async Orchestration

```python
import asyncio
from video_producer import VideoProducerOrchestrator

async def main():
    # Initialize
    orch = VideoProducerOrchestrator(project_dir="/tmp/video")
    
    # Run orchestration
    result = await orch.orchestrate(
        asset_paths=["presentation.pptx"],
        instructions={
            "style": "professional",
            "duration_sec": 60,
            "target_audience": "technical"
        }
    )
    
    # Check result
    if result["status"] == "success":
        print(f"✅ Analysis: {len(result['analysis']['factual_claims'])} facts")
        print(f"✅ Storyboard: {len(result['storyboard']['scenes'])} scenes")
    else:
        print(f"❌ Blocked: {result['analysis']['blockers']}")

asyncio.run(main())
```

### Result Structure

```json
{
  "status": "success" | "blocked",
  "analysis": {
    "metadata": { ... },
    "factual_claims": [ ... ],
    "ready_for_narration": true,
    "blockers": []
  },
  "storyboard": {
    "metadata": { ... },
    "scenes": [
      {
        "id": "s01",
        "kind": "card",
        "narration": "...",
        "source_asset": "presentation.pptx",
        "captions": true
      }
    ]
  }
}
```

## HTTP API (Console)

### POST /v1/console/video-producer/orchestrate

Request:
```bash
curl -X POST http://localhost:8765/v1/console/video-producer/orchestrate \
  -H "Content-Type: application/json" \
  -d '{
    "assets": ["presentation.pptx"],
    "instructions": {
      "style": "professional",
      "duration_sec": 60
    }
  }'
```

Response:
```json
{
  "job_id": "job_abc123",
  "status": "processing"
}
```

### GET /v1/console/video-producer/jobs/{job_id}

```bash
curl http://localhost:8765/v1/console/video-producer/jobs/job_abc123
```

Response:
```json
{
  "job_id": "job_abc123",
  "status": "success",
  "result": { ... }
}
```

## Workflow Examples

### Example 1: Simple PPT → Video

```bash
# 1. Create a simple PPT or use existing
presentation.pptx

# 2. Run orchestration
python3 -m video_producer orchestrate \
  --assets "presentation.pptx" \
  --project-dir "./output" \
  --output "result.json"

# 3. Check result
cat output/result.json | python3 -m json.tool

# 4. (Optional) Use the storyboard for next stage
cat output/storyboard.json
```

### Example 2: Multiple Assets

```bash
# Combine PPT + screenshots
python3 -m video_producer orchestrate \
  --assets "slides.pptx,screenshots/,images/" \
  --project-dir "/tmp/multi_asset_video" \
  --instructions '{"style":"infographic"}'
```

### Example 3: Python Script with Error Handling

```python
import asyncio
import json
from pathlib import Path
from video_producer import VideoProducerOrchestrator
from video_producer.exceptions import AnalysisGateFailedError

async def produce_video(ppt_path: str, output_dir: str):
    try:
        orch = VideoProducerOrchestrator(project_dir=output_dir)
        
        print(f"📹 Processing: {ppt_path}")
        result = await orch.orchestrate(
            asset_paths=[ppt_path],
            instructions={"style": "professional"}
        )
        
        if result["status"] == "success":
            # Save result
            output_file = Path(output_dir) / "result.json"
            with open(output_file, "w") as f:
                json.dump(result, f, indent=2)
            
            print(f"✅ Success: {output_file}")
            return result
        else:
            print(f"⚠️  Analysis blocked:")
            for blocker in result["analysis"]["blockers"]:
                print(f"   • {blocker}")
            return None
    
    except AnalysisGateFailedError as e:
        print(f"❌ Gate failure: {e}")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        raise

# Run
asyncio.run(produce_video("slides.pptx", "/tmp/video_output"))
```

## Configuration

For detailed environment variable setup, see [CONFIGURATION.md](./CONFIGURATION.md).

**Quick setup:**
```bash
export OPENAI_API_KEY="sk-..."
mkdir -p ~/.corvin && cp youtube-creds.json ~/.corvin/
python3 -m video_producer health
```

## Troubleshooting

Common issues and solutions — see [TROUBLESHOOTING.md](./TROUBLESHOOTING.md).

## Next Steps

- **Installation:** [INSTALLATION.md](./INSTALLATION.md)
- **Configuration:** [CONFIGURATION.md](./CONFIGURATION.md)
- **Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md)
- **Issues:** [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)

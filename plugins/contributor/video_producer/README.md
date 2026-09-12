# Video Producer Plugin

**Version:** 1.0.0 | **Tier:** Contributor | **Status:** Active

Create CorvinOS marketing and explainer videos from PowerPoints, screenshots, and voice narration. Orchestrated multi-skill system with deep asset analysis, per-scene feedback, and learning loops.

## Overview

The Video Producer Plugin provides a complete video creation workflow:

1. **Asset Analysis** — Deep-read PowerPoint slides for factual claims and contradictions
2. **Storyboard Generation** — LLM-constrained narrative creation
3. **Voice Narration** — AI voice synthesis with style customization (professional/casual/academic)
4. **Screenshot Capture** — Automated visual documentation
5. **Slide Rendering** — Convert PowerPoints to video frames
6. **Video Assembly** — FFmpeg-based video composition
7. **YouTube Export** — Direct upload to YouTube with metadata

## Features

- **Orchestrated Multi-Skill Architecture:** Maestro skill + 5 specialized worker skills
- **Deep Asset Analysis:** Contradiction detection and factual claim verification (no hallucination)
- **Per-Scene Feedback:** User feedback loops for continuous improvement
- **Learning Optimizer:** Self-tuning parameters based on production outcomes
- **Audit Trail:** Full GDPR-compliant audit logging of all production steps
- **Console Integration:** Native panel in CorvinOS Console under "My Panels"

## Installation

### Option 1: Using pip (Recommended)

```bash
pip install git+https://github.com/CorvinLabs/Corvin-Marketplace.git#subdirectory=plugins/contributor/video_producer
```

### Option 2: Local Development

```bash
cd plugins/contributor/video_producer
pip install -e .
```

### Option 3: Docker

```bash
docker run -v ~/.corvin:/root/.corvin \
  corvinlabs/corvinOS:latest \
  corvin plugin install video-producer
```

## Quick Start

### 1. Access Console Panel

Navigate to CorvinOS Console → "My Panels" → "Video Producer"

### 2. Upload PowerPoint

Click "Upload Presentation" and select your `.pptx` file.

### 3. Configure Narration

- **Style:** Professional (default), Casual, or Academic
- **Max Duration:** Set maximum video length (default: 30 minutes)
- **Enable Learning:** Toggle to use learned parameters (default: on)

### 4. Start Production

Click "Create Video" to begin the production workflow.

### 5. Monitor Progress

- Real-time progress bar
- Phase updates (Analyzing → Narrating → Assembling → Uploading)
- Live event stream via SSE
- Estimated completion time

### 6. Provide Feedback (Optional)

After video generation, provide per-scene feedback for the learning optimizer to improve future videos.

## API Endpoints

All endpoints are available at `/v1/console/video-producer/`:

### POST /orchestrate

Start a new video production job.

**Request:**
```json
{
  "ppt_url": "https://example.com/presentation.pptx",
  "video_title": "My Explainer Video",
  "narration_style": "professional",
  "max_duration_minutes": 30,
  "enable_learning": true
}
```

**Response:**
```json
{
  "job_id": "uuid-xxx",
  "status": "pending",
  "progress_percent": 0,
  "current_phase": "ingestion",
  "created_at": "2026-09-12T10:00:00Z"
}
```

### GET /jobs/{job_id}

Get current status of a production job.

**Response:**
```json
{
  "job_id": "uuid-xxx",
  "status": "analyzing",
  "progress_percent": 25,
  "current_phase": "analyzing",
  "created_at": "2026-09-12T10:00:00Z",
  "updated_at": "2026-09-12T10:05:00Z"
}
```

### GET /jobs/{job_id}/events

Stream job events as Server-Sent Events (SSE).

```javascript
const eventSource = new EventSource('/v1/console/video-producer/jobs/uuid-xxx/events');
eventSource.addEventListener('job_started', (e) => console.log(JSON.parse(e.data)));
eventSource.addEventListener('phase_change', (e) => console.log(JSON.parse(e.data)));
```

### GET /metrics

Get system-wide video production metrics.

**Response:**
```json
{
  "total_videos_created": 12,
  "total_duration_minutes": 360.5,
  "average_processing_time_seconds": 1800,
  "success_rate_percent": 94.0,
  "total_scenes_narrated": 156,
  "learning_optimizer_score": 0.87
}
```

### DELETE /jobs/{job_id}

Cancel an in-progress video production job.

### GET /health

Health check endpoint.

## Configuration

Configure the plugin via `~/.corvin/tenants/_default/plugins/video-producer.yaml`:

```yaml
video_producer:
  # TTS engine selection
  tts_engine: "azure"  # or "gcp", "aws"
  
  # YouTube upload settings
  youtube_oauth_required: true
  youtube_auto_publish: false
  
  # Production limits
  max_video_length_minutes: 60
  max_concurrent_jobs: 3
  
  # Learning optimizer
  enable_learning: true
  learning_convergence_threshold: 0.85
  
  # Storage
  temp_storage_path: "/tmp/video-producer"
  output_storage_path: "s3://my-bucket/videos"
  
  # Logging
  log_level: "info"
  audit_all_operations: true
```

## Permissions

The plugin requires these permissions:

- `console:read` — Read console state
- `console:write` — Write console UI updates
- `skills:execute` — Execute worker skills
- `tasks:manage` — Manage video production tasks
- `learning:write` — Write learning optimizer data
- `audit:read` — Read audit trail

## Troubleshooting

### Video Production Fails at Analysis Phase

**Issue:** Asset analyzer rejects the PowerPoint.

**Solution:**
1. Verify all factual claims in your slides
2. Check for contradictory statements across slides
3. Use `corvin debug video-producer --analyze <file.pptx>` for detailed feedback

### Narration Quality Issues

**Issue:** Synthetic voice sounds unnatural or pauses incorrectly.

**Solution:**
1. Provide per-scene feedback after production (helps the learning optimizer)
2. Try a different `narration_style` (professional/casual/academic)
3. Check TTS engine configuration in settings

### YouTube Upload Fails

**Issue:** OAuth token expired or permissions insufficient.

**Solution:**
1. Re-authenticate: `corvin auth youtube --plugin video-producer`
2. Verify YouTube channel has upload permissions
3. Check channel is not restricted for automated uploads

### Out of Memory During Assembly

**Issue:** Video assembly fails on large files.

**Solution:**
1. Reduce `max_video_length_minutes` (split into multiple videos)
2. Lower video quality (480p instead of 1080p)
3. Increase system memory or use a machine with more RAM

## Learning Optimizer

The plugin includes a self-tuning learning optimizer that:

1. **Tracks Outcomes:** Success/failure, user satisfaction, viewer engagement
2. **Computes Gradients:** Which decisions led to good/bad outcomes?
3. **Updates Parameters:** Narration speed, scene duration, music volume, etc.
4. **Convergence Detection:** Stops optimizing when performance plateaus

**How to Use:**
1. After video production, provide per-scene feedback (1-5 star rating)
2. Learning optimizer automatically processes feedback
3. Next video uses optimized parameters
4. View optimization progress: `corvin learning video-producer --status`

## Advanced Usage

### Batch Production

Process multiple presentations in sequence:

```bash
corvin batch video-producer \
  --input-dir ./presentations/ \
  --output-dir ./videos/ \
  --narration-style professional \
  --concurrent 3
```

### Custom Prompts

Override the default LLM prompts used for narration:

```bash
corvin config video-producer --prompts-file ./custom-prompts.yaml
```

### Webhook Notifications

Receive webhooks when video production completes:

```bash
corvin config video-producer \
  --webhook-url https://example.com/webhooks/video-complete \
  --webhook-events job_complete,job_failed
```

## Development

### Running Tests

```bash
cd plugins/contributor/video_producer
pip install -e ".[dev]"
pytest tests/ -v
```

### Building Documentation

```bash
cd docs/
pip install -r requirements.txt
make html
```

### Contributing

1. Fork Corvin-Marketplace
2. Create feature branch: `git checkout -b feature/my-feature`
3. Write tests + documentation
4. Submit PR (must include ADR if adding new subsystem)

## API Reference

For detailed API documentation, see [API.md](docs/API.md).

## Architecture

For technical architecture details, see [ARCHITECTURE.md](docs/ARCHITECTURE.md).

The plugin is built on ADR-0692 through ADR-0695:

- **ADR-0692:** Video Producer Orchestration (phases 0-7, gates, preconditions)
- **ADR-0693:** Asset Analyzer Worker (deep read, contradiction detection)
- **ADR-0694:** Voice Synthesizer & Screenshot Capturer (parallel execution, feedback)
- **ADR-0695:** Video Assembler & YouTube Uploader (FFmpeg, async upload)

## License

Apache-2.0 (see [LICENSE](LICENSE))

## Support

- **Issues:** https://github.com/CorvinLabs/Corvin-Marketplace/issues
- **Discussions:** https://github.com/CorvinLabs/Corvin-Marketplace/discussions
- **Email:** corvinOS-team@anthropic.com

## Changelog

### v1.0.0 (2026-09-12)

- ✅ Initial release as Contributor plugin
- ✅ Console panel integration ("My Panels")
- ✅ Full multi-skill orchestration (150+ tests)
- ✅ Learning optimizer with feedback loops
- ✅ GDPR-compliant audit trail
- ✅ YouTube integration

# API Reference — Video Producer Plugin

All endpoints are served at `/v1/console/video-producer/` base URL.

## Endpoints

### POST /orchestrate

Start a new video production job.

**Method:** `POST`

**URL:** `/v1/console/video-producer/orchestrate`

**Authentication:** Requires valid CorvinOS session cookie

**Request Body:**

```json
{
  "ppt_url": "https://example.com/presentation.pptx",
  "video_title": "My Explainer Video",
  "narration_style": "professional",
  "max_duration_minutes": 30,
  "enable_learning": true
}
```

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `ppt_url` | string | Yes | — | URL or local file path to PowerPoint (.pptx) |
| `video_title` | string | Yes | — | Output video title |
| `narration_style` | string | No | `professional` | Voice style: `professional`, `casual`, `academic` |
| `max_duration_minutes` | integer | No | 30 | Maximum video length in minutes |
| `enable_learning` | boolean | No | true | Use learned parameters for optimization |

**Response:** `200 OK`

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "pending",
  "progress_percent": 0,
  "current_phase": "ingestion",
  "created_at": "2026-09-12T10:00:00.000Z",
  "message": "Video production job queued"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string (UUID) | Unique identifier for the production job |
| `status` | string | Current status: `pending`, `analyzing`, `narrating`, `assembling`, `uploading`, `complete`, `failed` |
| `progress_percent` | integer | Progress 0-100 |
| `current_phase` | string | Current workflow phase |
| `created_at` | string (ISO-8601) | Job creation timestamp |
| `message` | string | Human-readable status message |

**Error Responses:**

| Status | Error | Description |
|--------|-------|-------------|
| 400 | `invalid_ppt_url` | PowerPoint URL is invalid or unreachable |
| 400 | `invalid_narration_style` | Unsupported narration style |
| 413 | `file_too_large` | PowerPoint exceeds max size (500MB) |
| 503 | `queue_full` | Max concurrent jobs reached, try later |

**Example:**

```bash
curl -X POST http://localhost:8765/v1/console/video-producer/orchestrate \
  -H "Content-Type: application/json" \
  -d '{
    "ppt_url": "https://example.com/presentation.pptx",
    "video_title": "Q3 Product Roadmap",
    "narration_style": "professional",
    "max_duration_minutes": 45
  }'
```

---

### GET /jobs/{job_id}

Get current status and metadata for a video production job.

**Method:** `GET`

**URL:** `/v1/console/video-producer/jobs/{job_id}`

**Authentication:** Requires valid CorvinOS session cookie

**Parameters:**

| Name | Type | Location | Description |
|------|------|----------|-------------|
| `job_id` | string | Path | Job ID returned from `/orchestrate` |

**Response:** `200 OK`

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "analyzing",
  "progress_percent": 25,
  "current_phase": "analyzing",
  "created_at": "2026-09-12T10:00:00.000Z",
  "updated_at": "2026-09-12T10:05:30.000Z",
  "error_message": null,
  "video_url": null,
  "youtube_url": null,
  "metrics": {
    "slides_analyzed": 12,
    "scenes_generated": 24,
    "audio_duration_seconds": 780,
    "estimated_completion_time_seconds": 1200
  }
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string | Job identifier |
| `status` | string | Current status |
| `progress_percent` | integer | 0-100 progress |
| `current_phase` | string | Current workflow phase |
| `created_at` | string (ISO-8601) | Job creation time |
| `updated_at` | string (ISO-8601) | Last update time |
| `error_message` | string or null | Error message if failed, else null |
| `video_url` | string or null | URL to final video MP4 |
| `youtube_url` | string or null | YouTube video URL if uploaded |
| `metrics` | object | Phase-specific metrics |

**Error Responses:**

| Status | Error | Description |
|--------|-------|-------------|
| 404 | `job_not_found` | Job ID does not exist or has expired |
| 410 | `job_expired` | Job deleted after completion (retention expired) |

**Example:**

```bash
curl http://localhost:8765/v1/console/video-producer/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### GET /jobs/{job_id}/events

Stream job events as Server-Sent Events (SSE).

**Method:** `GET`

**URL:** `/v1/console/video-producer/jobs/{job_id}/events`

**Authentication:** Requires valid CorvinOS session cookie

**Response:** `200 OK` (text/event-stream)

```
data: {"type": "job_started", "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "timestamp": "2026-09-12T10:00:00Z"}

data: {"type": "phase_change", "phase": "analyzing", "progress_percent": 10, "timestamp": "2026-09-12T10:01:00Z"}

data: {"type": "scene_generated", "scene_id": "s1", "scene_title": "Introduction", "timestamp": "2026-09-12T10:02:00Z"}

data: {"type": "phase_change", "phase": "narrating", "progress_percent": 50, "timestamp": "2026-09-12T10:10:00Z"}

data: {"type": "job_complete", "video_url": "https://storage.example.com/video.mp4", "timestamp": "2026-09-12T10:30:00Z"}
```

**Event Types:**

| Type | Data | Description |
|------|------|-------------|
| `job_started` | `{job_id}` | Job processing started |
| `phase_change` | `{phase, progress_percent}` | Moved to new workflow phase |
| `scene_generated` | `{scene_id, scene_title, narration_text}` | Scene created |
| `contradiction_detected` | `{scene_id, contradiction_text}` | Contradiction found (requires review) |
| `narration_ready` | `{scene_id, audio_url}` | Voice narration ready for review |
| `screenshot_captured` | `{scene_id, screenshot_url}` | Screenshot captured |
| `video_assembled` | `{video_url}` | Raw video assembled |
| `uploading_youtube` | `{progress_percent}` | Upload in progress |
| `job_complete` | `{video_url, youtube_url}` | Job completed successfully |
| `job_failed` | `{error_message}` | Job failed |

**Example (JavaScript):**

```javascript
const eventSource = new EventSource(
  '/v1/console/video-producer/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/events'
);

eventSource.addEventListener('phase_change', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Progress: ${data.progress_percent}% — Phase: ${data.phase}`);
});

eventSource.addEventListener('contradiction_detected', (e) => {
  const data = JSON.parse(e.data);
  console.warn(`Contradiction in scene ${data.scene_id}: ${data.contradiction_text}`);
  // Operator must review and approve
});

eventSource.addEventListener('job_complete', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Video ready: ${data.video_url}`);
  console.log(`YouTube: ${data.youtube_url}`);
});

eventSource.addEventListener('job_failed', (e) => {
  const data = JSON.parse(e.data);
  console.error(`Job failed: ${data.error_message}`);
  eventSource.close();
});
```

---

### GET /metrics

Get system-wide video production metrics and optimizer status.

**Method:** `GET`

**URL:** `/v1/console/video-producer/metrics`

**Authentication:** Requires valid CorvinOS session cookie

**Response:** `200 OK`

```json
{
  "total_videos_created": 12,
  "total_duration_minutes": 360.5,
  "average_processing_time_seconds": 1800,
  "success_rate_percent": 94.0,
  "total_scenes_narrated": 156,
  "learning_optimizer_score": 0.87,
  "optimizer_convergence_status": "converging",
  "last_optimization_update": "2026-09-12T09:30:00Z",
  "active_jobs": 2,
  "queue_depth": 5
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `total_videos_created` | integer | Lifetime videos produced |
| `total_duration_minutes` | number | Total output video duration |
| `average_processing_time_seconds` | number | Mean time per video |
| `success_rate_percent` | number | Percentage of successful completions |
| `total_scenes_narrated` | integer | Total scenes across all videos |
| `learning_optimizer_score` | number (0-1) | Current optimizer performance |
| `optimizer_convergence_status` | string | `converging`, `converged`, `diverging` |
| `last_optimization_update` | string (ISO-8601) | Last time parameters were updated |
| `active_jobs` | integer | Currently processing jobs |
| `queue_depth` | integer | Jobs waiting in queue |

**Example:**

```bash
curl http://localhost:8765/v1/console/video-producer/metrics
```

---

### DELETE /jobs/{job_id}

Cancel an in-progress video production job.

**Method:** `DELETE`

**URL:** `/v1/console/video-producer/jobs/{job_id}`

**Authentication:** Requires valid CorvinOS session cookie

**Parameters:**

| Name | Type | Location | Description |
|------|------|----------|-------------|
| `job_id` | string | Path | Job ID to cancel |

**Response:** `200 OK`

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "cancelled",
  "cancelled_at": "2026-09-12T10:30:00Z",
  "refund_available": false
}
```

**Error Responses:**

| Status | Error | Description |
|--------|-------|-------------|
| 404 | `job_not_found` | Job does not exist |
| 409 | `job_already_complete` | Cannot cancel completed job |

**Example:**

```bash
curl -X DELETE http://localhost:8765/v1/console/video-producer/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### GET /health

Health check endpoint for the Video Producer plugin.

**Method:** `GET`

**URL:** `/v1/console/video-producer/health`

**Authentication:** None required

**Response:** `200 OK`

```json
{
  "status": "ok",
  "service": "video-producer",
  "version": "1.0.0",
  "uptime_seconds": 86400,
  "ffmpeg_available": true,
  "tts_engine_available": true,
  "storage_available_gb": 50.5
}
```

**Response Statuses:**

| Status | Meaning |
|--------|---------|
| `ok` | All systems operational |
| `degraded` | Some services unavailable (e.g., YouTube upload) |
| `down` | Service not operational |

**Example:**

```bash
curl http://localhost:8765/v1/console/video-producer/health
```

---

## Rate Limiting

- **Default:** 100 requests per minute per user
- **Burst:** Up to 10 concurrent requests
- **Job Queue:** Max 10 concurrent video productions

## Retry Policy

Requests should implement exponential backoff:

```javascript
async function withRetry(fn, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (e) {
      if (i === maxRetries - 1) throw e;
      const delay = Math.pow(2, i) * 1000; // 1s, 2s, 4s
      await new Promise(r => setTimeout(r, delay));
    }
  }
}
```

## Webhooks

Configure webhooks to receive notifications when jobs complete:

```bash
corvin config video-producer \
  --webhook-url https://example.com/webhooks/video-complete \
  --webhook-events job_complete,job_failed,contradiction_detected
```

Webhook payload example:

```json
{
  "type": "job_complete",
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "video_url": "https://storage.example.com/video.mp4",
  "youtube_url": "https://youtube.com/watch?v=abc123",
  "timestamp": "2026-09-12T10:30:00Z"
}
```

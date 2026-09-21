# Workflows Plugin Routes

**All routes prefixed by `/v1/console/workflows`**

---

## Phase 1: Core Workflows (CRUD + YAML + Runs)

### Workflow Management (CRUD)

#### `GET /workflows`
List all workflows for the current tenant.

**Parameters:**
- `count` (optional, int): Results per page (default: 50)
- `offset` (optional, int): Pagination offset (default: 0)

**Response:**
```json
{
  "workflows": [
    {
      "wid": "wf-001",
      "title": "My Workflow",
      "description": "...",
      "status": "ACTIVE",
      "created_at": "2026-09-01T12:00:00Z",
      "updated_at": "2026-09-01T12:00:00Z",
      "node_count": 5,
      "phase": "Phase 1"
    }
  ],
  "count": 10,
  "total": 42
}
```

#### `POST /workflows`
Create a new workflow.

**Request:**
```json
{
  "title": "My Workflow",
  "description": "Optional description"
}
```

**Response:**
```json
{
  "wid": "wf-new",
  "title": "My Workflow",
  "description": "Optional description",
  "status": "DRAFT",
  "created_at": "2026-09-21T12:00:00Z",
  "updated_at": "2026-09-21T12:00:00Z",
  "node_count": 0,
  "phase": "Phase 1"
}
```

**Errors:**
- `400` — Title invalid or too long
- `409` — Workflow ID collision (internal)
- `429` — License limit exceeded (workflows_concurrent)

#### `GET /workflows/{wid}`
Get workflow details with parsed graph.

**Response:**
```json
{
  "wid": "wf-001",
  "title": "My Workflow",
  "description": "...",
  "status": "ACTIVE",
  "created_at": "2026-09-01T12:00:00Z",
  "updated_at": "2026-09-01T12:00:00Z",
  "node_count": 5,
  "phase": "Phase 1",
  "graph": {
    "nodes": [
      {"id": "claude-1", "type": "claude", "name": "Analyze", "prompt": "..."},
      {"id": "deliver-1", "type": "deliver", "name": "Send"}
    ],
    "edges": [
      {"from": "claude-1", "to": "deliver-1"}
    ]
  }
}
```

#### `PATCH /workflows/{wid}`
Update workflow metadata.

**Request:**
```json
{
  "title": "Updated Title",
  "description": "Updated description"
}
```

**Response:** Updated workflow object (same schema as GET)

#### `DELETE /workflows/{wid}`
Delete a workflow and all its runs.

**Response:**
```json
{"deleted": true}
```

---

### YAML Management

#### `GET /workflows/{wid}/yaml`
Get raw YAML source.

**Response:** Raw YAML text (Content-Type: `text/x-yaml`)

#### `PUT /workflows/{wid}/yaml`
Replace workflow YAML and reparse graph.

**Request:** Raw YAML body (Content-Type: `text/x-yaml`)

**Response:** Updated workflow object

**Errors:**
- `400` — YAML parse error or validation failed (returns validation details)

---

### Runs (Execution)

#### `POST /workflows/{wid}/runs`
Start a workflow run. Returns SSE stream.

**Request:**
```json
{
  "skip_approval": false,  // Skip HITL gates
  "context": {}            // User context
}
```

**Response (SSE stream):**
```
event: run.started
data: {"rid": "run-001", "started_at": "..."}

event: run.node.started
data: {"node_id": "claude-1", "started_at": "..."}

event: run.node.output
data: {"node_id": "claude-1", "output": "Result..."}

event: run.node.completed
data: {"node_id": "claude-1", "status": "success"}

event: run.completed
data: {"rid": "run-001", "status": "completed", "completed_at": "..."}
```

**Errors:**
- `404` — Workflow not found
- `409` — Run already active
- `429` — License limit exceeded

#### `GET /workflows/{wid}/runs`
List all runs for a workflow.

**Response:**
```json
{
  "runs": [
    {
      "rid": "run-001",
      "status": "completed",
      "started_at": "2026-09-21T12:00:00Z",
      "completed_at": "2026-09-21T12:05:00Z",
      "node_results": {
        "claude-1": {"status": "success", "output": "..."},
        "deliver-1": {"status": "success"}
      }
    }
  ]
}
```

#### `GET /workflows/{wid}/runs/{rid}`
Get run details.

**Response:**
```json
{
  "rid": "run-001",
  "wid": "wf-001",
  "status": "completed",
  "started_at": "2026-09-21T12:00:00Z",
  "completed_at": "2026-09-21T12:05:00Z",
  "node_results": {...},
  "events": [
    {"timestamp": "...", "type": "node.started", "node_id": "claude-1"},
    {"timestamp": "...", "type": "node.output", "node_id": "claude-1", "output": "..."}
  ]
}
```

#### `DELETE /workflows/{wid}/runs/{rid}`
Delete a run.

**Response:**
```json
{"deleted": true}
```

---

## Phase 4: Scheduling

#### `GET /workflows/{wid}/schedule`
Get current schedule.

**Response:**
```json
{
  "schedule": "0 12 * * *",  // Cron, or null if none
  "scheduled": true,
  "next_run": "2026-09-22T12:00:00Z"
}
```

#### `PUT /workflows/{wid}/schedule`
Set a cron schedule.

**Request:**
```json
{
  "cron": "0 12 * * *"  // Cron expression
}
```

**Response:** Updated schedule object

**Errors:**
- `400` — Invalid cron expression
- `503` — Scheduler unavailable

#### `DELETE /workflows/{wid}/schedule`
Remove the schedule.

**Response:**
```json
{"removed": true}
```

---

## Phase 5: Export/Import

#### `GET /workflows/{wid}/export.awpkg`
Export workflow as AWPKG bundle (ZIP).

**Response:** ZIP file (Content-Type: `application/zip`)

**Errors:**
- `503` — AWPKG export unavailable

#### `POST /workflows/import`
Import a YAML or AWPKG file.

**Request:** Multipart form-data with `file` field (`.yaml` or `.awpkg`)

**Response:**
```json
{
  "wid": "wf-imported",
  "title": "Imported Workflow",
  "imported_at": "2026-09-21T12:00:00Z"
}
```

**Errors:**
- `400` — Invalid file format
- `409` — Workflow ID collision

---

## Phase 7: Design Chat

#### `WS /workflows/{wid}/chat`
WebSocket for guided workflow design.

**Message format (client → server):**
```json
{
  "type": "message",
  "content": "Add a node to parse JSON"
}
```

**Message format (server → client):**
```json
{
  "type": "assistant",
  "content": "I'll add a Claude node...",
  "suggestions": ["nodes_to_add", ...]
}
```

```json
{
  "type": "audio",
  "content_url": "...",  // Audio TTS URL
  "transcript": "Voice response transcript"
}
```

---

## Error Handling

All error responses use standard HTTP status codes + JSON body:

```json
{
  "error": "workflow_not_found",
  "message": "Workflow wf-unknown not found",
  "details": {
    "wid": "wf-unknown"
  }
}
```

**Common Errors:**
- `400 Bad Request` — Validation failed
- `401 Unauthorized` — Session invalid
- `403 Forbidden` — Permission denied
- `404 Not Found` — Resource not found
- `409 Conflict` — State conflict (workflow exists, run active, etc.)
- `429 Too Many Requests` — Rate limit or license limit exceeded
- `503 Service Unavailable` — Optional dependency missing

---

## Audit Events

Every mutation route logs an audit event:

| Route | Event Type | Payload |
|-------|------------|---------|
| POST /workflows | workflow.created | wid, title, description |
| PATCH /workflows/{wid} | workflow.updated | wid, title, description |
| DELETE /workflows/{wid} | workflow.deleted | wid |
| PUT /workflows/{wid}/yaml | workflow.yaml.updated | wid, node_count, validation_errors (if any) |
| POST /workflows/{wid}/runs | workflow.run.started | wid, rid, started_at |
| (SSE) run.completed | workflow.run.completed | rid, status, node_results_summary |
| DELETE /workflows/{wid}/runs/{rid} | workflow.run.deleted | wid, rid |
| PUT /workflows/{wid}/schedule | workflow.schedule.set | wid, cron, next_run |
| DELETE /workflows/{wid}/schedule | workflow.schedule.removed | wid |

All events include `tenant_id`, `timestamp`, `user_id` (from session).

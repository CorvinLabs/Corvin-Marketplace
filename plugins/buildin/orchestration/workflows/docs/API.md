# Workflows Plugin API Reference

**Version:** 1.0.0  
**Base URL:** `/v1/console/workflows`  
**Authentication:** Session + CSRF token  
**Content-Type:** application/json (except YAML routes)

---

## Overview

The Workflows Plugin provides RESTful API + WebSocket for workflow management.

**Quick Start:**
```bash
# List workflows
curl -b cookies.txt http://localhost:8765/v1/console/workflows

# Create workflow
curl -b cookies.txt -H "X-CSRF-Token: <token>" -X POST \
  -d '{"title":"My WF"}' \
  http://localhost:8765/v1/console/workflows

# Start run (SSE stream)
curl -b cookies.txt -X POST \
  http://localhost:8765/v1/console/workflows/wf-001/runs
```

---

## Request/Response Models

### Workflow Object

```typescript
interface Workflow {
  wid: string;                    // ID: [a-z][a-z0-9_-]{0,63}
  title: string;                  // Max 256 chars
  description?: string;           // Max 1024 chars
  status: "DRAFT" | "ACTIVE" | "PAUSED";
  created_at: ISO8601DateTime;
  updated_at: ISO8601DateTime;
  node_count: number;             // Nodes in graph
  phase: "Phase 1" | "Phase 2" | ... | "Phase 7";
  graph?: WorkflowGraph;          // Optional (GET only)
}

interface WorkflowGraph {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

interface WorkflowNode {
  id: string;
  type: "claude" | "delegation" | "fan-out" | "deliver" | "condition" | "loop";
  name: string;
  config: Record<string, any>;
}

interface WorkflowEdge {
  from: string;
  to: string;
  label?: string;
}
```

### Run Object

```typescript
interface WorkflowRun {
  rid: string;                    // ID: 8-byte hex
  wid: string;
  status: "RUNNING" | "COMPLETED" | "FAILED" | "PAUSED" | "CANCELLED";
  started_at: ISO8601DateTime;
  completed_at?: ISO8601DateTime;
  node_results: {
    [node_id: string]: NodeResult;
  };
  events?: RunEvent[];            // GET only
  error?: string;                 // If failed
}

interface NodeResult {
  status: "success" | "error" | "paused";
  output?: any;
  error?: string;
  duration_ms: number;
  timestamp: ISO8601DateTime;
}

interface RunEvent {
  timestamp: ISO8601DateTime;
  type: "run.started" | "node.started" | "node.output" | "node.completed" | "run.completed";
  data: Record<string, any>;
}
```

---

## Endpoints

### CRUD (Phases 1)

**POST /workflows**
```bash
curl -X POST -H "X-CSRF-Token: $CSRF" \
  -d '{"title":"My WF","description":"..."}' \
  http://localhost:8765/v1/console/workflows

# Response 201
{
  "wid": "wf-abc123",
  "title": "My WF",
  "description": "...",
  "status": "DRAFT",
  "created_at": "2026-09-21T12:00:00Z",
  "updated_at": "2026-09-21T12:00:00Z",
  "node_count": 0,
  "phase": "Phase 1"
}
```

**GET /workflows**
```bash
curl http://localhost:8765/v1/console/workflows?count=10&offset=0

# Response 200
{
  "workflows": [{ ... }],
  "count": 10,
  "total": 42
}
```

**GET /workflows/{wid}**
```bash
curl http://localhost:8765/v1/console/workflows/wf-abc123

# Response 200
{
  "wid": "wf-abc123",
  "title": "My WF",
  ...,
  "graph": {
    "nodes": [{ "id": "claude-1", "type": "claude", ... }],
    "edges": []
  }
}
```

**PATCH /workflows/{wid}**
```bash
curl -X PATCH -H "X-CSRF-Token: $CSRF" \
  -d '{"title":"Updated"}' \
  http://localhost:8765/v1/console/workflows/wf-abc123

# Response 200
{ ... updated workflow ... }
```

**DELETE /workflows/{wid}**
```bash
curl -X DELETE -H "X-CSRF-Token: $CSRF" \
  http://localhost:8765/v1/console/workflows/wf-abc123

# Response 200
{ "deleted": true }
```

---

### YAML (Phase 1)

**GET /workflows/{wid}/yaml**
```bash
curl http://localhost:8765/v1/console/workflows/wf-abc123/yaml

# Response 200 (text/x-yaml)
nodes:
  - id: claude-1
    type: claude
    prompt: "Hello"
edges:
  - from: claude-1
    to: deliver-1
```

**PUT /workflows/{wid}/yaml**
```bash
curl -X PUT -H "X-CSRF-Token: $CSRF" \
  --data-binary @workflow.yaml \
  http://localhost:8765/v1/console/workflows/wf-abc123/yaml

# Response 200
{ ... updated workflow with reparsed graph ... }

# Response 400 (validation error)
{
  "error": "validation_failed",
  "message": "YAML parse error",
  "details": {
    "line": 5,
    "error": "Node 'claude-2' not found in edges"
  }
}
```

---

### Runs (Phase 1)

**POST /workflows/{wid}/runs** (SSE Stream)
```bash
curl -X POST http://localhost:8765/v1/console/workflows/wf-abc123/runs

# Response 200 (text/event-stream)
event: run.started
data: {"rid":"run-xyz","started_at":"2026-09-21T12:00:00Z"}

event: run.node.started
data: {"node_id":"claude-1","started_at":"..."}

event: run.node.output
data: {"node_id":"claude-1","output":"Result text"}

event: run.node.completed
data: {"node_id":"claude-1","status":"success"}

event: run.completed
data: {"rid":"run-xyz","status":"completed","completed_at":"..."}
```

**GET /workflows/{wid}/runs**
```bash
curl http://localhost:8765/v1/console/workflows/wf-abc123/runs

# Response 200
{
  "runs": [
    {
      "rid": "run-xyz",
      "wid": "wf-abc123",
      "status": "completed",
      "started_at": "2026-09-21T12:00:00Z",
      "completed_at": "2026-09-21T12:05:00Z",
      "node_results": {
        "claude-1": { "status": "success", "output": "..." }
      }
    }
  ]
}
```

**GET /workflows/{wid}/runs/{rid}**
```bash
curl http://localhost:8765/v1/console/workflows/wf-abc123/runs/run-xyz

# Response 200
{
  "rid": "run-xyz",
  "wid": "wf-abc123",
  "status": "completed",
  "started_at": "2026-09-21T12:00:00Z",
  "completed_at": "2026-09-21T12:05:00Z",
  "node_results": { ... },
  "events": [
    { "timestamp": "...", "type": "run.started", "data": { ... } },
    { "timestamp": "...", "type": "node.started", "data": { ... } },
    ...
  ]
}
```

**DELETE /workflows/{wid}/runs/{rid}**
```bash
curl -X DELETE -H "X-CSRF-Token: $CSRF" \
  http://localhost:8765/v1/console/workflows/wf-abc123/runs/run-xyz

# Response 200
{ "deleted": true }
```

---

### Scheduling (Phase 4)

**GET /workflows/{wid}/schedule**
```bash
curl http://localhost:8765/v1/console/workflows/wf-abc123/schedule

# Response 200
{
  "schedule": "0 12 * * *",
  "scheduled": true,
  "next_run": "2026-09-22T12:00:00Z"
}

# Response 200 (if no schedule)
{
  "schedule": null,
  "scheduled": false
}
```

**PUT /workflows/{wid}/schedule**
```bash
curl -X PUT -H "X-CSRF-Token: $CSRF" \
  -d '{"cron":"0 12 * * *"}' \
  http://localhost:8765/v1/console/workflows/wf-abc123/schedule

# Response 200
{ "schedule": "0 12 * * *", "scheduled": true, ... }
```

**DELETE /workflows/{wid}/schedule**
```bash
curl -X DELETE -H "X-CSRF-Token: $CSRF" \
  http://localhost:8765/v1/console/workflows/wf-abc123/schedule

# Response 200
{ "removed": true }
```

---

### Export/Import (Phase 5)

**GET /workflows/{wid}/export.awpkg**
```bash
curl http://localhost:8765/v1/console/workflows/wf-abc123/export.awpkg \
  -o workflow.awpkg

# Response 200 (application/zip)
# File contains: manifest.json + workflow.yaml + assets/
```

**POST /workflows/import**
```bash
curl -X POST -H "X-CSRF-Token: $CSRF" \
  -F "file=@workflow.awpkg" \
  http://localhost:8765/v1/console/workflows/import

# Response 201
{
  "wid": "wf-imported",
  "title": "Imported Workflow",
  "imported_at": "2026-09-21T12:00:00Z"
}
```

---

### Chat (Phase 7)

**WS /workflows/{wid}/chat**
```javascript
// Connect
const ws = new WebSocket('ws://localhost:8765/v1/console/workflows/wf-abc123/chat');

// Send message
ws.send(JSON.stringify({
  type: "message",
  content: "Add a node to parse JSON"
}));

// Receive response
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  // msg.type: "assistant", "audio", "error"
  // msg.content: Response text
};
```

---

## Error Responses

All errors follow this schema:

```json
{
  "error": "error_code",
  "message": "Human-readable message",
  "details": {
    "field": "value"
  }
}
```

**Common Errors:**

| Code | HTTP | Meaning |
|------|------|---------|
| `workflow_not_found` | 404 | Workflow wid not found |
| `validation_failed` | 400 | YAML/request validation failed |
| `yaml_parse_error` | 400 | YAML syntax error |
| `run_active` | 409 | Workflow run already active |
| `license_limit_exceeded` | 429 | License limit (workflows_concurrent) |
| `scheduler_unavailable` | 503 | Scheduler not available (Phase 4) |
| `export_unavailable` | 503 | AWPKG export not available (Phase 5) |
| `unauthorized` | 401 | Session invalid or expired |
| `csrf_token_invalid` | 403 | CSRF token mismatch |
| `method_not_allowed` | 405 | HTTP method not supported |

---

## Rate Limiting

- **Default:** 100 requests/minute per session
- **Workflows created:** 10/hour per tenant
- **Runs started:** 50/hour per workflow

---

## Audit Trail

Every mutation generates an audit event:

```
event_type: "workflow.created"
payload: {
  tenant_id: "...",
  user_id: "...",
  wid: "...",
  title: "...",
  description: "..."
}
```

Query audit trail via `corvin audit show-workflow <wid>`.

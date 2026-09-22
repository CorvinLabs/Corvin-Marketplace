# Workflows Plugin — Automate Your Business Processes

**Transform manual processes into intelligent, self-healing workflows.**

Workflows Plugin turns CorvinOS into a workflow automation engine. Define complex business processes once, execute them reliably across your entire platform. From data pipelines to customer outreach, automate the work that matters.

---

## 🎯 What It Does

The Workflows Plugin enables you to:

- **Design workflows visually** using Claude-powered chat interface — describe your process in natural language, get YAML
- **Schedule automated execution** with cron expressions and timezone support — run workflows reliably on schedule
- **Export/import workflows** as portable AWPKG files — share workflows with your team or the community
- **Monitor executions** with real-time status tracking and detailed logs — see every step, every decision, every error
- **Integrate with any tool** via CorvinOS Skill system — connect to APIs, databases, email, Slack, and more

Perfect for: data pipelines, customer outreach, content moderation, lead scoring, quality assurance, report generation, scheduled maintenance.

---

## ✨ Key Features

### 1. **AI-Powered Workflow Designer**

Chat with Claude to design workflows. Describe your process in natural language:

*"Create a workflow that fetches daily news, summarizes each article, formats an HTML digest, sends it to a Slack channel if there are 5+ articles"*

Claude responds with:
- Suggested YAML workflow (ready to execute)
- Step-by-step explanation of the flow
- Suggestions for improvements
- Clarification questions

The designer validates every workflow YAML before saving, catching syntax errors and logical inconsistencies upfront.

**Benefits:**
- Non-technical users can design workflows (no YAML knowledge required)
- Rapid iteration (chat-based refinement)
- Best practices baked in (Claude suggests optimal node types, error handling, parallelization)

### 2. **Scheduler (Cron + Timezone)**

Run workflows on schedule. Supports:

- **Cron expressions:** POSIX format (`0 9 * * 1-5` = Mon–Fri 9 AM, `0 2 * * *` = daily at 2 AM)
- **Named timezones:** IANA database (`America/New_York`, `Europe/London`, `Asia/Tokyo`, etc.)
- **Overrun policies:** SKIP (skip if previous run still active), PARALLEL (allow concurrent runs), WAIT (enqueue, run sequentially)
- **One-off execution:** Manually trigger a workflow run at any time

Every scheduled run is logged with full audit trail (start time, completion time, status, errors, outcomes).

**Use cases:**
- Daily reports (9 AM every weekday)
- Hourly data syncs (0 * * * * = every hour)
- Monthly cleanup (first Sunday of month: `0 0 ? * 1#1`)
- Quarterly reviews (scheduled manually or via cron)

### 3. **Export/Import (AWPKG)**

Export workflows as portable ZIP packages (AWPKG = Automation Workflow Package):

**Contents of an AWPKG:**
- `workflow.yaml` — Complete workflow definition (nodes, edges, config)
- `manifest.json` — Metadata (name, version, author, description, dependencies)
- `tools.json` — Custom tools/skills referenced by the workflow
- `README.md` — Documentation (optional, included if present)
- `checksums.sha256` — Integrity verification

**Benefits:**
- **Share workflows:** Export → email → teammate imports → runs immediately
- **Version control:** Treat AWPKG as a portable unit (git, S3, Marketplace)
- **Backup/restore:** Export entire workflow library, restore after disaster
- **Integrity:** Checksums verify no tampering during transmission
- **Size limit:** 10 MB (enforced) prevents bloated packages

**Typical workflow:**
```bash
# Export
curl -X GET http://localhost:8765/workflows/daily-digest/export.awpkg \
  -o daily-digest.awpkg

# Import (new environment)
curl -X POST http://localhost:8765/workflows/import \
  -F "file=@daily-digest.awpkg"
# Response: {"workflow_id": "imported-daily-digest", "status": "imported"}
```

### 4. **Real-time Monitoring Dashboard**

Monitor workflow executions with a live dashboard showing:

- **Workflow list:** All defined workflows, status (active/paused/scheduled), last run, next scheduled run
- **Run history:** Last 30 runs (sortable by status, date, duration)
- **Run details:** Click any run to see:
  - Timeline (each node's start/end time)
  - Logs per node (stdout, stderr, errors)
  - Input/output data (trimmed to 1 KB for display)
  - Status (running, completed, failed, paused)
  - Duration (total + per-node breakdown)

**Control actions:**
- **Start:** Trigger workflow immediately
- **Pause:** Pause a running workflow (can be resumed)
- **Resume:** Resume a paused run from where it stopped
- **Stop:** Forcefully terminate a run (cleanup runs)
- **Re-run:** Restart a failed run with same inputs

**Approval gates:** Pause at human-decision points; operator approves via dashboard; workflow resumes automatically.

### 5. **Enterprise-Grade Compliance**

Workflows Plugin is GDPR-compliant and follows EU AI Act 2026:

- **Audit trail:** Every action logged (hash-chained, immutable)
  - workflow.created, workflow.updated, workflow.deleted
  - workflow.executed, workflow.node_completed, workflow.node_failed
  - workflow.export.completed, workflow.import.completed
  - All events tied to operator + timestamp + tenant_id

- **Tenant isolation:** Per-tenant workflow storage, no cross-tenant leakage

- **Data export:** API endpoint `GET /workflows/export` returns all user workflows in AWPKG format

- **Data deletion:** `DELETE /workflows/{wid}` removes workflow + all historical runs (audit trail retained)

- **Prompt guard integration:** Every Claude invocation validated (fail-closed)
  - Input validation: no injection patterns
  - Output validation: safe node definitions
  - Fallback: NoOp if guard unavailable

- **Consent tracking:** Workflows honor user consent gates (L16); refuse to execute if user revoked consent

---

## 🏗️ How It Works

### Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                    Workflows Plugin (v2.0)                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Frontend Layer (React)                                          │
│  ├─ Workflow CRUD UI       (Create, read, update, delete)        │
│  ├─ Design Chat            (WebSocket, real-time)                │
│  └─ Run Monitor Dashboard  (Live status, logs, controls)         │
│                                    ↓                               │
│  API Layer (FastAPI)                                             │
│  ├─ CRUD: /workflows/*                                           │
│  ├─ Scheduler: /workflows/{wid}/schedule                         │
│  ├─ Export/Import: /workflows/{wid}/export.awpkg                 │
│  ├─ Execution: /workflows/{wid}/runs/*                           │
│  └─ Chat: WS /workflows/{wid}/chat                               │
│                                    ↓                               │
│  Core Engine (Python)                                            │
│  ├─ Parser          (YAML → DAG validation)                      │
│  ├─ Executor        (Topological sort, node dispatch)            │
│  ├─ Scheduler       (Cron adapter, timezone support)             │
│  └─ Storage         (File-based, per-tenant)                     │
│                                    ↓                               │
│  CorvinOS Integration                                            │
│  ├─ Skill invocation    (Claude, tools, custom skills)           │
│  ├─ Audit backend       (Hash-chained, immutable)                │
│  ├─ Prompt guard        (Safety validation, fail-closed)         │
│  └─ Session management  (Auth, tenant isolation, consent)        │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘
```

### Typical Workflow Execution

**Scenario:** Daily News Digest

```
1. DESIGNER (User Interface)
   └─ Chat: "Create a daily digest workflow"
              (natural language → Claude → YAML)
   
2. STORAGE
   └─ workflow.yaml saved + audit logged
              (workflow_id = "daily-digest-v1")
   
3. SCHEDULING (Cron Registration)
   └─ Registered: 0 9 * * * (daily at 9 AM UTC)
              (Next run: tomorrow at 09:00:00Z)
   
4. EXECUTION (Next day, 09:00 UTC)
   ├─ Node 1: Fetch News API
   │   ├─ HTTP GET → news.api.com/tech (timeout 30s)
   │   └─ Output: 300 KB JSON (10 articles)
   │
   ├─ Node 2: Summarize (Claude)
   │   ├─ Invoke Claude Opus (batch mode)
   │   └─ Output: 3–5 line summary per article
   │
   ├─ Node 3: Format Email
   │   ├─ HTML template → beautiful digest
   │   └─ Output: 150 KB HTML
   │
   ├─ Node 4: Approval Gate (Human Decision)
   │   ├─ Dashboard shows formatted digest
   │   ├─ Operator clicks "Approve"
   │   └─ Workflow resumes (timeout 60 min)
   │
   └─ Node 5: Send Email
       ├─ Slack API → post to #daily-digest channel
       └─ Output: message_id, timestamp
   
5. MONITORING & AUDIT
   ├─ Dashboard shows: "Completed in 4.2 seconds"
   ├─ Audit trail records every step (immutable)
   └─ Run stored for history/replay
```

### Node Types (20+ Supported)

| Node Type | Purpose | Example |
|-----------|---------|---------|
| **http** | HTTP request (GET, POST, PUT, DELETE) | Fetch from API, webhook |
| **claude** | Invoke Claude (any model, streaming) | Summarization, classification, generation |
| **skill** | Invoke CorvinOS Skill (custom automation) | Email, Slack, database write |
| **python** | Execute Python code (sandboxed) | Data transformation, custom logic |
| **database** | SQL query (any database) | Fetch data, INSERT/UPDATE |
| **approval_gate** | Human decision point | Wait for operator approval |
| **parallel** | Run multiple nodes simultaneously | Parallel processing, fan-out |
| **conditional** | Branch based on data (if/else) | Route based on result |
| **loop** | Iterate over array (for-each) | Process 100 items in sequence |
| **email** | Send email (SMTP) | Notifications, reports |
| **slack** | Post to Slack channel | Alerts, summaries |
| **s3** | Upload/download S3 object | Data staging, backups |
| **webhook** | Call external webhook | Trigger external systems |
| **delay** | Wait N seconds/minutes | Throttle, schedule gaps |
| **assert** | Validate output (fail if false) | Quality gate, sanity check |
| **transform** | JSON transform (jq-like) | Data shape conversion |
| **merge** | Combine multiple inputs | Aggregate results |
| **log** | Emit structured log | Observability |

---

## 🚀 Quick Start

### 1. Create a Workflow via Chat

Open the Workflows console panel (if not visible, enable via Settings → Plugins → Workflows).

**Design chat example:**
```
You: "Create a workflow that fetches trending GitHub repositories every 6 hours, 
     extracts the top 10, and posts them to Slack"

Claude: "I'll create a workflow with 3 nodes: fetch (GitHub API), select (top 10), 
        and post (Slack). Here's the YAML..."

[YAML workflow shown]

You: "Can you add a summary step? And make it hourly instead of 6 hours?"

Claude: [Updated YAML with 4 nodes, 1-hour cron]
```

### 2. Schedule Execution

**Via API:**
```bash
curl -X PUT http://localhost:8765/v1/workflows/trending-repos/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "cron_schedule": "0 * * * *",
    "timezone": "America/New_York",
    "overrun_policy": "skip"
  }'

# Response:
# {
#   "status": "scheduled",
#   "cron_schedule": "0 * * * *",
#   "timezone": "America/New_York",
#   "next_run": "2026-09-24T04:00:00-04:00"
# }
```

**Via Dashboard:**
- Navigate to Workflows → Select workflow
- Click "Schedule"
- Enter cron expression (or select from templates)
- Select timezone
- Choose overrun policy
- Click "Save"

### 3. Monitor Executions

**Via Dashboard:**
- Workflows panel shows live status
- Click any run to see detailed logs
- Use "Start", "Pause", "Resume", "Stop" buttons

**Via API:**
```bash
curl -X GET http://localhost:8765/v1/workflows/trending-repos/runs

# Response: List of 30 recent runs with status, start time, duration
```

### 4. Export Workflow

```bash
# Export to ZIP
curl -X GET http://localhost:8765/v1/workflows/trending-repos/export.awpkg \
  -o trending-repos.awpkg

# Share with team (email, Slack, S3, git commit, etc.)
```

### 5. Import Workflow

**Via Dashboard:**
- Click "Import Workflow"
- Select .awpkg file
- Review metadata
- Click "Import"

**Via API:**
```bash
curl -X POST http://localhost:8765/v1/workflows/import \
  -F "file=@trending-repos.awpkg"

# Response:
# {
#   "workflow_id": "imported-trending-repos",
#   "name": "Trending Repos",
#   "status": "imported",
#   "node_count": 4
# }
```

---

## 🔒 Security & Compliance

### Audit Trail (GDPR Art. 30, 32)

Every action is logged in the immutable audit chain:

```json
{
  "event_type": "workflow_created",
  "workflow_id": "daily-digest-v1",
  "operator": "user@example.com",
  "timestamp": "2026-09-23T14:30:00.000Z",
  "tenant_id": "_default",
  "hash": "sha256(...)",
  "prev_hash": "sha256(...)"
}
```

Events tracked:
- `workflow_created`, `workflow_updated`, `workflow_deleted`
- `workflow_executed`, `workflow_node_completed`, `workflow_node_failed`
- `workflow_paused`, `workflow_resumed`, `workflow_stopped`
- `workflow_exported`, `workflow_imported`
- All events hash-chained for integrity

### Tenant Isolation (GDPR Art. 5, 6)

- Per-tenant workflows directory: `~/.corvin/tenants/<tenant_id>/workflows/`
- Audit queries filtered by `tenant_id`
- No cross-tenant data leakage (verified by tests)

### Prompt Guard (Fail-Closed)

Every Claude invocation validated:
- **Input:** Check for injection patterns, rate-limit abuse
- **Output:** Validate node definitions (syntax, allowed types)
- **Fallback:** If guard unavailable, workflow pauses (fails safely)

### Consent & GDPR Compliance

- **User consent:** Workflows honor user consent gate (L16)
- **Data export:** `GET /workflows/export` → ZIP of all workflows
- **Data deletion:** `DELETE /workflows/{wid}` removes workflow + runs
- **Audit retention:** Audit trail retained independently (compliance requirement)

---

## 📊 Specifications & Limits

| Metric | Value | Notes |
|--------|-------|-------|
| **Max workflows per tenant** | Unlimited | No hard limit; quotas per tier |
| **Max workflow size (YAML)** | 256 KB | Prevents bloated definitions |
| **Max AWPKG size** | 10 MB | Prevents large package uploads |
| **Supported node types** | 20+ | Extensible via Skill system |
| **Max parallel nodes** | 100 | Concurrent execution limit |
| **Node timeout** | 300 s (configurable) | Default 5 minutes per node |
| **Cron format** | POSIX (croniter) | Full POSIX support, no wildcards |
| **Timezones** | IANA (pytz) | All IANA zones supported |
| **Max concurrent runs** | Unlimited per workflow | Subject to tenant quota |
| **Execution latency (P50)** | 50 ms | Node dispatch overhead |
| **Execution latency (P99)** | 200 ms | 99th percentile observed |
| **Audit retention** | 90 days default | Configurable per tenant |
| **Max run history** | Last 1,000 runs | Older runs archived |

---

## 📚 API Reference

### Workflow CRUD

#### List Workflows
```
GET /v1/workflows
```

Response:
```json
{
  "workflows": [
    {
      "workflow_id": "daily-digest-v1",
      "name": "Daily News Digest",
      "description": "Fetch tech news, summarize, send email",
      "created_at": "2026-09-23T10:00:00Z",
      "updated_at": "2026-09-23T14:30:00Z",
      "node_count": 5,
      "status": "active"
    }
  ]
}
```

#### Create Workflow
```
POST /v1/workflows
Content-Type: application/json

{
  "name": "Daily News Digest",
  "description": "Fetch tech news, summarize, send email",
  "yaml": "name: Daily News Digest\nnodes:\n  ..."
}
```

Response: `201 Created` + workflow object with `workflow_id`.

#### Get Workflow
```
GET /v1/workflows/{workflow_id}
```

Returns complete workflow definition + metadata.

#### Update Workflow
```
PATCH /v1/workflows/{workflow_id}
Content-Type: application/json

{
  "name": "Updated Name",
  "description": "Updated description",
  "yaml": "..."
}
```

#### Delete Workflow
```
DELETE /v1/workflows/{workflow_id}
```

Response: `204 No Content` (workflow + runs archived, audit retained).

### Scheduling

#### Get Schedule
```
GET /v1/workflows/{workflow_id}/schedule
```

Response:
```json
{
  "scheduled": true,
  "cron_schedule": "0 9 * * 1-5",
  "timezone": "America/New_York",
  "overrun_policy": "skip",
  "next_run": "2026-09-25T13:00:00-04:00"
}
```

#### Set/Update Schedule
```
PUT /v1/workflows/{workflow_id}/schedule
Content-Type: application/json

{
  "cron_schedule": "0 9 * * 1-5",
  "timezone": "America/New_York",
  "overrun_policy": "skip"
}
```

#### Remove Schedule
```
DELETE /v1/workflows/{workflow_id}/schedule
```

### Export/Import

#### Export Workflow
```
GET /v1/workflows/{workflow_id}/export.awpkg
```

Response: `Content-Type: application/zip` (AWPKG file).

#### Import Workflow
```
POST /v1/workflows/import
Content-Type: multipart/form-data

file=<awpkg_file>
```

Response:
```json
{
  "workflow_id": "imported-workflow-id",
  "name": "Imported Workflow",
  "status": "imported"
}
```

### Execution

#### Start Run
```
POST /v1/workflows/{workflow_id}/runs
```

Response: `201 Created` with `run_id`.

#### List Runs
```
GET /v1/workflows/{workflow_id}/runs?limit=30&offset=0
```

Response: List of recent runs (paginated).

#### Get Run Details
```
GET /v1/workflows/{workflow_id}/runs/{run_id}
```

Response:
```json
{
  "run_id": "run-12345",
  "workflow_id": "daily-digest-v1",
  "status": "completed",
  "start_time": "2026-09-24T09:00:00Z",
  "end_time": "2026-09-24T09:00:04Z",
  "duration_ms": 4200,
  "nodes": [
    {
      "node_id": "fetch_news",
      "status": "completed",
      "start_time": "2026-09-24T09:00:00Z",
      "end_time": "2026-09-24T09:00:01Z",
      "output_size_kb": 300
    }
  ],
  "result": "success"
}
```

#### Approve Gate
```
POST /v1/workflows/{workflow_id}/runs/{run_id}/approve
```

Resumes workflow from approval gate.

#### Pause Run
```
POST /v1/workflows/{workflow_id}/runs/{run_id}/pause
```

#### Resume Run
```
POST /v1/workflows/{workflow_id}/runs/{run_id}/resume
```

#### Stop Run
```
POST /v1/workflows/{workflow_id}/runs/{run_id}/stop
```

### Design Chat

#### Connect to Chat
```
WS /v1/workflows/{workflow_id}/chat
```

Send/receive JSON messages:
```json
{
  "type": "message",
  "content": "Create a workflow that fetches data from Postgres...",
  "role": "user"
}

// Response:
{
  "type": "message",
  "content": "I'll create a workflow with 3 nodes...",
  "role": "assistant",
  "yaml": "name: My Workflow\n..."
}
```

---

## 🛠️ Examples

### Example 1: Daily News Digest

**Workflow YAML:**
```yaml
name: Daily News Digest
description: Fetch tech news, summarize, send email digest

nodes:
  - id: fetch_news
    type: http
    config:
      method: GET
      url: "https://api.hacker-news.com/v0/topstories.json"
      params:
        limit: 20

  - id: fetch_articles
    type: http
    config:
      method: GET
      url: "https://api.hacker-news.com/v0/item/{{ fetch_news.response[0] }}.json"
      loop: true
      for_each: fetch_news.response

  - id: summarize
    type: claude
    config:
      model: claude-opus-5
      prompt: |
        Summarize this article in 2-3 sentences:
        Title: {{ fetch_articles.response.title }}
        URL: {{ fetch_articles.response.url }}
        Points: {{ fetch_articles.response.score }}

  - id: format_digest
    type: skill
    config:
      skill: email_formatter
      inputs:
        articles: "{{ summarize.outputs }}"
        subject: "Daily Tech News Digest"

  - id: approval
    type: approval_gate
    config:
      timeout_minutes: 60
      message: "Review and approve the digest"

  - id: send_email
    type: email
    config:
      to: "team@example.com"
      subject: "{{ format_digest.subject }}"
      html: "{{ format_digest.html }}"

edges:
  - from: fetch_news
    to: fetch_articles
  - from: fetch_articles
    to: summarize
  - from: summarize
    to: format_digest
  - from: format_digest
    to: approval
  - from: approval
    to: send_email
```

**Schedule:** `0 9 * * 1-5` (Mon–Fri at 9 AM UTC)

### Example 2: Content Moderation Pipeline

```yaml
name: Content Moderation
description: Review submitted content and route for approval

nodes:
  - id: fetch_submissions
    type: database
    config:
      query: |
        SELECT id, content, user_id FROM submissions 
        WHERE reviewed = false 
        LIMIT 100

  - id: classify
    type: claude
    config:
      model: claude-opus-5
      prompt: |
        Classify this user-submitted content:
        {{ fetch_submissions.response[0].content }}
        
        Categories: safe, warning, violation
        Respond: {"classification": "...", "reason": "..."}
      batch: true
      for_each: fetch_submissions.response

  - id: filter_violations
    type: transform
    config:
      transform: |
        .[] | select(.classification == "violation")

  - id: notify_moderators
    type: slack
    config:
      channel: "#content-review"
      message: |
        Found {{ filter_violations.response | length }} violations
        Check: {{ env.CONTENT_REVIEW_URL }}
      condition: "filter_violations.response | length > 0"

  - id: archive_safe
    type: database
    config:
      query: |
        UPDATE submissions 
        SET reviewed = true, classification = '{{ classify.response[].classification }}' 
        WHERE id IN ({{ classify.response[].id }})
      condition: "classify.response | length > 0"

edges:
  - from: fetch_submissions
    to: classify
  - from: classify
    to: filter_violations
  - from: filter_violations
    to: notify_moderators
  - from: classify
    to: archive_safe
```

**Schedule:** `0 * * * *` (Hourly)

### Example 3: Data Pipeline with Parallelization

```yaml
name: ETL Pipeline
description: Extract from 3 sources, transform, load to warehouse

nodes:
  - id: extract_sources
    type: parallel
    children:
      - id: source_api_1
        type: http
        config:
          url: "https://api1.example.com/data"
      - id: source_api_2
        type: http
        config:
          url: "https://api2.example.com/data"
      - id: source_database
        type: database
        config:
          query: "SELECT * FROM internal_db"

  - id: transform
    type: python
    config:
      code: |
        import pandas as pd
        
        data1 = {{ extract_sources.source_api_1.response }}
        data2 = {{ extract_sources.source_api_2.response }}
        data3 = {{ extract_sources.source_database.response }}
        
        df = pd.concat([data1, data2, data3])
        df_clean = df.dropna()
        return df_clean.to_json()

  - id: load_warehouse
    type: database
    config:
      query: |
        INSERT INTO warehouse.daily_data (data)
        VALUES ('{{ transform.response }}')

  - id: notify_success
    type: slack
    config:
      channel: "#data-team"
      message: "ETL pipeline completed successfully"

edges:
  - from: extract_sources
    to: transform
  - from: transform
    to: load_warehouse
  - from: load_warehouse
    to: notify_success
```

**Schedule:** `0 2 * * *` (Daily at 2 AM)

---

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Report Issues
- GitHub Issues: [CorvinOS/issues](https://github.com/CorvinLabs/CorvinOS/issues)
- Include workflow YAML + error log + steps to reproduce

### Suggest Features
- GitHub Discussions: [Marketplace/discussions](https://github.com/CorvinLabs/Corvin-Marketplace/discussions)
- Use thread: "Workflows Plugin Feature Requests"

---

## 📄 License

Apache 2.0. See [LICENSE](../../LICENSE).

---

## 🙋 Support

- **Documentation:** This README (most comprehensive)
- **API Reference:** See "API Reference" section above
- **Examples:** See "Examples" section above
- **Issues:** [GitHub Issues](https://github.com/CorvinLabs/Corvin-Marketplace/issues?q=label%3Aworkflows)
- **Discussions:** [Marketplace Discussions](https://github.com/CorvinLabs/Corvin-Marketplace/discussions)
- **Security:** [security@corvinlabs.io](mailto:security@corvinlabs.io)

---

**Version:** 2.0.0 | **Status:** Production | **Last Updated:** 2026-09-23

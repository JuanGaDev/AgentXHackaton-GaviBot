# AGENTS_USE.md

Documentation for the SRE Incident Intake & Triage Agent, following the [Anthropic AGENTS_USE.md format](https://docs.anthropic.com/en/docs/agents-use-md).

---

## Agent Overview

**Name**: GaviBot — SRE Incident Intake & Triage Agent  
**Purpose**: Automate the end-to-end SRE incident management pipeline for the Solidus e-commerce platform  
**Framework**: LangGraph (stateful directed graph)  
**LLM**: Google `gemma-3-27b-it` via the `google-generativeai` SDK  
**Embeddings**: `models/text-embedding-004` (same API key, different model)

---

## Use Cases

### Primary: Incident Triage & Routing

When an engineer reports an incident through the UI or API:

1. Input is sanitized and validated (guardrails)
2. The incident is analyzed against the Solidus Ruby codebase via RAG
3. Severity (P0–P4) and responsible team are determined by the LLM
4. A Linear ticket is created with full technical context (or a mock ticket if Linear is not configured)
5. The responsible team is notified via Slack (if configured)
6. The reporter receives an email confirmation via Resend (if configured)
7. Notification content is stored in the audit log and displayed in the UI regardless of whether external services are available

### Secondary: Resolution Tracking

Two paths for incident resolution:

**Production path**: Linear webhook fires `POST /api/v1/webhooks/linear` when a ticket status changes to "completed" → `resolve_node` notifies the reporter.

**Demo path**: `POST /api/v1/incidents/{id}/resolve` manually triggers the resolution flow — no Linear or webhook setup required.

---

## Agent Architecture

### LangGraph State Machine

```
Entry
  │
  ▼
intake_node ──[guardrail_passed = False]──► END (incident status = failed)
  │
  [guardrail_passed = True]
  │
  ▼
triage_node  (Gemini LLM + RAG over Solidus codebase)
  │
  ▼
route_node   (validate team; P0 → infrastructure override)
  │
  ▼
ticket_node  (Linear GraphQL or MOCK-XXXX)
  │
  ▼
notify_node  (Slack team + Slack reporter + Resend email)
  │
  ▼
END

─── separate ───────────────────────────────────────────────────────
resolve_node (triggered by Linear webhook OR POST /incidents/{id}/resolve)
  ├─ Sends Resend resolution email to reporter
  ├─ Sends Slack resolution notification to reporter
  ├─ Appends resolution_preview to notification_previews
  └─ Ends the Langfuse trace
```

### Node Reference

| Node | File | What it does |
|------|------|--------------|
| `intake_node` | `agent/nodes/intake.py` | Runs all guardrails; sanitizes title/description; sets `guardrail_passed` |
| `triage_node` | `agent/nodes/triage.py` | Queries ChromaDB for relevant Solidus code; calls Gemini multimodal; parses structured JSON response |
| `route_node` | `agent/nodes/route.py` | Validates team against allowlist; escalates P0 to `infrastructure` |
| `ticket_node` | `agent/nodes/ticket.py` | Creates Linear issue via GraphQL; falls back to `MOCK-XXXXXXXX` if no API key |
| `notify_node` | `agent/nodes/notify.py` | Slack (team channel + reporter) + Resend email (reporter); builds `notification_previews` |
| `resolve_node` | `agent/nodes/resolve.py` | Resend resolution email + Slack resolution message; closes Langfuse trace |

### State Schema (`agent/state.py`)

```python
class IncidentState(TypedDict):
    # Input
    incident_id: str
    title: str
    description: str
    reporter_name: str
    reporter_email: str
    severity_hint: Optional[str]
    attachment_paths: list[str]
    log_content: Optional[str]

    # Set by intake_node
    guardrail_passed: bool
    guardrail_reason: Optional[str]

    # Set by triage_node
    severity_final: Optional[str]        # P0 / P1 / P2 / P3 / P4
    assigned_team: Optional[str]         # backend / frontend / payments / infrastructure / database
    affected_components: list[str]
    root_cause_hint: Optional[str]
    triage_summary: Optional[str]
    triage_confidence: Optional[str]     # high / medium / low
    recommended_actions: list[str]

    # Set by ticket_node
    linear_ticket_id: Optional[str]
    linear_ticket_url: Optional[str]
    linear_ticket_identifier: Optional[str]

    # Set by notify_node and resolve_node
    team_notified: bool
    reporter_notified: bool
    notification_previews: Optional[list[dict]]  # stored in audit log, shown in UI

    # Meta
    error: Optional[str]
    trace_context: Optional[object]      # Langfuse TraceContext
```

---

## Implementation Details

### LLM Analysis (`integrations/gemini_client.py`)

**Model**: `gemma-3-27b-it`  
**Temperature**: 0.2 (low — consistent, factual output)  
**Max tokens**: 4096  

The triage node builds a multipart prompt:
1. System prompt defining severity scale, team list, and JSON output schema
2. Incident text (title, description, reporter, severity hint)
3. Log file content — first 5,000 chars (if uploaded)
4. Relevant Solidus code from RAG — first 3,000 chars
5. Attached images as base64 `inline_data` parts (up to 3 images)

**Output**: Gemini returns strictly JSON with:
```json
{
  "severity": "P0|P1|P2|P3|P4",
  "assigned_team": "backend|frontend|payments|infrastructure|database|unknown",
  "affected_components": ["..."],
  "root_cause_hint": "...",
  "triage_summary": "...",
  "confidence": "high|medium|low",
  "recommended_actions": ["..."]
}
```

If Gemini fails (quota exceeded, network error, malformed JSON), the node returns a safe fallback: `P2 / backend / "Automated triage failed — manual review needed"`. The pipeline always continues.

### RAG over Solidus Codebase

**Files**: `rag/indexer.py`, `rag/retriever.py`

**Indexing** (runs once on startup, in background):
1. Clones Solidus from GitHub with `depth=1` (latest commit only, no history)
2. Finds all `.rb`, `.rake`, `.gemspec` files excluding `spec/`, `test/`, `vendor/`
3. Chunks files at ~800 chars with 20-line overlap
4. Embeds each chunk via `text-embedding-004` with `task_type=retrieval_document`
5. Stores vectors + text + file metadata in ChromaDB (`solidus_codebase` collection)
6. Skips re-indexing if collection already has >100 chunks (idempotent)

**Retrieval** (per incident, at triage time):
1. Embeds `title + description` with `task_type=retrieval_query`
2. Cosine similarity search for top-5 chunks
3. Filters out chunks with distance > 1.2 (low relevance)
4. Returns up to 3 formatted snippets with file paths

### Team Routing (`agent/nodes/route.py`)

Valid teams: `backend`, `frontend`, `payments`, `infrastructure`, `database`, `unknown`

Rules applied after LLM classification:
- Unknown or invalid team → defaults to `backend`
- **P0 + team not in {infrastructure, payments}** → overrides to `infrastructure`

### Notifications (`agent/nodes/notify.py`, `agent/nodes/resolve.py`)

Three channels, all optional (graceful degradation if not configured):

| Channel | Service | When |
|---------|---------|------|
| Team Slack | Incoming Webhook | After ticket creation — Block Kit message with severity, summary, components, actions |
| Reporter Slack | Incoming Webhook | After ticket creation — confirmation with ticket ID |
| Reporter Email | Resend API | After ticket creation + after resolution |

Regardless of whether external services succeed, `notify_node` always writes `notification_previews` to the state — structured dicts with `type`, `to`, `subject`, and `body`. These are saved as `AuditLog` entries with `stage="notification_preview"` and displayed in the **Email Notifications** card in the UI.

### Email Integration (`integrations/email_client.py`)

**Service**: Resend  
**From address**: `SRE Agent <onboarding@resend.dev>` (free tier — no domain verification needed)

Two emails per incident lifecycle:
- `send_reporter_created()` — "Your incident has been received and triaged"
- `send_reporter_resolved()` — "Your incident has been resolved"

Both silently skip if `RESEND_API_KEY` is empty.

### Linear Integration (`integrations/linear_client.py`)

Uses the Linear **GraphQL API** (Linear has no traditional REST API).

```graphql
mutation CreateIssue($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { id identifier url }
  }
}
```

Priority mapping: `P0 → Urgent (1)`, `P1 → High (2)`, `P2 → Medium (3)`, `P3/P4 → Low (4)`

**Mock mode** (no `LINEAR_API_KEY`):
```python
{"id": "MOCK-7E234A30", "url": "https://linear.app/mock/issue/MOCK-7E234A30", "identifier": "MOCK-7E234A30"}
```

---

## Safety & Guardrails

**File**: `agent/guardrails.py`

### 1. Input Sanitization
- `bleach.clean()` strips all HTML tags — prevents XSS if content is ever rendered as HTML
- Regex removal of control characters (null bytes, etc.)
- Field length limits: title ≤ 500 chars, description ≤ 10,000 chars
- Email format validation

### 2. Prompt Injection Detection (Regex Layer)
Fast heuristic check — 14 compiled regex patterns — before any LLM call:

```
ignore previous instructions  |  you are now a  |  disregard your
system prompt  |  jailbreak  |  act as  |  do anything now  |  dan mode
<script>  |  javascript:  |  eval(  |  __import__  |  os.system  |  subprocess
```

If any pattern matches, `guardrail_passed = False` and the pipeline ends immediately.

> Note: `check_prompt_injection()` (LLM-based classifier) exists in `gemini_client.py` but is not called in the main pipeline. It is available as an optional second layer if needed.

### 3. File Upload Validation
- Type allowlist: `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.txt`, `.log`, `.json`, `.csv`
- Max size: 10MB per file
- Max files: 5 per incident

### 4. Gemini Safety Settings
Model configured with `BLOCK_MEDIUM_AND_ABOVE` for all harm categories:
`HARASSMENT`, `HATE_SPEECH`, `SEXUALLY_EXPLICIT`, `DANGEROUS_CONTENT`

### 5. Linear Webhook Signature Verification
Payloads verified via HMAC-SHA256 against `LINEAR_WEBHOOK_SECRET`. If the secret is not configured, verification is skipped with a warning (safe for local demo).

---

## Database Schema

**File**: `db/models.py`

### `incidents` table

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `title` | String(500) | Sanitized title |
| `description` | Text | Sanitized description |
| `reporter_email` | String(255) | Reporter email |
| `reporter_name` | String(255) | Reporter name |
| `severity_hint` | Enum | What reporter submitted (P0–P4) |
| `severity_final` | Enum | What the AI determined (P0–P4) |
| `status` | Enum | received → triaging → triaged → ticket_created → notified → resolved / failed |
| `assigned_team` | Enum | backend / frontend / payments / infrastructure / database / unknown |
| `triage_summary` | Text | AI-generated 2–3 sentence summary |
| `affected_components` | JSON | Array of component names |
| `root_cause_hint` | Text | AI hypothesis |
| `linear_ticket_id` | String | Linear issue ID or MOCK-XXXX |
| `linear_ticket_url` | String | Link to Linear issue |
| `attachments` | JSON | Array of uploaded file paths |
| `error_detail` | Text | Set if pipeline fails |

### `incident_audit_logs` table

> Note: named `incident_audit_logs` (not `audit_logs`) to avoid conflict with Langfuse's own `audit_logs` table in the shared PostgreSQL database.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `incident_id` | UUID | Foreign key → `incidents.id` |
| `stage` | String | Pipeline stage name |
| `message` | Text | Human-readable event description |
| `extra_data` | JSON | Stage-specific data (severity, team, ticket ID, email preview content) |
| `success` | Boolean | Whether the step succeeded |

Entries with `stage = "notification_preview"` are filtered out of the main audit timeline and shown separately in the UI's **Email Notifications** card.

---

## Observability

### Langfuse Integration (`observability/langfuse_setup.py`)

Every pipeline invocation creates a Langfuse trace:
- **Trace**: Full pipeline execution (identified by `incident_id`)
- **Span per node**: `intake`, `route`, `ticket`, `notify`, `resolve`
- **Generation**: Gemini call in `triage_node` with truncated prompt + completion

If `LANGFUSE_SECRET_KEY` and `LANGFUSE_PUBLIC_KEY` are not set, `TraceContext` runs as a no-op — all trace calls silently do nothing.

### Structured Logging (`observability/logging_config.py`)

JSON logs to stdout:
```json
{"timestamp": "...", "level": "INFO", "logger": "app.agent.nodes.triage",
 "message": "Triage complete for abc123: severity=P1 team=payments",
 "incident_id": "abc123", "stage": "triage"}
```

View live: `docker compose logs -f backend`

---

## Demo Mode Summary

| Feature | Without key | Behavior |
|---------|-------------|----------|
| AI triage | No `GEMINI_API_KEY` | Returns fallback: P2, backend, "manual review needed" |
| RAG indexing | No `GEMINI_API_KEY` | Skips embedding, returns empty context |
| Linear ticket | No `LINEAR_API_KEY` | Returns `MOCK-XXXXXXXX` |
| Slack notification | No webhook URL | Logs warning, pipeline continues |
| Email notification | No `RESEND_API_KEY` | Logs warning; preview still shown in UI |
| Observability | No Langfuse keys | Tracing disabled silently |
| Resolution | No Linear webhook | Use `POST /api/v1/incidents/{id}/resolve` demo endpoint |

---

## Known Limitations

1. **Solidus indexing**: First boot clones the full Solidus repo and indexes ~500 Ruby files. Takes 5–10 min and requires internet. ChromaDB is persistent across restarts.

2. **Async/sync boundary**: LangGraph nodes are synchronous. Async integrations (Linear, Slack) use `ThreadPoolExecutor` to run coroutines from sync context.

3. **Single-tenant**: Credentials are global. Multi-tenant support would require workspace-scoped keys.

4. **Production resolution**: Linear webhook requires a publicly accessible URL. Use ngrok for local testing: `ngrok http 8000` → set URL in Linear webhook settings.

5. **Gemini rate limits**: Free tier has RPM/TPD limits. If you see `429` errors, create a new API key from a fresh Google project at https://ai.google.dev/gemini-api/docs/rate-limits.

6. **Schema migration**: Uses SQLAlchemy `create_all()` — tables are created on first boot but not altered on schema changes. Use `docker compose down -v` to reset if schema conflicts occur.

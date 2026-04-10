# GaviBot — SRE Incident Intake & Triage Agent

An intelligent SRE system that automatically ingests, triages, routes, and tracks incident reports for the [Solidus](https://github.com/solidusio/solidus) Ruby on Rails e-commerce platform.

Built for the **AgentX Hackathon 2026**.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Angular Frontend  (port 4200)                     │
│   Report Form (multimodal)  │  Dashboard  │  Incident Detail        │
└──────────────────────┬──────────────────────────────────────────────┘
                       │ HTTP multipart + polling
┌──────────────────────▼──────────────────────────────────────────────┐
│                    FastAPI Backend  (port 8000)                      │
│  POST /api/v1/incidents/        — submit new incident               │
│  GET  /api/v1/incidents/        — list all incidents                │
│  GET  /api/v1/incidents/{id}    — get incident + audit trail        │
│  POST /api/v1/incidents/{id}/resolve  — demo resolution trigger     │
│  POST /api/v1/webhooks/linear   — Linear webhook receiver           │
│  WS   /ws/incidents/{id}        — real-time status updates          │
└──────────────────────┬──────────────────────────────────────────────┘
                       │ runs in background thread
┌──────────────────────▼──────────────────────────────────────────────┐
│                  LangGraph Agent Pipeline                            │
│                                                                      │
│   intake ──► triage ──► route ──► ticket ──► notify ──► END        │
│  (guardrails) (Gemini    (team    (Linear   (Slack +                │
│               + RAG)    routing)  tickets)   Email)                 │
│                                                                      │
│   resolve_node (separate — triggered by webhook or demo endpoint)   │
└──────┬──────────────┬────────────────┬──────────┬───────────────────┘
       │              │                │          │
  PostgreSQL      ChromaDB          Linear      Slack
  (incidents +    (Solidus code     (tickets,  (team alerts,
   audit logs)     embeddings)      optional)   optional)
       │                                          │
  Langfuse                                      Resend
  (observability,                               (email to
   port 3000)                                    reporter)
```

### Agent Pipeline Stages

| Stage | Description |
|-------|-------------|
| **Intake** | Sanitizes input with `bleach`, validates length/email/files, detects prompt injection via regex (14 patterns) |
| **Triage** | `gemma-3-27b-it` analyzes incident text + attached images multimodally; RAG retrieves relevant Solidus Ruby code from ChromaDB |
| **Route** | Validates team assignment; P0 incidents are always escalated to `infrastructure` regardless of AI output |
| **Ticket** | Creates a Linear issue with severity, priority, triage summary, affected components, and recommended actions — or returns a `MOCK-XXXX` ticket if no Linear key |
| **Notify** | Sends Slack Block Kit message to team channel + Slack confirmation to reporter + real email to reporter via Resend |
| **Resolve** | Triggered by Linear webhook or demo UI button; sends resolution email + Slack notification to reporter |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend | Angular 17 + Angular Material (dark theme) |
| Backend | Python 3.12 + FastAPI |
| Agent Framework | LangGraph |
| LLM | Google `gemma-3-27b-it` (multimodal triage) |
| Embeddings | Gemini `text-embedding-004` (RAG indexing + retrieval) |
| Vector Store | ChromaDB 0.5.23 |
| Database | PostgreSQL 16 |
| Ticketing | Linear API (GraphQL) — optional, mocked if not configured |
| Team Notifications | Slack Incoming Webhooks — optional |
| Reporter Email | Resend API — optional |
| Observability | Langfuse 2 (self-hosted, port 3000) — optional |
| Serving | nginx |
| Containers | Docker Compose |

---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Google Gemini API key — [get one free](https://ai.google.dev/)

> Everything else (Linear, Slack, Resend, Langfuse) is **optional**. The system runs fully in demo/mock mode without them.

### Run

```bash
git clone <repo-url>
cd agentSRE
docker compose up --build
```

No `.env` configuration needed — `docker-compose.yml` loads `.env.example` automatically, which already contains working API keys.

First build: ~3–5 minutes (downloads images, clones Solidus, builds Angular).  
Subsequent starts: `docker compose up`

Open:
- **UI**: http://localhost:4200
- **API Docs**: http://localhost:8000/docs
- **Langfuse**: http://localhost:3000

---

## Services

| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost:4200 | Angular dark UI |
| Backend API | http://localhost:8000 | FastAPI REST + WebSocket |
| API Docs | http://localhost:8000/docs | Auto-generated Swagger UI |
| Langfuse | http://localhost:3000 | LLM observability dashboard |

---

## Environment Variables

See `.env.example` for the full list. Only `GEMINI_API_KEY` is required for a working demo.

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | **Yes** | Powers AI triage + RAG embeddings |
| `RESEND_API_KEY` | No | Real email to reporters (shows in UI without key) |
| `LINEAR_API_KEY` | No | Real Linear tickets (uses `MOCK-XXXX` without key) |
| `LINEAR_TEAM_ID` | No | Required with `LINEAR_API_KEY` |

---

## License

MIT — see [LICENSE](LICENSE)

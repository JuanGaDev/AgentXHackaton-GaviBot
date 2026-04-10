# Quick Start Guide

Get GaviBot running in under 5 minutes.

---

## Step 1: Clone the Repository

```bash
git clone <https://github.com/JuanGaDev/AgentXHackaton-GaviBot>
cd agentSRE
```

---

## Step 2: Start the Application

```bash
docker compose up --build
```

> No `.env` setup required. The `docker-compose.yml` automatically loads `.env.example`, which already has working API keys for Gemini and Resend.

**First build** takes 3–5 minutes:
- Downloads Docker images (PostgreSQL, ChromaDB, Langfuse)
- Installs Python and Node dependencies
- Builds the Angular app

**Subsequent starts** (no rebuild):
```bash
docker compose up
```

**Background Solidus indexing**: On first startup, the backend clones the Solidus GitHub repository and indexes ~500 Ruby files into ChromaDB. This takes 5–10 minutes and happens automatically in the background. You can submit incidents while it's running — the RAG context will be empty until indexing finishes.

---

## Step 3: Open the UI

| URL | What it is |
|-----|-----------|
| http://localhost:4200 | GaviBot frontend |
| http://localhost:8000/docs | FastAPI auto-generated API docs |
| http://localhost:3000 | Langfuse observability (optional) |

---

## Step 4: Submit a Test Incident

### Via UI

1. Go to http://localhost:4200
2. Click **Report Incident** in the top navigation
3. Fill in title and description (use examples from `test_incidents.txt`)
4. Optionally attach a screenshot or log file
5. Click **Submit Incident Report**
6. You are redirected to the detail page — watch the pipeline progress bar in real time

### Via API (curl)

```bash
curl -X POST http://localhost:8000/api/v1/incidents/ \
  -F "title=Checkout failing with 500 error on payment step" \
  -F "description=Users are unable to complete purchases. Getting HTTP 500 on /checkout/payment. Started 30 minutes ago. Around 50% of orders are failing. Error: Spree::Payment validation failed." \
  -F "reporter_name=Jane Smith" \
  -F "reporter_email=jane@example.com" \
  -F "severity_hint=P1"
```

---

## Step 5: Understanding the Pipeline Output

Once the pipeline completes, the incident detail page shows:

**Pipeline progress bar**: Received → Triage → Triaged → Ticket → Notified → Resolved

**AI Triage Analysis card**:
- Severity (P0–P4) determined by the AI
- Assigned team (backend / frontend / payments / infrastructure / database)
- Affected components (e.g., `Spree::Payment`, `checkout_controller`)
- Root cause hypothesis
- Recommended actions

**Linear ticket**: Shows `MOCK-XXXXXXXX` (without a real Linear API key) or a real Linear issue URL.

**Email Notifications card**: Shows the exact email content sent to the reporter — confirmation on intake, resolution notice on resolve.

---

## Step 6: Simulate Resolution (Demo Mode)

When the engineering team resolves the issue, the reporter is automatically notified. In demo mode (no real Linear webhook), you can trigger this manually:

1. Open any incident that is in `ticket_created` or `notified` status
2. Scroll to the **Demo: Simulate Resolution** card
3. Click **Mark as Resolved**
4. Watch the pipeline status jump to `resolved`
5. A resolution email appears in the **Email Notifications** card

In production with a real Linear API key, this triggers automatically when the Linear ticket is marked **Done**.

---

## Step 7: Langfuse Observability (Optional)

To connect Langfuse tracing:

1. Open http://localhost:3000
2. Sign up with any email/password
3. Create an organization and project
4. Go to Settings → API Keys → Create new key pair
5. Add to your `.env`:
   ```
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   ```
6. Restart backend: `docker compose restart backend`

You can now see full LLM traces per incident: prompt, completion, token usage, and latency per node.

---

## Useful API Endpoints

```bash
# List all incidents
curl http://localhost:8000/api/v1/incidents/

# Get a specific incident with full details
curl http://localhost:8000/api/v1/incidents/<incident-id>

# Get audit trail for an incident
curl http://localhost:8000/api/v1/incidents/<incident-id>/audit

# Manually resolve an incident (demo endpoint)
curl -X POST http://localhost:8000/api/v1/incidents/<incident-id>/resolve

# System stats
curl http://localhost:8000/api/v1/stats

# Health check
curl http://localhost:8000/health
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Backend fails to start | Wait for postgres health: `docker compose ps` — postgres must be healthy first |
| "Automated triage failed: 429" | Gemini API quota exceeded. Get a new key at https://ai.google.dev/, update `GEMINI_API_KEY` in `.env.example`, then `docker compose restart backend` |
| Solidus indexing slow | Expected on first boot — 5–10 min. ChromaDB volume persists across restarts, so it only happens once |
| No email notifications | Check `RESEND_API_KEY` in `.env.example`; notifications still display in UI regardless |
| No Linear tickets | Without `LINEAR_API_KEY`, mock tickets (`MOCK-XXXX`) are created — this is normal for demo |
| Angular build fails | Run `docker compose build frontend` to see build errors in detail |
| Port conflict | Edit `docker-compose.yml` — change `4200:80` to `4201:80`, etc. |
| Need a fresh DB | `docker compose down -v` then `docker compose up --build` |

---

## Stopping

```bash
docker compose down          # Stop, keep all data volumes
docker compose down -v       # Stop and wipe all data (fresh start)
```

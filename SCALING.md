# Scaling Architecture

How the GaviBot scales from hackathon prototype to production-grade system.

---

## Current Architecture (Single-Host Docker Compose)

The current implementation runs all services on a single host via Docker Compose. This is appropriate for:
- Hackathon demo
- Small teams (< 50 incidents/day)
- Development and evaluation

**Constraints**:
- Single point of failure
- Vertical scaling only
- Shared database connection pool
- RAG index rebuilt per instance

---

## Scaling Dimensions

### 1. Incident Volume (Horizontal Backend Scaling)

**Current**: Single FastAPI container  
**Scale to**: Multiple backend replicas behind a load balancer

```
                   ┌── backend:8000 (replica 1)
nginx/ALB ────────├── backend:8001 (replica 2)
                   └── backend:8002 (replica 3)
```

- FastAPI + uvicorn is async-native and scales well horizontally
- Use `gunicorn` with `uvicorn` workers for production: `gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app`
- Session state is stored in PostgreSQL (not in-process), so replicas are stateless
- WebSocket connections can be distributed via sticky sessions or moved to a dedicated WebSocket service

**Docker Compose scale**: `docker compose up --scale backend=3`

### 2. Pipeline Throughput (Background Task Queue)

**Current**: LangGraph pipeline runs in FastAPI `BackgroundTasks` (in-process thread pool)  
**Scale to**: Celery + Redis (or AWS SQS) task queue

```
FastAPI ──► [Redis Queue] ──► Celery Worker 1 (LangGraph)
                          ──► Celery Worker 2 (LangGraph)
                          ──► Celery Worker N (LangGraph)
```

Benefits:
- Decouple incident ingestion from processing
- Retry failed pipelines automatically
- Scale workers independently from API
- Priority queues for P0/P1 incidents

### 3. LLM Calls (Caching + Rate Limit Management)

**Current**: Direct Gemini API calls, no caching  
**Scale to**:
- **Semantic cache**: Cache Gemini responses for similar incident descriptions (using cosine similarity on embeddings). Reduces redundant API calls.
- **OpenRouter fallback**: Route to alternative models (GPT-4o, Claude 3.5) when Gemini rate limits are hit
- **Request batching**: Batch embedding requests for the RAG indexer

### 4. Vector Store (ChromaDB → Managed)

**Current**: ChromaDB in Docker container (single instance)  
**Scale to**:
- **Pinecone** or **Weaviate**: Managed, horizontally scalable vector databases with serverless tiers
- **Shared index**: Multiple backend replicas share the same vector index (no re-indexing per replica)
- **Index updates**: Incremental indexing as the Solidus codebase is updated (Git webhook → re-index changed files)

### 5. Database (PostgreSQL Scaling)

**Current**: Single PostgreSQL 16 container  
**Scale to**:
- **Read replicas**: Route `GET /incidents` queries to read replicas
- **Connection pooling**: Add PgBouncer between backend and PostgreSQL to handle connection limits
- **Managed service**: AWS RDS, Google Cloud SQL, or Supabase for HA and automated backups
- **Partitioning**: Partition `incidents` table by `created_at` month for large historical datasets

### 6. Multi-Tenancy (Multiple E-commerce Clients)

**Current**: Single-tenant, hardcoded Solidus  
**Scale to**:
- Tenant-scoped API keys for Linear and Slack
- Separate ChromaDB collections per codebase
- Tenant middleware in FastAPI to route requests to correct config
- Multiple RAG indices (one per supported e-commerce platform)

---

## Production Deployment Architecture

```
                          CDN / CloudFront
                               │
                    ┌──────────▼──────────┐
                    │   Load Balancer      │
                    │  (nginx / ALB)       │
                    └──┬──────────────┬───┘
                       │              │
             ┌─────────▼──┐   ┌───────▼─────────┐
             │  Frontend   │   │   Backend API    │
             │  (S3/nginx) │   │  (k8s Deployment)│
             └─────────────┘   └───────┬──────────┘
                                       │
                          ┌────────────▼────────────┐
                          │      Redis              │
                          │  (Task Queue + Cache)    │
                          └────────────┬────────────┘
                                       │
                         ┌─────────────▼──────────┐
                         │  Celery Workers (k8s)   │
                         │  - LangGraph pipelines  │
                         └─────────────┬───────────┘
                                       │
              ┌──────────┬─────────────┼───────────────┐
              │          │             │               │
       PostgreSQL     ChromaDB      Gemini          Langfuse
       (RDS/Aurora)   (Pinecone)    API             (managed)
```

---

## Key Design Decisions

### Why LangGraph over simple function calls?
LangGraph provides **explicit state management** at each pipeline step. If a node fails, the state before that failure is preserved. This enables:
- Retry failed stages without reprocessing earlier stages
- Human-in-the-loop approval between stages (e.g., manual severity override before ticket creation)
- Observable pipeline with per-node metrics

### Why PostgreSQL over a NoSQL store?
Incidents have **relational properties**: foreign keys between incidents and audit logs, complex queries for dashboard filtering, ACID guarantees for audit compliance. PostgreSQL's JSONB columns handle the semi-structured triage result fields.

### Why self-hosted Langfuse over SaaS tracing?
- **Data privacy**: LLM inputs/outputs (incident descriptions) stay on-premise
- **No additional vendor API keys** required
- **Cost**: Free at any volume

### Why ChromaDB for RAG?
For hackathon/prototype scale, ChromaDB runs entirely in Docker with no external service. The embedding index persists across container restarts via a named volume. Migration to Pinecone requires only changing `get_chroma_client()` in `rag/indexer.py`.

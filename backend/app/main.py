"""
SRE Incident Intake & Triage Agent - FastAPI Application
"""
import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.db.session import init_db
from app.api.routes.incidents import router as incidents_router
from app.api.routes.webhooks import router as webhooks_router
from app.observability.logging_config import setup_logging, get_logger

setup_logging(os.getenv("LOG_LEVEL", "INFO"))
logger = get_logger(__name__)


class ConnectionManager:
    """Manage WebSocket connections for real-time incident status updates."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, incident_id: str):
        await websocket.accept()
        if incident_id not in self.active_connections:
            self.active_connections[incident_id] = []
        self.active_connections[incident_id].append(websocket)

    def disconnect(self, websocket: WebSocket, incident_id: str):
        if incident_id in self.active_connections:
            try:
                self.active_connections[incident_id].remove(websocket)
            except ValueError:
                pass

    async def broadcast(self, incident_id: str, message: dict):
        connections = self.active_connections.get(incident_id, [])
        disconnected = []
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            connections.remove(ws)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("GaviBot starting up...")
    await init_db()
    logger.info("Database initialized")

    # Start Solidus indexing in background (non-blocking)
    asyncio.create_task(_index_solidus_background())

    yield

    logger.info("GaviBot shutting down")


async def _index_solidus_background():
    """Index Solidus codebase in the background after startup."""
    try:
        await asyncio.sleep(5)  # Let the app fully start first
        from app.rag.indexer import index_solidus
        count = await index_solidus()
        logger.info(f"Solidus indexing complete: {count} chunks")
    except Exception as e:
        logger.error(f"Background Solidus indexing failed: {e}")


app = FastAPI(
    title="SRE Incident Intake & Triage Agent",
    description="Automated SRE incident triage system for Solidus e-commerce",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(incidents_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "sre-agent"}


@app.get("/api/v1/stats")
async def stats():
    """Return basic system stats."""
    from app.db.session import AsyncSessionLocal
    from app.db.models import Incident, IncidentStatus
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Incident.status, func.count(Incident.id)).group_by(Incident.status)
        )
        counts = {row[0].value: row[1] for row in result.all()}

    return {
        "incidents_by_status": counts,
        "total": sum(counts.values()),
    }


@app.websocket("/ws/incidents/{incident_id}")
async def websocket_incident(websocket: WebSocket, incident_id: str):
    """WebSocket endpoint for real-time incident status updates."""
    await manager.connect(websocket, incident_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, incident_id)


@app.get("/")
async def root():
    return {
        "message": "SRE Incident Intake & Triage Agent",
        "docs": "/docs",
        "health": "/health",
    }

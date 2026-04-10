"""
Incident API endpoints: create, list, get, and file upload.
"""
import os
import uuid
import aiofiles
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel, EmailStr

from app.db.session import get_db
from app.db.models import Incident, AuditLog, IncidentStatus, Severity, TeamName
from app.agent.graph import run_incident_pipeline
from app.observability.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/incidents", tags=["incidents"])

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


class IncidentResponse(BaseModel):
    id: str
    title: str
    description: str
    reporter_name: str
    reporter_email: str
    status: str
    severity_hint: Optional[str]
    severity_final: Optional[str]
    assigned_team: Optional[str]
    triage_summary: Optional[str]
    affected_components: Optional[list]
    root_cause_hint: Optional[str]
    recommended_actions: Optional[list]
    linear_ticket_id: Optional[str]
    linear_ticket_url: Optional[str]
    linear_ticket_identifier: Optional[str]
    attachments: Optional[list]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


async def _save_upload(file: UploadFile, incident_id: str) -> Optional[str]:
    """Save uploaded file and return the path."""
    upload_path = Path(UPLOAD_DIR) / incident_id
    upload_path.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = upload_path / filename

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        return None

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    return str(file_path)


async def _run_pipeline_and_update(
    incident_id: str,
    db_session_factory,
    title: str,
    description: str,
    reporter_name: str,
    reporter_email: str,
    severity_hint: Optional[str],
    attachment_paths: list[str],
    log_content: Optional[str],
):
    """Background task: run the agent pipeline and update the database."""
    from app.db.session import AsyncSessionLocal

    # Update status to triaging
    async with AsyncSessionLocal() as session:
        incident = await session.get(Incident, uuid.UUID(incident_id))
        if incident:
            incident.status = IncidentStatus.TRIAGING
            await session.commit()

    # Run LangGraph pipeline
    final_state = await run_incident_pipeline(
        incident_id=incident_id,
        title=title,
        description=description,
        reporter_name=reporter_name,
        reporter_email=reporter_email,
        severity_hint=severity_hint,
        attachment_paths=attachment_paths,
        log_content=log_content,
    )

    # Update incident with results
    async with AsyncSessionLocal() as session:
        incident = await session.get(Incident, uuid.UUID(incident_id))
        if not incident:
            return

        if not final_state.get("guardrail_passed"):
            incident.status = IncidentStatus.FAILED
            incident.error_detail = final_state.get("guardrail_reason", "Guardrail failed")
        elif final_state.get("error"):
            incident.status = IncidentStatus.FAILED
            incident.error_detail = final_state.get("error", "Unknown error")
        elif final_state.get("team_notified"):
            incident.status = IncidentStatus.NOTIFIED
        elif final_state.get("linear_ticket_id"):
            incident.status = IncidentStatus.TICKET_CREATED
        else:
            incident.status = IncidentStatus.TRIAGED

        incident.severity_final = final_state.get("severity_final")
        incident.assigned_team = final_state.get("assigned_team")
        incident.triage_summary = final_state.get("triage_summary")
        incident.affected_components = final_state.get("affected_components")
        incident.root_cause_hint = final_state.get("root_cause_hint")
        incident.linear_ticket_id = final_state.get("linear_ticket_id")
        incident.linear_ticket_url = final_state.get("linear_ticket_url")

        # Audit log entry
        log = AuditLog(
            incident_id=uuid.UUID(incident_id),
            stage="pipeline_complete",
            message=f"Pipeline finished: status={incident.status}",
            extra_data={
                "severity": final_state.get("severity_final"),
                "team": final_state.get("assigned_team"),
                "ticket": final_state.get("linear_ticket_identifier"),
                "team_notified": final_state.get("team_notified"),
            },
            success=incident.status != IncidentStatus.FAILED,
        )
        session.add(log)

        for preview in (final_state.get("notification_previews") or []):
            preview_log = AuditLog(
                incident_id=uuid.UUID(incident_id),
                stage="notification_preview",
                message=f"Notification → {preview.get('to', '')}",
                extra_data=preview,
                success=True,
            )
            session.add(preview_log)

        await session.commit()

    logger.info(f"Incident {incident_id} updated after pipeline: status={incident.status}")


@router.post("/", response_model=IncidentResponse, status_code=202)
async def create_incident(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    description: str = Form(...),
    reporter_name: str = Form(...),
    reporter_email: str = Form(...),
    severity_hint: Optional[str] = Form(None),
    attachments: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
):
    """Submit a new incident report. Processing happens asynchronously."""
    incident_id = str(uuid.uuid4())

    # Save uploaded files
    attachment_paths = []
    log_content = None

    for upload in attachments:
        if upload.filename:
            file_path = await _save_upload(upload, incident_id)
            if file_path:
                attachment_paths.append(file_path)
                # Read log files inline
                if upload.filename.endswith((".txt", ".log", ".json")):
                    try:
                        async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            log_content = await f.read()
                        log_content = log_content[:5000]
                    except Exception:
                        pass

    # Create incident record
    severity_enum = None
    if severity_hint and severity_hint in Severity.__members__:
        severity_enum = Severity(severity_hint)

    incident = Incident(
        id=uuid.UUID(incident_id),
        title=title[:500],
        description=description,
        reporter_name=reporter_name,
        reporter_email=reporter_email,
        severity_hint=severity_enum,
        status=IncidentStatus.RECEIVED,
        attachments=attachment_paths,
    )
    db.add(incident)
    await db.flush()

    # Audit log
    audit = AuditLog(
        incident_id=uuid.UUID(incident_id),
        stage="received",
        message="Incident received and queued for triage",
        success=True,
    )
    db.add(audit)
    await db.commit()

    # Run pipeline in background
    background_tasks.add_task(
        _run_pipeline_and_update,
        incident_id=incident_id,
        db_session_factory=None,
        title=title,
        description=description,
        reporter_name=reporter_name,
        reporter_email=reporter_email,
        severity_hint=severity_hint,
        attachment_paths=attachment_paths,
        log_content=log_content,
    )

    # Return current state
    await db.refresh(incident)
    return _incident_to_response(incident)


@router.get("/", response_model=list[IncidentResponse])
async def list_incidents(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all incidents, newest first."""
    query = select(Incident).order_by(desc(Incident.created_at)).offset(skip).limit(limit)
    if status:
        query = query.where(Incident.status == status)
    result = await db.execute(query)
    incidents = result.scalars().all()
    return [_incident_to_response(i) for i in incidents]


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(incident_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single incident by ID."""
    try:
        incident = await db.get(Incident, uuid.UUID(incident_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid incident ID")

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    return _incident_to_response(incident)


@router.post("/{incident_id}/resolve", response_model=IncidentResponse)
async def resolve_incident(incident_id: str, db: AsyncSession = Depends(get_db)):
    """Demo endpoint: manually trigger resolution of an incident (simulates Linear webhook)."""
    try:
        incident = await db.get(Incident, uuid.UUID(incident_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid incident ID")

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if incident.status == IncidentStatus.RESOLVED:
        raise HTTPException(status_code=400, detail="Incident is already resolved")

    resolvable = {IncidentStatus.TICKET_CREATED, IncidentStatus.NOTIFIED, IncidentStatus.TRIAGED}
    if incident.status not in resolvable:
        raise HTTPException(status_code=400, detail=f"Cannot resolve incident with status '{incident.status.value}'")

    from app.agent.nodes.resolve import resolve_node
    from app.agent.state import IncidentState

    state: IncidentState = {
        "incident_id": incident_id,
        "title": incident.title,
        "description": incident.description,
        "reporter_name": incident.reporter_name,
        "reporter_email": incident.reporter_email,
        "severity_hint": incident.severity_hint.value if incident.severity_hint else None,
        "attachment_paths": incident.attachments or [],
        "log_content": None,
        "guardrail_passed": True,
        "guardrail_reason": None,
        "severity_final": incident.severity_final.value if incident.severity_final else None,
        "assigned_team": incident.assigned_team.value if incident.assigned_team else None,
        "affected_components": incident.affected_components or [],
        "root_cause_hint": incident.root_cause_hint,
        "triage_summary": incident.triage_summary,
        "triage_confidence": None,
        "recommended_actions": [],
        "linear_ticket_id": incident.linear_ticket_id,
        "linear_ticket_url": incident.linear_ticket_url,
        "linear_ticket_identifier": incident.linear_ticket_id,
        "team_notified": True,
        "reporter_notified": False,
        "error": None,
        "trace_context": None,
    }

    final_state = resolve_node(state)

    incident.status = IncidentStatus.RESOLVED

    audit = AuditLog(
        incident_id=uuid.UUID(incident_id),
        stage="resolved",
        message="Incident manually resolved via demo endpoint. Reporter notified (if Slack configured).",
        extra_data={"triggered_by": "demo_resolve"},
        success=True,
    )
    db.add(audit)

    for preview in (final_state.get("notification_previews") or []):
        if preview.get("type") == "reporter_resolved":
            preview_log = AuditLog(
                incident_id=uuid.UUID(incident_id),
                stage="notification_preview",
                message=f"Notification → {preview.get('to', '')}",
                extra_data=preview,
                success=True,
            )
            db.add(preview_log)

    await db.commit()
    await db.refresh(incident)

    logger.info(f"Incident {incident_id} resolved via demo endpoint")
    return _incident_to_response(incident)


@router.get("/{incident_id}/audit", response_model=list[dict])
async def get_audit_log(incident_id: str, db: AsyncSession = Depends(get_db)):
    """Get audit trail for an incident."""
    try:
        uid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid incident ID")

    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.incident_id == uid)
        .order_by(AuditLog.created_at)
    )
    logs = result.scalars().all()
    return [
        {
            "id": str(log.id),
            "stage": log.stage,
            "message": log.message,
            "success": log.success,
            "metadata": log.extra_data,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


def _incident_to_response(incident: Incident) -> dict:
    return {
        "id": str(incident.id),
        "title": incident.title,
        "description": incident.description,
        "reporter_name": incident.reporter_name,
        "reporter_email": incident.reporter_email,
        "status": incident.status.value if incident.status else "received",
        "severity_hint": incident.severity_hint.value if incident.severity_hint else None,
        "severity_final": incident.severity_final.value if incident.severity_final else None,
        "assigned_team": incident.assigned_team.value if incident.assigned_team else None,
        "triage_summary": incident.triage_summary,
        "affected_components": incident.affected_components or [],
        "root_cause_hint": incident.root_cause_hint,
        "recommended_actions": [],  # stored in Linear ticket description
        "linear_ticket_id": incident.linear_ticket_id,
        "linear_ticket_url": incident.linear_ticket_url,
        "linear_ticket_identifier": incident.linear_ticket_id or "",
        "attachments": incident.attachments or [],
        "created_at": incident.created_at.isoformat() if incident.created_at else "",
        "updated_at": incident.updated_at.isoformat() if incident.updated_at else "",
    }

"""
Linear webhook receiver: processes ticket status updates and triggers resolution flow.
"""
import os
import hashlib
import hmac
import uuid
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.db.models import Incident, IncidentStatus, AuditLog
from app.agent.nodes.resolve import resolve_node
from app.agent.state import IncidentState
from app.observability.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

LINEAR_WEBHOOK_SECRET = os.getenv("LINEAR_WEBHOOK_SECRET", "")


def _verify_linear_signature(body: bytes, signature: str) -> bool:
    """Verify the Linear webhook signature."""
    if not LINEAR_WEBHOOK_SECRET:
        logger.warning("LINEAR_WEBHOOK_SECRET not set - skipping signature verification")
        return True
    expected = hmac.new(LINEAR_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _find_incident_by_ticket(ticket_id: str, db: AsyncSession) -> Optional[Incident]:
    """Find an incident by its Linear ticket ID."""
    result = await db.execute(
        select(Incident).where(Incident.linear_ticket_id == ticket_id)
    )
    return result.scalar_one_or_none()


@router.post("/linear")
async def linear_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Receive Linear webhook events.
    When an issue transitions to 'completed' state, trigger the resolve flow.
    """
    body = await request.body()
    signature = request.headers.get("linear-signature", "")

    if signature and not _verify_linear_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    action = payload.get("action", "")
    data = payload.get("data", {})
    event_type = payload.get("type", "")

    logger.info(f"Linear webhook received: type={event_type} action={action}")

    # We only care about Issue updates where state changes to completed
    if event_type != "Issue" or action != "update":
        return {"status": "ignored", "reason": "Not an issue update"}

    new_state = data.get("state", {})
    state_type = new_state.get("type", "")

    if state_type != "completed":
        return {"status": "ignored", "reason": f"State type is {state_type}, not completed"}

    ticket_id = data.get("id", "")
    if not ticket_id:
        return {"status": "ignored", "reason": "No ticket ID"}

    incident = await _find_incident_by_ticket(ticket_id, db)
    if not incident:
        logger.info(f"No incident found for Linear ticket {ticket_id}")
        return {"status": "ignored", "reason": "No matching incident"}

    incident_id = str(incident.id)
    logger.info(f"Resolving incident {incident_id} for ticket {ticket_id}")

    # Build minimal state for resolve node
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

    # Update incident status
    incident.status = IncidentStatus.RESOLVED

    audit = AuditLog(
        incident_id=uuid.UUID(incident_id),
        stage="resolved",
        message="Incident resolved via Linear webhook. Reporter notified.",
        extra_data={"ticket_id": ticket_id, "reporter_notified": final_state.get("reporter_notified")},
        success=True,
    )
    db.add(audit)
    await db.commit()

    return {"status": "resolved", "incident_id": incident_id}

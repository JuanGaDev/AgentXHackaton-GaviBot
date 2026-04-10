"""
Resolve node: handle Linear webhook for ticket resolution and notify reporter.
"""
import asyncio
import concurrent.futures
from app.agent.state import IncidentState
from app.integrations.slack_client import notify_reporter_resolved
from app.integrations.email_client import send_reporter_resolved
from app.observability.logging_config import get_logger

logger = get_logger(__name__)


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def resolve_node(state: IncidentState) -> IncidentState:
    incident_id = state["incident_id"]
    logger.info(
        f"Processing resolution for incident {incident_id}",
        extra={"stage": "resolve", "incident_id": incident_id},
    )

    send_reporter_resolved(
        reporter_email=state["reporter_email"],
        reporter_name=state["reporter_name"],
        title=state["title"],
        ticket_id=state.get("linear_ticket_identifier") or state.get("linear_ticket_id", "N/A"),
        ticket_url=state.get("linear_ticket_url", ""),
    )

    success = _run_async(
        notify_reporter_resolved(
            reporter_email=state["reporter_email"],
            reporter_name=state["reporter_name"],
            incident_id=incident_id,
            title=state["title"],
            ticket_url=state.get("linear_ticket_url", ""),
            ticket_identifier=state.get("linear_ticket_identifier", ""),
            resolution_note=None,
        )
    )

    if state.get("trace_context"):
        state["trace_context"].span(
            "resolve",
            output_data={"reporter_notified": success},
        )
        state["trace_context"].end()

    logger.info(
        f"Incident {incident_id} resolved. Reporter notified: {success}",
        extra={"stage": "resolve", "incident_id": incident_id},
    )

    ticket_id = state.get("linear_ticket_identifier") or state.get("linear_ticket_id", "N/A")
    ticket_url = state.get("linear_ticket_url", "")

    resolution_preview = {
        "type": "reporter_resolved",
        "to": state["reporter_email"],
        "subject": f"✅ Resolved: {state['title'][:60]}",
        "body": (
            f"Hello {state['reporter_name']},\n\n"
            f"Great news! The incident you reported has been resolved.\n\n"
            f"Title:  {state['title']}\n"
            f"Ticket: {ticket_id}{(' — ' + ticket_url) if ticket_url else ''}\n\n"
            f"Thank you for your report. If you experience further issues, please submit a new incident.\n\n"
            f"— GaviBot"
        ),
    }

    existing = list(state.get("notification_previews") or [])
    existing.append(resolution_preview)

    return {**state, "reporter_notified": success, "notification_previews": existing}

"""
Notify node: send Slack notifications to team and reporter confirmation.
"""
import asyncio
import concurrent.futures
from app.agent.state import IncidentState
from app.integrations.slack_client import notify_team, notify_reporter_created
from app.integrations.email_client import send_reporter_created
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


def notify_node(state: IncidentState) -> IncidentState:
    incident_id = state["incident_id"]
    logger.info(f"Sending notifications for incident {incident_id}", extra={"stage": "notify", "incident_id": incident_id})

    team_success = _run_async(
        notify_team(
            team=state.get("assigned_team", "backend"),
            incident_id=incident_id,
            title=state["title"],
            severity=state.get("severity_final", "P2"),
            triage_summary=state.get("triage_summary", ""),
            ticket_url=state.get("linear_ticket_url", ""),
            ticket_identifier=state.get("linear_ticket_identifier", ""),
            reporter_name=state["reporter_name"],
            reporter_email=state["reporter_email"],
            affected_components=state.get("affected_components", []),
            recommended_actions=state.get("recommended_actions", []),
        )
    )

    reporter_success = _run_async(
        notify_reporter_created(
            reporter_email=state["reporter_email"],
            reporter_name=state["reporter_name"],
            incident_id=incident_id,
            title=state["title"],
            severity=state.get("severity_final", "P2"),
            ticket_url=state.get("linear_ticket_url", ""),
            ticket_identifier=state.get("linear_ticket_identifier", ""),
        )
    )

    send_reporter_created(
        reporter_email=state["reporter_email"],
        reporter_name=state["reporter_name"],
        title=state["title"],
        severity=state.get("severity_final", "P2"),
        team=state.get("assigned_team", "backend"),
        ticket_id=state.get("linear_ticket_identifier") or state.get("linear_ticket_id", "N/A"),
        ticket_url=state.get("linear_ticket_url", ""),
    )

    if state.get("trace_context"):
        state["trace_context"].span(
            "notify",
            output_data={"team_notified": team_success, "reporter_notified": reporter_success},
        )

    severity = state.get("severity_final", "P2")
    ticket_id = state.get("linear_ticket_identifier") or state.get("linear_ticket_id", "N/A")
    ticket_url = state.get("linear_ticket_url", "")
    team = (state.get("assigned_team") or "backend").capitalize()
    components = ", ".join(state.get("affected_components") or []) or "Unknown"
    actions = "\n".join(f"  • {a}" for a in (state.get("recommended_actions") or [])[:5]) or "  • Review manually"

    reporter_preview = {
        "type": "reporter_created",
        "to": state["reporter_email"],
        "subject": f"[{severity}] Incident received: {state['title'][:60]}",
        "body": (
            f"Hello {state['reporter_name']},\n\n"
            f"Your incident report has been received and automatically triaged by the GaviBot.\n\n"
            f"Title:    {state['title']}\n"
            f"Severity: {severity}\n"
            f"Team:     {team}\n"
            f"Ticket:   {ticket_id}{(' — ' + ticket_url) if ticket_url else ''}\n\n"
            f"The responsible team has been notified and is working on your issue.\n\n"
            f"— GaviBot"
        ),
    }

    team_preview = {
        "type": "team_notification",
        "to": f"{team} Team (via Slack)",
        "subject": f"[{severity}] New Incident: {state['title'][:60]}",
        "body": (
            f"🚨 New Incident Assigned\n\n"
            f"Title:     {state['title']}\n"
            f"Severity:  {severity}\n"
            f"Reporter:  {state['reporter_name']} <{state['reporter_email']}>\n"
            f"Ticket:    {ticket_id}\n\n"
            f"Triage Summary:\n{state.get('triage_summary') or 'N/A'}\n\n"
            f"Affected Components: {components}\n\n"
            f"Recommended Actions:\n{actions}"
        ),
    }

    return {
        **state,
        "team_notified": team_success,
        "reporter_notified": reporter_success,
        "notification_previews": [reporter_preview, team_preview],
    }

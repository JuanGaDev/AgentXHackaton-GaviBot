import os
import httpx
from typing import Optional
from app.observability.logging_config import get_logger

logger = get_logger(__name__)

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

TEAM_WEBHOOKS = {
    "backend": os.getenv("SLACK_WEBHOOK_TEAM_BACKEND", ""),
    "frontend": os.getenv("SLACK_WEBHOOK_TEAM_FRONTEND", ""),
    "payments": os.getenv("SLACK_WEBHOOK_TEAM_PAYMENTS", ""),
    "infrastructure": os.getenv("SLACK_WEBHOOK_TEAM_INFRA", ""),
    "database": os.getenv("SLACK_WEBHOOK_TEAM_BACKEND", ""),
    "unknown": os.getenv("SLACK_WEBHOOK_URL", ""),
}

SEVERITY_COLORS = {
    "P0": "#FF0000",
    "P1": "#FF6600",
    "P2": "#FFA500",
    "P3": "#FFD700",
    "P4": "#00AA00",
}

SEVERITY_EMOJIS = {
    "P0": ":rotating_light:",
    "P1": ":red_circle:",
    "P2": ":large_orange_circle:",
    "P3": ":large_yellow_circle:",
    "P4": ":large_green_circle:",
}


async def _post_to_webhook(webhook_url: str, payload: dict) -> bool:
    if not webhook_url:
        logger.warning("Slack webhook URL not configured")
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, json=payload)
            if response.status_code == 200:
                return True
            logger.error(f"Slack webhook returned {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Slack notification failed: {e}")
        return False


async def notify_team(
    team: str,
    incident_id: str,
    title: str,
    severity: str,
    triage_summary: str,
    ticket_url: str,
    ticket_identifier: str,
    reporter_name: str,
    reporter_email: str,
    affected_components: list[str],
    recommended_actions: list[str],
) -> bool:
    """Send a Slack notification to the assigned engineering team."""
    webhook = TEAM_WEBHOOKS.get(team, "") or SLACK_WEBHOOK_URL
    color = SEVERITY_COLORS.get(severity, "#808080")
    emoji = SEVERITY_EMOJIS.get(severity, ":bell:")

    components_text = ", ".join(affected_components) if affected_components else "Unknown"
    actions_text = "\n".join(f"• {a}" for a in recommended_actions[:5]) if recommended_actions else "• Review manually"

    ticket_link = f"<{ticket_url}|{ticket_identifier}>" if ticket_url else ticket_identifier

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} New Incident: [{severity}] {title[:60]}",
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Severity:*\n{severity}"},
                    {"type": "mrkdwn", "text": f"*Team:*\n{team.capitalize()}"},
                    {"type": "mrkdwn", "text": f"*Reporter:*\n{reporter_name} ({reporter_email})"},
                    {"type": "mrkdwn", "text": f"*Ticket:*\n{ticket_link}"},
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Triage Summary:*\n{triage_summary}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Affected Components:*\n{components_text}"},
                    {"type": "mrkdwn", "text": f"*Recommended Actions:*\n{actions_text}"},
                ]
            },
            {"type": "divider"},
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Incident ID: `{incident_id}` | GaviBot"}
                ]
            }
        ],
        "attachments": [{"color": color}]
    }

    success = await _post_to_webhook(webhook, payload)
    if success:
        logger.info(f"Team {team} notified via Slack for incident {incident_id}")
    return success


async def notify_reporter_resolved(
    reporter_email: str,
    reporter_name: str,
    incident_id: str,
    title: str,
    ticket_url: str,
    ticket_identifier: str,
    resolution_note: Optional[str] = None,
) -> bool:
    """Notify the original reporter that their incident was resolved."""
    webhook = SLACK_WEBHOOK_URL

    ticket_link = f"<{ticket_url}|{ticket_identifier}>" if ticket_url else ticket_identifier
    note_text = f"\n*Resolution Note:* {resolution_note}" if resolution_note else ""

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": ":white_check_mark: Incident Resolved",
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"Hello *{reporter_name}*,\n\n"
                        f"The incident you reported has been resolved.\n\n"
                        f"*Incident:* {title}\n"
                        f"*Ticket:* {ticket_link}"
                        f"{note_text}"
                    )
                }
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Incident ID: `{incident_id}` | Thank you for reporting!"}
                ]
            }
        ]
    }

    success = await _post_to_webhook(webhook, payload)
    if success:
        logger.info(f"Reporter {reporter_email} notified of resolution for incident {incident_id}")
    return success


async def notify_reporter_created(
    reporter_email: str,
    reporter_name: str,
    incident_id: str,
    title: str,
    severity: str,
    ticket_url: str,
    ticket_identifier: str,
) -> bool:
    """Notify the reporter that their ticket was created and team is working on it."""
    webhook = SLACK_WEBHOOK_URL
    emoji = SEVERITY_EMOJIS.get(severity, ":bell:")
    ticket_link = f"<{ticket_url}|{ticket_identifier}>" if ticket_url else ticket_identifier

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{emoji} Incident Received & Triaged"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"Hello *{reporter_name}*,\n\n"
                        f"Your incident report has been received and automatically triaged.\n\n"
                        f"*Title:* {title}\n"
                        f"*Severity:* {severity}\n"
                        f"*Ticket:* {ticket_link}\n\n"
                        f"The responsible team has been notified and is working on it."
                    ),
                },
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Incident ID: `{incident_id}`"}
                ],
            },
        ]
    }

    return await _post_to_webhook(webhook, payload)

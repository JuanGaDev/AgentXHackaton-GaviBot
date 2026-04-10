import os
import resend
from app.observability.logging_config import get_logger

logger = get_logger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_ADDRESS = os.getenv("RESEND_FROM", "GaviBot <onboarding@resend.dev>")


def _is_configured() -> bool:
    return bool(RESEND_API_KEY)


def _send(to: str, subject: str, body: str) -> bool:
    if not _is_configured():
        logger.warning("RESEND_API_KEY not set — skipping email to %s", to)
        return False
    try:
        resend.api_key = RESEND_API_KEY
        resend.Emails.send({
            "from": FROM_ADDRESS,
            "to": [to],
            "subject": subject,
            "text": body,
        })
        logger.info("Email sent to %s: %s", to, subject)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to, e)
        return False


def send_reporter_created(
    reporter_email: str,
    reporter_name: str,
    title: str,
    severity: str,
    team: str,
    ticket_id: str,
    ticket_url: str,
) -> bool:
    subject = f"[{severity}] Incident received: {title[:60]}"
    body = (
        f"Hello {reporter_name},\n\n"
        f"Your incident report has been received and automatically triaged by the GaviBot.\n\n"
        f"Title:    {title}\n"
        f"Severity: {severity}\n"
        f"Team:     {team.capitalize()}\n"
        f"Ticket:   {ticket_id}{(' — ' + ticket_url) if ticket_url else ''}\n\n"
        f"The responsible team has been notified and is working on your issue.\n\n"
        f"— GaviBot"
    )
    return _send(reporter_email, subject, body)


def send_reporter_resolved(
    reporter_email: str,
    reporter_name: str,
    title: str,
    ticket_id: str,
    ticket_url: str,
) -> bool:
    subject = f"✅ Resolved: {title[:60]}"
    body = (
        f"Hello {reporter_name},\n\n"
        f"Great news! The incident you reported has been resolved.\n\n"
        f"Title:  {title}\n"
        f"Ticket: {ticket_id}{(' — ' + ticket_url) if ticket_url else ''}\n\n"
        f"Thank you for your report. If you experience further issues, please submit a new incident.\n\n"
        f"— GaviBot"
    )
    return _send(reporter_email, subject, body)

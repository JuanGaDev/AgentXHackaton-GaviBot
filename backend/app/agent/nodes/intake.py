"""
Intake node: validate and sanitize incident input using guardrails.
"""
from app.agent.state import IncidentState
from app.agent.guardrails import run_guardrails
from app.observability.logging_config import get_logger

logger = get_logger(__name__)


def intake_node(state: IncidentState) -> IncidentState:
    incident_id = state["incident_id"]
    logger.info(f"Intake processing incident {incident_id}", extra={"stage": "intake", "incident_id": incident_id})

    if state.get("trace_context"):
        state["trace_context"].span("intake", input_data={"incident_id": incident_id})

    passed, reason, clean_title, clean_description = run_guardrails(
        title=state["title"],
        description=state["description"],
        reporter_email=state["reporter_email"],
        attachment_paths=state.get("attachment_paths", []),
    )

    if not passed:
        logger.warning(f"Guardrail failed for incident {incident_id}: {reason}")

    return {
        **state,
        "title": clean_title,
        "description": clean_description,
        "guardrail_passed": passed,
        "guardrail_reason": reason if not passed else None,
    }

"""
Route node: determine final team assignment and escalation path.
"""
from app.agent.state import IncidentState
from app.observability.logging_config import get_logger

logger = get_logger(__name__)

VALID_TEAMS = {"backend", "frontend", "payments", "infrastructure", "database", "unknown"}

SEVERITY_ESCALATION = {
    "P0": ["infrastructure", "backend"],
    "P1": ["backend", "payments"],
}


def route_node(state: IncidentState) -> IncidentState:
    incident_id = state["incident_id"]
    assigned_team = state.get("assigned_team", "backend")
    severity = state.get("severity_final", "P2")

    if assigned_team not in VALID_TEAMS:
        assigned_team = "backend"

    # Override for P0: always involve infrastructure
    if severity == "P0" and assigned_team not in {"infrastructure", "payments"}:
        logger.info(f"P0 incident {incident_id}: escalating to infrastructure team")
        assigned_team = "infrastructure"

    logger.info(
        f"Routing incident {incident_id} to team={assigned_team} severity={severity}",
        extra={"stage": "route", "incident_id": incident_id},
    )

    if state.get("trace_context"):
        state["trace_context"].span(
            "route",
            input_data={"team": assigned_team, "severity": severity},
        )

    return {**state, "assigned_team": assigned_team}

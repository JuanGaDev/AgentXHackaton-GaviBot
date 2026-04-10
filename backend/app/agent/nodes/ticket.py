"""
Ticket node: create a Linear issue for the triaged incident.
"""
import asyncio
from app.agent.state import IncidentState
from app.integrations.linear_client import create_ticket
from app.observability.logging_config import get_logger

logger = get_logger(__name__)


def ticket_node(state: IncidentState) -> IncidentState:
    incident_id = state["incident_id"]
    logger.info(f"Creating ticket for incident {incident_id}", extra={"stage": "ticket", "incident_id": incident_id})

    ticket_description = f"""**Reporter:** {state['reporter_name']} ({state['reporter_email']})

**Triage Summary:**
{state.get('triage_summary', '')}

**Root Cause Hint:**
{state.get('root_cause_hint', 'Unknown')}

**Original Description:**
{state['description'][:2000]}
"""

    try:
        result = asyncio.get_event_loop().run_until_complete(
            create_ticket(
                title=state["title"],
                description=ticket_description,
                severity=state.get("severity_final", "P2"),
                team_name=state.get("assigned_team", "backend"),
                incident_id=incident_id,
                affected_components=state.get("affected_components", []),
                recommended_actions=state.get("recommended_actions", []),
            )
        )
    except RuntimeError:
        # Handle case where event loop is already running (inside async context)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                create_ticket(
                    title=state["title"],
                    description=ticket_description,
                    severity=state.get("severity_final", "P2"),
                    team_name=state.get("assigned_team", "backend"),
                    incident_id=incident_id,
                    affected_components=state.get("affected_components", []),
                    recommended_actions=state.get("recommended_actions", []),
                )
            )
            result = future.result()

    ticket_id = result.get("id", "")
    ticket_url = result.get("url", "")
    ticket_identifier = result.get("identifier", "")

    if ticket_id:
        logger.info(
            f"Ticket {ticket_identifier} created for incident {incident_id}",
            extra={"stage": "ticket", "incident_id": incident_id},
        )
    else:
        logger.error(f"Ticket creation failed for incident {incident_id}")

    if state.get("trace_context"):
        state["trace_context"].span(
            "ticket",
            input_data={"incident_id": incident_id},
            output_data={"ticket_id": ticket_id, "ticket_url": ticket_url},
        )

    return {
        **state,
        "linear_ticket_id": ticket_id,
        "linear_ticket_url": ticket_url,
        "linear_ticket_identifier": ticket_identifier,
    }

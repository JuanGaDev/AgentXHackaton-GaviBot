"""
LangGraph workflow definition for the SRE incident pipeline.

Flow:
  intake -> [guardrail check] -> triage -> route -> ticket -> notify -> END
                    |
                  FAIL -> END (error)
"""
from langgraph.graph import StateGraph, END
from app.agent.state import IncidentState
from app.agent.nodes.intake import intake_node
from app.agent.nodes.triage import triage_node
from app.agent.nodes.route import route_node
from app.agent.nodes.ticket import ticket_node
from app.agent.nodes.notify import notify_node
from app.observability.logging_config import get_logger

logger = get_logger(__name__)


def _should_continue_after_intake(state: IncidentState) -> str:
    """Route to triage if guardrails pass, otherwise end with error."""
    if state.get("guardrail_passed", False):
        return "triage"
    return END


def build_graph() -> StateGraph:
    workflow = StateGraph(IncidentState)

    workflow.add_node("intake", intake_node)
    workflow.add_node("triage", triage_node)
    workflow.add_node("route", route_node)
    workflow.add_node("ticket", ticket_node)
    workflow.add_node("notify", notify_node)

    workflow.set_entry_point("intake")

    workflow.add_conditional_edges(
        "intake",
        _should_continue_after_intake,
        {
            "triage": "triage",
            END: END,
        },
    )

    workflow.add_edge("triage", "route")
    workflow.add_edge("route", "ticket")
    workflow.add_edge("ticket", "notify")
    workflow.add_edge("notify", END)

    return workflow


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph().compile()
    return _compiled_graph


async def run_incident_pipeline(
    incident_id: str,
    title: str,
    description: str,
    reporter_name: str,
    reporter_email: str,
    severity_hint: str | None = None,
    attachment_paths: list[str] | None = None,
    log_content: str | None = None,
) -> IncidentState:
    """
    Run the full incident triage pipeline and return final state.
    """
    from app.observability.langfuse_setup import TraceContext

    trace = TraceContext(incident_id=incident_id).start()

    initial_state: IncidentState = {
        "incident_id": incident_id,
        "title": title,
        "description": description,
        "reporter_name": reporter_name,
        "reporter_email": reporter_email,
        "severity_hint": severity_hint,
        "attachment_paths": attachment_paths or [],
        "log_content": log_content,
        "guardrail_passed": False,
        "guardrail_reason": None,
        "severity_final": None,
        "assigned_team": None,
        "affected_components": [],
        "root_cause_hint": None,
        "triage_summary": None,
        "triage_confidence": None,
        "recommended_actions": [],
        "linear_ticket_id": None,
        "linear_ticket_url": None,
        "linear_ticket_identifier": None,
        "team_notified": False,
        "reporter_notified": False,
        "error": None,
        "trace_context": trace,
    }

    graph = get_graph()

    try:
        logger.info(f"Starting pipeline for incident {incident_id}")
        final_state = await graph.ainvoke(initial_state)
        logger.info(f"Pipeline complete for incident {incident_id}")
        return final_state
    except Exception as e:
        logger.error(f"Pipeline failed for incident {incident_id}: {e}")
        trace.end()
        return {**initial_state, "error": str(e)}

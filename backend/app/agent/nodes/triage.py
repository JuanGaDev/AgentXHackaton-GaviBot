"""
Triage node: multimodal analysis with Gemini + RAG over Solidus codebase.
"""
from app.agent.state import IncidentState
from app.integrations.gemini_client import analyze_incident
from app.rag.retriever import retrieve_context
from app.observability.logging_config import get_logger

logger = get_logger(__name__)


def triage_node(state: IncidentState) -> IncidentState:
    incident_id = state["incident_id"]
    logger.info(f"Triaging incident {incident_id}", extra={"stage": "triage", "incident_id": incident_id})

    # Build query for RAG
    query = f"{state['title']} {state['description']}"

    # Retrieve relevant Solidus code context
    code_context = retrieve_context(query, n_results=5)
    if code_context:
        logger.info(f"RAG retrieved {len(code_context)} chars of context for {incident_id}")
    else:
        logger.info(f"No RAG context found for {incident_id}")

    # Get image attachments only (not logs)
    attachment_paths = state.get("attachment_paths", [])
    image_paths = [
        p for p in attachment_paths
        if any(p.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"])
    ]

    incident_text = f"""Title: {state['title']}

Reporter: {state['reporter_name']} ({state['reporter_email']})

Description:
{state['description']}

Severity Hint from Reporter: {state.get('severity_hint', 'Not specified')}
"""

    # Call Gemini multimodal
    result = analyze_incident(
        text=incident_text,
        code_context=code_context,
        image_paths=image_paths if image_paths else None,
        log_content=state.get("log_content"),
    )

    if state.get("trace_context"):
        state["trace_context"].generation(
            name="triage",
            model="gemini-2.0-flash",
            prompt=incident_text[:500],
            completion=str(result)[:500],
        )

    logger.info(
        f"Triage complete for {incident_id}: severity={result.get('severity')} team={result.get('assigned_team')}",
        extra={"stage": "triage", "incident_id": incident_id},
    )

    return {
        **state,
        "severity_final": result.get("severity", "P2"),
        "assigned_team": result.get("assigned_team", "backend"),
        "affected_components": result.get("affected_components", []),
        "root_cause_hint": result.get("root_cause_hint", ""),
        "triage_summary": result.get("triage_summary", ""),
        "triage_confidence": result.get("confidence", "low"),
        "recommended_actions": result.get("recommended_actions", []),
    }

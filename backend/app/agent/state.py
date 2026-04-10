"""
LangGraph agent state schema for the SRE incident pipeline.
"""
from typing import Optional, Annotated
from typing_extensions import TypedDict


class IncidentState(TypedDict):
    # Input fields
    incident_id: str
    title: str
    description: str
    reporter_name: str
    reporter_email: str
    severity_hint: Optional[str]
    attachment_paths: list[str]
    log_content: Optional[str]

    # Guardrail results
    guardrail_passed: bool
    guardrail_reason: Optional[str]

    # Triage results
    severity_final: Optional[str]
    assigned_team: Optional[str]
    affected_components: list[str]
    root_cause_hint: Optional[str]
    triage_summary: Optional[str]
    triage_confidence: Optional[str]
    recommended_actions: list[str]

    # Ticket
    linear_ticket_id: Optional[str]
    linear_ticket_url: Optional[str]
    linear_ticket_identifier: Optional[str]

    # Notifications
    team_notified: bool
    reporter_notified: bool
    notification_previews: Optional[list[dict]]

    # Error tracking
    error: Optional[str]

    # Observability
    trace_context: Optional[object]

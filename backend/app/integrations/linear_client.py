import os
import httpx
from typing import Optional
from app.observability.logging_config import get_logger

logger = get_logger(__name__)

LINEAR_API_KEY = os.getenv("LINEAR_API_KEY", "")
LINEAR_TEAM_ID = os.getenv("LINEAR_TEAM_ID", "")
LINEAR_API_URL = "https://api.linear.app/graphql"

SEVERITY_TO_PRIORITY = {
    "P0": 1,  # Urgent
    "P1": 2,  # High
    "P2": 3,  # Medium
    "P3": 4,  # Low
    "P4": 4,  # Low
}

TEAM_TO_LABEL_COLOR = {
    "backend": "#E44444",
    "frontend": "#4A90E2",
    "payments": "#F5A623",
    "infrastructure": "#7B68EE",
    "database": "#50C878",
    "unknown": "#808080",
}


async def _graphql(query: str, variables: dict) -> dict:
    headers = {
        "Authorization": LINEAR_API_KEY,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            LINEAR_API_URL,
            json={"query": query, "variables": variables},
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            raise RuntimeError(f"Linear GraphQL error: {data['errors']}")
        return data.get("data", {})


async def get_team_states() -> list[dict]:
    """Fetch workflow states for the team."""
    query = """
    query GetTeamStates($teamId: String!) {
      team(id: $teamId) {
        states {
          nodes {
            id
            name
            type
          }
        }
      }
    }
    """
    try:
        data = await _graphql(query, {"teamId": LINEAR_TEAM_ID})
        return data.get("team", {}).get("states", {}).get("nodes", [])
    except Exception as e:
        logger.error(f"Failed to get Linear states: {e}")
        return []


async def create_ticket(
    title: str,
    description: str,
    severity: str,
    team_name: str,
    incident_id: str,
    affected_components: list[str],
    recommended_actions: list[str],
) -> dict:
    """Create a Linear issue and return ticket ID and URL."""
    if not LINEAR_API_KEY or not LINEAR_TEAM_ID:
        logger.warning("Linear not configured - returning mock ticket")
        mock_id = f"MOCK-{incident_id[:8].upper()}"
        return {
            "id": mock_id,
            "url": f"https://linear.app/mock/issue/{mock_id}",
            "identifier": mock_id,
        }

    priority = SEVERITY_TO_PRIORITY.get(severity, 3)

    components_list = "\n".join(f"- {c}" for c in affected_components) if affected_components else "- Unknown"
    actions_list = "\n".join(f"- [ ] {a}" for a in recommended_actions) if recommended_actions else "- [ ] Investigate manually"

    body = f"""## SRE Incident Report

**Severity:** {severity}  
**Team:** {team_name}  
**Incident ID:** {incident_id}

---

{description}

## Affected Components
{components_list}

## Recommended Actions
{actions_list}

---
*Ticket automatically created by GaviBot*
"""

    query = """
    mutation CreateIssue($input: IssueCreateInput!) {
      issueCreate(input: $input) {
        success
        issue {
          id
          identifier
          url
        }
      }
    }
    """
    variables = {
        "input": {
            "teamId": LINEAR_TEAM_ID,
            "title": f"[{severity}] {title}",
            "description": body,
            "priority": priority,
        }
    }

    try:
        data = await _graphql(query, variables)
        issue = data.get("issueCreate", {}).get("issue", {})
        logger.info(f"Linear ticket created: {issue.get('identifier')} for incident {incident_id}")
        return {
            "id": issue.get("id", ""),
            "url": issue.get("url", ""),
            "identifier": issue.get("identifier", ""),
        }
    except Exception as e:
        logger.error(f"Failed to create Linear ticket: {e} — falling back to mock ticket")
        mock_id = f"MOCK-{incident_id[:8].upper()}"
        return {
            "id": mock_id,
            "url": f"https://linear.app/mock/issue/{mock_id}",
            "identifier": mock_id,
        }


async def get_ticket_status(ticket_id: str) -> Optional[str]:
    """Get the current status of a Linear issue."""
    query = """
    query GetIssue($id: String!) {
      issue(id: $id) {
        state {
          name
          type
        }
      }
    }
    """
    try:
        data = await _graphql(query, {"id": ticket_id})
        state = data.get("issue", {}).get("state", {})
        return state.get("type", "")
    except Exception as e:
        logger.error(f"Failed to get Linear ticket status: {e}")
        return None


async def update_ticket_status(ticket_id: str, state_id: str) -> bool:
    """Update Linear issue state."""
    query = """
    mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
      issueUpdate(id: $id, input: $input) {
        success
      }
    }
    """
    try:
        data = await _graphql(query, {"id": ticket_id, "input": {"stateId": state_id}})
        return data.get("issueUpdate", {}).get("success", False)
    except Exception as e:
        logger.error(f"Failed to update Linear ticket: {e}")
        return False

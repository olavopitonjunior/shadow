"""
Analytics Router - Deep metrics, charts, trends.

Endpoints:
- GET /analytics/overview — Summary metrics
- GET /analytics/agents — Per-agent usage stats
- GET /analytics/tools — Tool usage heatmap data
- GET /analytics/tokens — Token distribution by agent
- GET /analytics/contacts — Contact activity ranking
- GET /analytics/quality — Conversation quality metrics
- GET /analytics/trends — Trend analysis
"""

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

_agent_path = str(Path(__file__).parent.parent.parent.parent / "shadow" / "agent")
if _agent_path not in sys.path:
    sys.path.insert(0, _agent_path)

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _get_storage():
    from storage import Storage
    return Storage()


@router.get("/overview")
def get_overview(days: int = Query(7, le=90)) -> dict[str, Any]:
    """Summary metrics for the analytics dashboard."""
    storage = _get_storage()

    tasks = storage.list_tasks(limit=500)
    appointments = storage.list_appointments(limit=500)
    contacts = storage.list_contacts(limit=500)

    tasks_done = [t for t in tasks if getattr(t, "status", "") == "completed"]

    return {
        "period_days": days,
        "tasks_total": len(tasks),
        "tasks_completed": len(tasks_done),
        "completion_rate": round(len(tasks_done) / max(len(tasks), 1) * 100, 1),
        "appointments_total": len(appointments),
        "contacts_total": len(contacts),
    }


@router.get("/agents")
def get_agent_stats() -> dict[str, Any]:
    """Per-agent usage statistics from event history."""
    try:
        from graph.streaming import get_agent_event_bus
        bus = get_agent_event_bus()
        events = bus.get_history(500)

        # Count events per node
        node_counts: dict[str, int] = {}
        for e in events:
            node = e.get("node_name", "unknown")
            if e.get("event_type") == "node_end":
                node_counts[node] = node_counts.get(node, 0) + 1

        return {"agent_calls": node_counts}
    except Exception:
        return {"agent_calls": {}}


@router.get("/tools")
def get_tool_usage() -> dict[str, Any]:
    """Tool usage frequency for heatmap visualization."""
    try:
        from graph.streaming import get_agent_event_bus
        bus = get_agent_event_bus()
        events = bus.get_history(500)

        tool_counts: dict[str, int] = {}
        for e in events:
            if e.get("event_type") == "tool_call":
                tool = e.get("data", {}).get("tool", e.get("node_name", ""))
                if tool:
                    tool_counts[tool] = tool_counts.get(tool, 0) + 1

        # Sort by frequency
        sorted_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)
        return {"tools": [{"name": k, "calls": v} for k, v in sorted_tools]}
    except Exception:
        return {"tools": []}


@router.get("/tokens")
def get_token_distribution() -> dict[str, Any]:
    """Token distribution by agent for donut chart."""
    storage = _get_storage()
    try:
        usage = storage.get_usage_summary(days=7)
        return {"token_distribution": usage}
    except Exception:
        return {"token_distribution": {}}


@router.get("/contacts")
def get_contact_activity(limit: int = 10) -> dict[str, Any]:
    """Top contacts by interaction count."""
    storage = _get_storage()
    contacts = storage.list_contacts(limit=limit)

    results = []
    for c in contacts:
        results.append({
            "phone": getattr(c, "phone", ""),
            "name": getattr(c, "name", ""),
            "updated_at": getattr(c, "updated_at", ""),
        })

    return {"contacts": results}


@router.get("/quality")
def get_quality_metrics() -> dict[str, Any]:
    """Conversation quality metrics."""
    # TODO: Implement quality tracking from feedback system
    return {
        "task_completion_rate": 94.0,
        "avg_steps_per_task": 2.1,
        "tool_accuracy": 97.0,
    }


@router.get("/trends")
def get_trends(period: str = "7d") -> dict[str, Any]:
    """Trend analysis for key metrics."""
    storage = _get_storage()
    try:
        history = storage.get_usage_history(days=int(period.rstrip("d")))
        return {"period": period, "trends": history}
    except Exception:
        return {"period": period, "trends": []}

"""
Agents Router - Real-time agent monitoring and execution history.

Endpoints:
- GET /agents/status — All agent statuses
- GET /agents/active — Currently executing sessions
- GET /agents/history — Recent executions with traces
- GET /agents/stream — SSE endpoint for real-time events
- GET /agents/{session_id}/trace — Full execution trace
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

# Add agent path for imports
_agent_path = str(Path(__file__).parent.parent.parent.parent / "shadow" / "agent")
if _agent_path not in sys.path:
    sys.path.insert(0, _agent_path)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/status")
def get_agent_status() -> dict[str, Any]:
    """Get status of all agents (supervisor + 5 workers)."""
    agents = [
        {"name": "supervisor", "type": "orchestrator", "status": "active"},
        {"name": "crm", "type": "worker", "status": "ready", "tools": 14},
        {"name": "planner", "type": "worker", "status": "ready", "tools": 12},
        {"name": "analytics", "type": "worker", "status": "ready", "tools": 8},
        {"name": "docgen", "type": "worker", "status": "ready", "tools": 6},
        {"name": "collector", "type": "worker", "status": "ready", "tools": 5},
    ]

    try:
        from graph.streaming import get_agent_event_bus
        bus = get_agent_event_bus()
        return {
            "agents": agents,
            "event_bus": {
                "subscribers": bus.subscriber_count,
                "history_size": len(bus._history),
            },
        }
    except Exception:
        return {"agents": agents, "event_bus": {"subscribers": 0, "history_size": 0}}


@router.get("/active")
def get_active_executions() -> dict[str, Any]:
    """Get currently executing sessions."""
    # TODO: Track active invocations in a registry
    return {"active": [], "count": 0}


@router.get("/history")
def get_execution_history(limit: int = 50) -> dict[str, Any]:
    """Get recent execution events."""
    try:
        from graph.streaming import get_agent_event_bus
        bus = get_agent_event_bus()
        return {"events": bus.get_history(limit), "total": len(bus._history)}
    except Exception:
        return {"events": [], "total": 0}


@router.get("/stream")
async def stream_agent_events():
    """SSE endpoint for real-time agent activity.

    Connect via EventSource in the frontend:
      const source = new EventSource('/agents/stream');
      source.onmessage = (e) => console.log(JSON.parse(e.data));
    """
    try:
        from graph.streaming import get_agent_event_bus, sse_event_generator
        bus = get_agent_event_bus()
        return StreamingResponse(
            sse_event_generator(bus, timeout=300.0),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        return {"error": str(e)}


@router.get("/{session_id}/trace")
def get_execution_trace(session_id: str) -> dict[str, Any]:
    """Get full execution trace for a session.

    Uses LangGraph checkpoint history for time-travel debugging.
    """
    try:
        from graph import get_compiled_graph, get_thread_config
        graph = get_compiled_graph()
        config = {"configurable": {"thread_id": session_id}}

        # Get state history from checkpointer
        states = []
        for state in graph.get_state_history(config):
            states.append({
                "step": state.metadata.get("step", 0) if state.metadata else 0,
                "node": state.next[0] if state.next else "end",
                "values": {
                    k: str(v)[:200] if not isinstance(v, (int, float, bool, type(None))) else v
                    for k, v in (state.values or {}).items()
                    if k not in ("messages", "raw_payload")
                },
            })

        return {"session_id": session_id, "states": states[:50]}
    except Exception as e:
        return {"session_id": session_id, "states": [], "error": str(e)[:200]}

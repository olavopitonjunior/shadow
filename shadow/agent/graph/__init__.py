"""
Shadow Graph - LangGraph orchestration for multi-agent system.

Entry point: run_graph() processes a message through the supervisor graph.

Architecture:
- Supervisor (orchestrator) with three-tier routing
- 5 worker subgraphs: CRM, Planner, Analytics, DocGen, Collector
- 4-layer RAG knowledge base
- SqliteSaver checkpointing per thread
- Thread safety via per-thread locking
- Tenant isolation via owner_id:chat_id thread IDs
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any

from graph.state import ShadowState, default_shadow_state
from graph.builder import build_shadow_graph, get_default_checkpointer

# ── Singleton graph instance ──
_compiled_graph = None
_graph_lock = threading.Lock()

# ── Per-thread concurrency locks ──
_thread_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)


def get_compiled_graph():
    """Get or create the singleton compiled graph."""
    global _compiled_graph
    if _compiled_graph is None:
        with _graph_lock:
            if _compiled_graph is None:
                checkpointer = get_default_checkpointer()
                _compiled_graph = build_shadow_graph(checkpointer=checkpointer)
    return _compiled_graph


def get_thread_config(owner_id: str | None, chat_id: str | None) -> dict:
    """Create tenant-isolated thread config.

    Thread ID format: owner_id:chat_id
    This ensures no cross-tenant checkpoint leaks.
    """
    owner = owner_id or "default"
    chat = chat_id or "unknown"
    thread_id = f"{owner}:{chat}"
    return {"configurable": {"thread_id": thread_id}}


def run_graph(
    payload: dict[str, Any],
    owner_id: str | None = None,
) -> dict[str, Any]:
    """Process a message through the Shadow LangGraph.

    This is the main entry point, called from main.py when
    SHADOW_USE_LANGGRAPH=true.

    Emits AgentEvents to the SSE bus for real-time dashboard monitoring.

    Args:
        payload: Raw message payload from webhook
        owner_id: Owner phone for tenant isolation

    Returns:
        Dict with reply, intent, actions, session_id
    """
    from datetime import datetime, timezone
    from uuid import uuid4

    graph = get_compiled_graph()

    # Determine thread ID for checkpointing
    chat_id = (
        payload.get("chat_id")
        or (payload.get("metadata") or {}).get("remoteJid")
        or payload.get("phone")
        or "unknown"
    )
    config = get_thread_config(owner_id, chat_id)
    thread_id = config["configurable"]["thread_id"]

    # Get event bus for dashboard streaming
    try:
        from graph.streaming import get_agent_event_bus, AgentEvent
        event_bus = get_agent_event_bus()
    except Exception:
        event_bus = None

    def _emit(event_type: str, node_name: str, data: dict | None = None):
        if event_bus:
            event_bus.emit(AgentEvent(
                event_id=str(uuid4())[:8],
                event_type=event_type,
                node_name=node_name,
                thread_id=thread_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                data=data or {},
            ))

    # Per-thread lock prevents concurrent invocations on same thread
    with _thread_locks[thread_id]:
        _emit("node_start", "graph", {"body": (payload.get("body") or "")[:100]})

        # Build input state
        input_state = {
            **default_shadow_state(),
            "raw_payload": payload,
            "is_owner": payload.get("is_owner", False),
        }

        try:
            result = graph.invoke(input_state, config=config)
            _emit("node_end", "graph", {"has_reply": bool(result.get("reply"))})
        except Exception as e:
            _emit("error", "graph", {"error": str(e)[:200]})
            print(f"[graph] Invocation error: {e}")
            return {
                "reply": "Desculpe, ocorreu um erro interno. Tente novamente.",
                "intent": "error",
                "actions": [],
                "session_id": None,
                "error": str(e)[:200],
            }

    # Emit step events from the execution trace
    for step in result.get("steps", []):
        node = step.get("node", "unknown")
        _emit("node_end", node, {k: v for k, v in step.items() if k != "node"})

    return {
        "reply": result.get("reply"),
        "intent": result.get("intent") or result.get("route") or "graph",
        "actions": [
            r.get("worker_name", "unknown")
            for r in result.get("worker_results", [])
            if r.get("status") == "ok"
        ],
        "session_id": result.get("session_id"),
        "tokens": {
            "input": result.get("total_input_tokens", 0),
            "output": result.get("total_output_tokens", 0),
        },
    }


__all__ = [
    "run_graph",
    "get_compiled_graph",
    "get_thread_config",
    "ShadowState",
]

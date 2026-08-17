"""
Graph Builder - Constructs and compiles the Shadow LangGraph.

Assembles the supervisor graph with:
- Three-tier routing (fast-path → keyword → LLM)
- Worker subgraph nodes (CRM, Planner, Analytics, DocGen, Collector)
- Quality check loop with re-delegation
- Checkpointing per thread (tenant-isolated)
- Retry policies on LLM nodes
"""

from __future__ import annotations

import os
from pathlib import Path

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver  # langgraph-checkpoint-sqlite

from graph.state import ShadowState
from graph.nodes.intake import intake_node
from graph.nodes.router import route_message
from graph.nodes.fast_path import fast_path_node
from graph.nodes.rag import rag_retrieve_node
from graph.nodes.synthesize import synthesize_node, check_quality
from graph.nodes.respond import respond_node
from graph.supervisor import supervisor_think_node, supervisor_route


def _make_worker_node(worker_name: str):
    """Create a node function that delegates to a worker subgraph.

    The node converts ShadowState → WorkerState, runs the subgraph,
    and converts the result back to a WorkerResult in ShadowState.
    """
    def worker_node(state: ShadowState) -> dict:
        task = state.get("worker_task") or state.get("body", "")

        try:
            from graph.workers.base import build_worker_subgraph
            from langchain_core.messages import HumanMessage

            subgraph = build_worker_subgraph(worker_name)

            # Build WorkerState input
            worker_input = {
                "messages": [HumanMessage(content=task)],
                "worker_name": worker_name,
                "task_description": task,
                "tools_used": [],
                "iteration": 0,
                "local_context": {
                    "sender_phone": state.get("sender_phone"),
                    "sender_name": state.get("sender_name"),
                    "chat_id": state.get("chat_id"),
                    "session_id": state.get("session_id"),
                },
                "status": "running",
                "error": None,
            }

            result = subgraph.invoke(worker_input)

            # Extract final response from last AI message
            display_text = ""
            messages = result.get("messages", [])
            for msg in reversed(messages):
                if hasattr(msg, "content") and msg.content:
                    display_text = msg.content
                    break

            return {
                "worker_results": [{
                    "worker_name": worker_name,
                    "status": result.get("status", "ok"),
                    "data": {},
                    "display_text": display_text or "Processado.",
                    "tools_used": result.get("tools_used", []),
                    "tokens_used": 0,
                }],
                "steps": [{"node": worker_name, "iterations": result.get("iteration", 0)}],
            }
        except Exception as e:
            print(f"[{worker_name}] Worker error: {e}")
            return {
                "worker_results": [{
                    "worker_name": worker_name,
                    "status": "error",
                    "data": {},
                    "display_text": f"Erro no agente {worker_name}: {str(e)[:100]}",
                    "tools_used": [],
                    "tokens_used": 0,
                }],
                "steps": [{"node": worker_name, "error": str(e)[:100]}],
            }

    worker_node.__name__ = f"{worker_name}_worker"
    return worker_node


def build_shadow_graph(
    checkpointer: SqliteSaver | None = None,
) -> StateGraph:
    """Build and compile the Shadow supervisor graph.

    Phase 1: Workers are passthrough to existing ReActAgent.
    Phase 2: Workers become proper LangGraph subgraphs.
    """
    graph = StateGraph(ShadowState)

    # ── Nodes ──
    graph.add_node("intake", intake_node)
    graph.add_node("fast_path", fast_path_node)
    graph.add_node("rag_retrieve", rag_retrieve_node)
    graph.add_node("supervisor_think", supervisor_think_node)

    # Worker nodes (LangGraph subgraphs with own ReAct loops)
    for worker_name in ["crm", "planner", "analytics", "docgen", "collector"]:
        graph.add_node(worker_name, _make_worker_node(worker_name))

    graph.add_node("synthesize", synthesize_node)
    graph.add_node("respond", respond_node)

    # ── Edges ──
    graph.add_edge(START, "intake")

    # Three-tier routing after intake
    graph.add_conditional_edges("intake", route_message, {
        "fast_path": "fast_path",
        "planner": "planner",
        "crm": "crm",
        "analytics": "analytics",
        "docgen": "docgen",
        "collector": "collector",
        "supervisor_think": "rag_retrieve",
    })

    # Fast-path goes directly to respond
    graph.add_edge("fast_path", "respond")

    # RAG → supervisor think
    graph.add_edge("rag_retrieve", "supervisor_think")

    # Supervisor routes to workers or responds directly
    graph.add_conditional_edges("supervisor_think", supervisor_route, {
        "crm": "crm",
        "planner": "planner",
        "analytics": "analytics",
        "docgen": "docgen",
        "collector": "collector",
        "respond": "respond",
    })

    # All workers → synthesize → quality check
    for worker_name in ["crm", "planner", "analytics", "docgen", "collector"]:
        graph.add_edge(worker_name, "synthesize")

    # Quality check: respond or re-delegate
    graph.add_conditional_edges("synthesize", check_quality, {
        "respond": "respond",
        "supervisor_think": "rag_retrieve",
    })

    graph.add_edge("respond", END)

    # ── Compile ──
    compile_kwargs = {}
    if checkpointer:
        compile_kwargs["checkpointer"] = checkpointer

    return graph.compile(**compile_kwargs)


def get_default_checkpointer() -> SqliteSaver | None:
    """Create the default SqliteSaver for conversation persistence.

    Uses a separate DB file to avoid lock contention with shadow.db.
    """
    try:
        db_path = Path(__file__).parent.parent / "data" / "shadow_graph.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return SqliteSaver.from_conn_string(str(db_path))
    except Exception as e:
        print(f"[graph] Failed to create checkpointer: {e}")
        return None

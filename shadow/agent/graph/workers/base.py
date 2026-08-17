"""
Base Worker Subgraph Factory.

Creates a LangGraph ReAct subgraph for any worker, given its name and tools.
Each worker runs its own think-act loop with tool access and retry policy.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from graph.state import WorkerState, WorkerResult
from graph.adapters.tool_adapter import get_worker_tools, make_tool_context_from_state


# Worker-specific system prompts
WORKER_PROMPTS: dict[str, str] = {
    "crm": (
        "You are the CRM agent. You manage contacts, relationships, and memories. "
        "Use tools to get, create, update, and search contacts. Store important facts "
        "about contacts as memories. Always respond in Portuguese (pt-BR)."
    ),
    "planner": (
        "You are the Planner agent. You manage tasks, appointments, and reminders. "
        "Create tasks with clear titles and due dates. Schedule appointments with "
        "proper times. Set reminders when asked. Always respond in Portuguese (pt-BR)."
    ),
    "analytics": (
        "You are the Analytics agent. You generate reports, summaries, and insights "
        "from tasks, appointments, contacts, and usage data. Present data clearly "
        "with numbers and organized lists. Always respond in Portuguese (pt-BR)."
    ),
    "docgen": (
        "You are the Document Generation agent. You create proposals, contracts, "
        "and formatted documents. Gather contact and project data before generating. "
        "Always respond in Portuguese (pt-BR)."
    ),
    "collector": (
        "You are the Data Collector agent. You import contacts and conversation data "
        "from WhatsApp via Z-API. Sync contacts to the CRM and store relevant memories. "
        "Always respond in Portuguese (pt-BR)."
    ),
}

MAX_WORKER_ITERATIONS = 5


def _should_continue(state: WorkerState) -> str:
    """Decide if the worker should continue or stop."""
    messages = state.get("messages", [])
    if not messages:
        return END

    last = messages[-1]
    # If the last message is an AIMessage with tool calls, continue
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tools"

    return END


def _make_worker_reason_node(worker_name: str):
    """Create the reasoning (LLM) node for a worker."""

    def reason_node(state: WorkerState) -> dict[str, Any]:
        from providers import get_provider

        system = WORKER_PROMPTS.get(worker_name, "You are a helpful assistant.")
        task = state.get("task_description", "")
        iteration = state.get("iteration", 0)

        if iteration >= MAX_WORKER_ITERATIONS:
            return {
                "messages": [AIMessage(content="Atingi o limite de iteracoes. Retornando o que tenho ate agora.")],
                "iteration": iteration,
                "status": "partial",
            }

        # Get tools for this worker
        context = make_tool_context_from_state(state)
        tools = get_worker_tools(worker_name, context)
        tool_schemas = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.args if hasattr(t, "args") else {"type": "object", "properties": {}},
                },
            }
            for t in tools
        ]

        # Build conversation for provider
        provider = get_provider()
        messages_for_llm = []

        for msg in state.get("messages", []):
            if isinstance(msg, HumanMessage):
                messages_for_llm.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                messages_for_llm.append({"role": "assistant", "content": msg.content})

        if not messages_for_llm:
            messages_for_llm.append({"role": "user", "content": task})

        # Retry with provider fallback (3 attempts, backoff 2x)
        response = None
        last_error = None
        for attempt in range(3):
            try:
                response = provider.chat(
                    messages=messages_for_llm,
                    tools=tool_schemas if tool_schemas else None,
                    system=system,
                    max_tokens=1000,
                    temperature=0.3,
                )
                break  # Success
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                if "rate_limit" in error_str or "429" in error_str:
                    # Rate limited — try fallback provider
                    import time as _time
                    _time.sleep(2 ** attempt)  # Backoff: 1s, 2s, 4s
                    try:
                        provider = get_provider(provider_name="gemini")
                    except Exception:
                        pass  # Keep current provider
                elif attempt < 2:
                    import time as _time
                    _time.sleep(1)  # Brief pause before retry
                else:
                    break  # Give up

        if response is None:
            return {
                "messages": [AIMessage(content=f"Erro apos 3 tentativas: {str(last_error)[:150]}")],
                "iteration": iteration + 1,
                "status": "error",
                "error": str(last_error)[:200],
            }

        # Convert response to LangChain message
        if response.has_tool_calls and response.tool_calls:
            tool_calls = [
                {
                    "id": tc.id or f"call_{i}",
                    "name": tc.name,
                    "args": tc.arguments,
                }
                for i, tc in enumerate(response.tool_calls)
            ]
            ai_msg = AIMessage(content=response.content or "", tool_calls=tool_calls)
        else:
            ai_msg = AIMessage(content=response.content or "")

        return {
            "messages": [ai_msg],
            "iteration": iteration + 1,
            "tools_used": state.get("tools_used", []),
        }

    reason_node.__name__ = f"{worker_name}_reason"
    return reason_node


def build_worker_subgraph(worker_name: str) -> StateGraph:
    """Build a worker subgraph with ReAct loop.

    Each worker has:
    - reason node (LLM call with worker-specific prompt + tools)
    - tools node (ToolNode executing tool calls)
    - loop: reason → tools → reason → ... → END
    """
    graph = StateGraph(WorkerState)

    # Get tools for ToolNode
    tools = get_worker_tools(worker_name)

    # Nodes
    graph.add_node("reason", _make_worker_reason_node(worker_name))
    if tools:
        graph.add_node("tools", ToolNode(tools))

    # Edges
    graph.add_edge(START, "reason")

    if tools:
        graph.add_conditional_edges("reason", _should_continue, {
            "tools": "tools",
            END: END,
        })
        graph.add_edge("tools", "reason")
    else:
        graph.add_edge("reason", END)

    return graph.compile()

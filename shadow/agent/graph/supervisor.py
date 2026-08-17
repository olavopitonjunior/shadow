"""
Supervisor think node - LLM-based routing for ambiguous messages.

Only invoked for Tier 3 (ambiguous/multimodal/multi-step) messages.
Tier 1 (fast-path) and Tier 2 (keyword) are handled by router.py.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.types import Send

from graph.state import ShadowState


SUPERVISOR_SYSTEM = """You are Shadow's supervisor agent. You coordinate specialized workers.

AVAILABLE WORKERS:
- crm: Contact management, relationship data, CRM operations, memories
- planner: Tasks, appointments, reminders, scheduling
- analytics: Dashboards, reports, data analysis, insights, summaries
- docgen: Proposals, contracts, formatted documents, PDFs
- collector: Fetch WhatsApp chat history, group data, import contacts

KNOWLEDGE CONTEXT (from RAG):
{knowledge_context}

RULES:
1. If you can answer directly (greetings, simple questions) → use "respond" tool
2. If you need a worker → use "delegate" tool with worker name and task description
3. If you need multiple workers → list them all in one "delegate" call (they run in parallel)
4. Always respond in Portuguese (pt-BR)
5. Be concise and helpful
"""


def supervisor_think_node(state: ShadowState) -> dict[str, Any]:
    """LLM decides: answer directly or delegate to workers.

    Uses the existing LiteLLM provider for multi-model support.
    Returns state update with either a direct reply or worker routing info.
    """
    from providers import get_provider

    body = state.get("body", "")
    knowledge = state.get("knowledge_context", [])
    multimodal = state.get("multimodal_context")

    # Build knowledge context string
    knowledge_str = ""
    if knowledge:
        knowledge_str = "\n".join(
            f"- [{k.get('source', '?')}] {k.get('text', k.get('content', ''))[:200]}"
            for k in knowledge[:5]
        )
    else:
        knowledge_str = "(nenhum contexto relevante encontrado)"

    system = SUPERVISOR_SYSTEM.format(knowledge_context=knowledge_str)

    # Build user message
    user_content = body
    if multimodal:
        user_content = f"{body}\n\n[Conteúdo multimídia processado]: {multimodal[:500]}"

    # Define tools for the supervisor
    tools = [
        {
            "type": "function",
            "function": {
                "name": "delegate",
                "description": "Delegate task to one or more specialized workers",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "workers": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "agent": {
                                        "type": "string",
                                        "enum": ["crm", "planner", "analytics", "docgen", "collector"],
                                    },
                                    "task": {
                                        "type": "string",
                                        "description": "Specific task description for this worker",
                                    },
                                },
                                "required": ["agent", "task"],
                            },
                            "description": "List of workers to delegate to",
                        },
                    },
                    "required": ["workers"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "respond",
                "description": "Respond directly to the user without delegating",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Response message to the user",
                        },
                    },
                    "required": ["message"],
                },
            },
        },
    ]

    try:
        provider = get_provider()
        messages = [
            {"role": "user", "content": user_content},
        ]

        response = provider.chat(
            messages=messages,
            tools=tools,
            system=system,
            max_tokens=500,
            temperature=0.3,
        )

        # Track tokens
        input_tokens = response.input_tokens or 0
        output_tokens = response.output_tokens or 0

        # Parse response
        if response.has_tool_calls and response.tool_calls:
            tc = response.tool_calls[0]

            if tc.name == "respond":
                # Direct reply
                reply_text = tc.arguments.get("message", response.content or "")
                return {
                    "reply": reply_text,
                    "route": "direct_reply",
                    "total_input_tokens": input_tokens,
                    "total_output_tokens": output_tokens,
                    "steps": [{"node": "supervisor_think", "action": "direct_reply"}],
                }

            if tc.name == "delegate":
                workers = tc.arguments.get("workers", [])
                if workers:
                    valid_agents = {"crm", "planner", "analytics", "docgen", "collector"}
                    workers = [w for w in workers if w.get("agent") in valid_agents]

                    if len(workers) == 1:
                        # Single worker — direct routing
                        first = workers[0]
                        return {
                            "route": first["agent"],
                            "worker_task": first["task"],
                            "active_workers": [first["agent"]],
                            "retry_count": state.get("retry_count", 0) + 1,
                            "total_input_tokens": input_tokens,
                            "total_output_tokens": output_tokens,
                            "steps": [{"node": "supervisor_think", "action": "delegate", "workers": [first["agent"]]}],
                        }
                    elif len(workers) > 1:
                        # Multi-worker fan-out via Send() API
                        # Store multi-worker info in state, return "fan_out" route
                        return {
                            "route": "fan_out",
                            "fan_out_workers": workers,
                            "active_workers": [w["agent"] for w in workers],
                            "retry_count": state.get("retry_count", 0) + 1,
                            "total_input_tokens": input_tokens,
                            "total_output_tokens": output_tokens,
                            "steps": [{"node": "supervisor_think", "action": "fan_out", "workers": [w["agent"] for w in workers]}],
                        }

        # No tool calls — treat content as direct reply
        return {
            "reply": response.content or "Desculpe, não entendi. Pode reformular?",
            "route": "direct_reply",
            "total_input_tokens": input_tokens,
            "total_output_tokens": output_tokens,
            "steps": [{"node": "supervisor_think", "action": "direct_reply_fallback"}],
        }

    except Exception as e:
        print(f"[supervisor] LLM error: {e}")
        return {
            "reply": "Desculpe, estou com dificuldade no momento. Tente novamente.",
            "route": "direct_reply",
            "error": str(e)[:200],
            "steps": [{"node": "supervisor_think", "error": str(e)[:100]}],
        }


def supervisor_route(state: ShadowState) -> str | list[Send]:
    """Route based on supervisor's decision.

    Returns the name of the next node, or a list of Send() for parallel fan-out.
    """
    route = state.get("route")

    if route == "direct_reply":
        return "respond"

    if route == "fan_out":
        # Multi-worker parallel execution via Send API
        workers = state.get("fan_out_workers", [])
        if workers:
            sends = []
            for w in workers:
                agent = w["agent"]
                if agent in {"crm", "planner", "analytics", "docgen", "collector"}:
                    # Send creates a parallel branch for each worker
                    sends.append(Send(agent, {
                        **state,
                        "worker_task": w["task"],
                    }))
            if sends:
                return sends
        # Fallback if no valid workers
        return "respond"

    if route in {"crm", "planner", "analytics", "docgen", "collector"}:
        return route

    # Fallback
    return "respond"

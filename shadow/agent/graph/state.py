"""
Shadow Graph State - Typed state schemas for LangGraph orchestration.

ShadowState: Parent graph state (supervisor + routing + workers)
WorkerState: Shared state for all worker subgraphs
WorkerResult: Structured output from worker execution
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class ShadowState:
    """Parent graph state for the supervisor orchestrator.

    Fields are grouped by lifecycle phase:
    - Inbound: set once at intake
    - RAG: populated by knowledge retrieval
    - Routing: set by three-tier router
    - Workers: populated during execution
    - Output: final response
    - Observability: tracing and metrics
    """

    # Use __annotations__ for TypedDict-style usage with LangGraph
    pass


# LangGraph requires TypedDict, not class — use functional form
from typing import TypedDict


class ShadowState(TypedDict):
    # ── Message history (LangGraph accumulator) ──
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Inbound context (set once at intake) ──
    raw_payload: dict[str, Any]
    body: str
    multimodal_context: str | None
    sender_phone: str | None
    sender_name: str | None
    chat_id: str | None
    chat_type: Literal["direct", "group"]
    is_owner: bool
    session_id: str | None
    media_type: str | None
    media_url: str | None

    # ── RAG context ──
    knowledge_context: list[dict[str, Any]]

    # ── Routing ──
    route: str | None
    intent: str | None

    # ── Supervisor ──
    worker_task: str | None
    active_workers: list[str]
    fan_out_workers: list[dict[str, str]]
    retry_count: int

    # ── Worker results (reducer: append for safe parallel merge) ──
    worker_results: Annotated[list[dict[str, Any]], operator.add]

    # ── Output ──
    reply: str | None
    attachments: list[dict[str, Any]]

    # ── Observability ──
    steps: Annotated[list[dict[str, Any]], operator.add]
    total_input_tokens: int
    total_output_tokens: int
    error: str | None


class WorkerState(TypedDict):
    """Shared state for all worker subgraphs.

    Each worker operates on its own copy of this state.
    Results are returned to the parent via worker_results reducer.
    """
    messages: Annotated[list[BaseMessage], add_messages]
    worker_name: str
    task_description: str
    tools_used: list[str]
    iteration: int
    local_context: dict[str, Any]
    status: Literal["running", "ok", "error", "partial"]
    error: str | None


@dataclass
class WorkerResult:
    """Structured output from a worker execution."""

    worker_name: str
    status: Literal["ok", "error", "partial"]
    data: dict[str, Any] = field(default_factory=dict)
    display_text: str = ""
    tools_used: list[str] = field(default_factory=list)
    tokens_used: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_name": self.worker_name,
            "status": self.status,
            "data": self.data,
            "display_text": self.display_text,
            "tools_used": self.tools_used,
            "tokens_used": self.tokens_used,
        }


def default_shadow_state() -> dict[str, Any]:
    """Create a default ShadowState dict with all fields initialized."""
    return {
        "messages": [],
        "raw_payload": {},
        "body": "",
        "multimodal_context": None,
        "sender_phone": None,
        "sender_name": None,
        "chat_id": None,
        "chat_type": "direct",
        "is_owner": False,
        "session_id": None,
        "media_type": None,
        "media_url": None,
        "knowledge_context": [],
        "route": None,
        "intent": None,
        "worker_task": None,
        "active_workers": [],
        "fan_out_workers": [],
        "retry_count": 0,
        "worker_results": [],
        "reply": None,
        "attachments": [],
        "steps": [],
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "error": None,
    }

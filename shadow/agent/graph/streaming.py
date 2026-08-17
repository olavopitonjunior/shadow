"""
Streaming - SSE endpoint for real-time agent monitoring + event bus bridge.

Provides:
1. AgentEventBus: Captures LangGraph node events and broadcasts to subscribers
2. SSE endpoint for admin dashboard (real-time agent activity visualization)
3. Async graph invocation with event streaming
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Callable
from uuid import uuid4

from graph.state import ShadowState, default_shadow_state


@dataclass
class AgentEvent:
    """A single event from the agent graph execution."""

    event_id: str
    event_type: str  # "node_start", "node_end", "tool_call", "tool_result", "error"
    node_name: str
    thread_id: str
    timestamp: str
    duration_ms: int = 0
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        return f"data: {json.dumps(self.to_dict())}\n\n"


class AgentEventBus:
    """Broadcast agent events to multiple subscribers.

    Used by the SSE endpoint to stream events to the admin dashboard.
    """

    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []
        self._history: list[AgentEvent] = []
        self._max_history = 500

    def subscribe(self) -> asyncio.Queue:
        """Create a new subscriber queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove a subscriber."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def emit(self, event: AgentEvent) -> None:
        """Broadcast event to all subscribers."""
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        dead_queues = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead_queues.append(queue)

        for q in dead_queues:
            self._subscribers.remove(q)

    def get_history(self, limit: int = 50) -> list[dict]:
        """Get recent event history."""
        return [e.to_dict() for e in self._history[-limit:]]

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Singleton
_event_bus: AgentEventBus | None = None


def get_agent_event_bus() -> AgentEventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = AgentEventBus()
    return _event_bus


async def stream_graph_events(
    graph,
    input_state: dict[str, Any],
    config: dict[str, Any],
    event_bus: AgentEventBus | None = None,
) -> dict[str, Any]:
    """Run graph with event streaming.

    Emits AgentEvents for each node start/end to the event bus.
    Returns the final graph result.

    This is used instead of graph.invoke() when we want real-time
    monitoring in the admin dashboard.
    """
    bus = event_bus or get_agent_event_bus()
    thread_id = config.get("configurable", {}).get("thread_id", "unknown")
    final_result = None

    try:
        async for event in graph.astream_events(
            input_state, config=config, version="v2"
        ):
            event_type = event.get("event", "")
            event_name = event.get("name", "")

            if event_type == "on_chain_start":
                bus.emit(AgentEvent(
                    event_id=str(uuid4())[:8],
                    event_type="node_start",
                    node_name=event_name,
                    thread_id=thread_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    data={"tags": event.get("tags", [])},
                ))

            elif event_type == "on_chain_end":
                output = event.get("data", {}).get("output", {})
                bus.emit(AgentEvent(
                    event_id=str(uuid4())[:8],
                    event_type="node_end",
                    node_name=event_name,
                    thread_id=thread_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    data={
                        "has_reply": bool(output.get("reply") if isinstance(output, dict) else False),
                    },
                ))

                # Capture final result from respond node
                if event_name == "respond" and isinstance(output, dict):
                    final_result = output

            elif event_type == "on_tool_start":
                bus.emit(AgentEvent(
                    event_id=str(uuid4())[:8],
                    event_type="tool_call",
                    node_name=event_name,
                    thread_id=thread_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    data={"tool": event_name},
                ))

            elif event_type == "on_tool_end":
                bus.emit(AgentEvent(
                    event_id=str(uuid4())[:8],
                    event_type="tool_result",
                    node_name=event_name,
                    thread_id=thread_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ))

    except Exception as e:
        bus.emit(AgentEvent(
            event_id=str(uuid4())[:8],
            event_type="error",
            node_name="graph",
            thread_id=thread_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            data={"error": str(e)[:200]},
        ))

    return final_result or {}


async def sse_event_generator(
    event_bus: AgentEventBus,
    timeout: float = 300.0,
) -> AsyncGenerator[str, None]:
    """Generate SSE events for the admin dashboard.

    Yields events as Server-Sent Event formatted strings.
    Keeps connection alive with periodic heartbeats.
    """
    queue = event_bus.subscribe()
    start = time.time()

    try:
        while time.time() - start < timeout:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield event.to_sse()
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                yield f"data: {json.dumps({'event_type': 'heartbeat'})}\n\n"
    finally:
        event_bus.unsubscribe(queue)

"""Synchronous message bus for decoupled channel-agent communication.

Adapted from nanobot/bus/queue.py.
Uses threading + queue.Queue (sync) instead of asyncio.Queue.
"""

import queue
import threading
from typing import Callable

from .events import InboundMessage, OutboundMessage


class MessageBus:
    """
    Sync message bus that decouples channels from the agent.

    Channels publish outbound messages to the bus. A dispatcher thread
    routes them to registered subscribers (e.g., gateway send callback).
    """

    def __init__(self) -> None:
        self.inbound: queue.Queue[InboundMessage] = queue.Queue()
        self.outbound: queue.Queue[OutboundMessage] = queue.Queue()
        self._subscribers: dict[str, list[Callable[[OutboundMessage], None]]] = {}
        self._running = False
        self._dispatcher_thread: threading.Thread | None = None

    def publish_inbound(self, msg: InboundMessage) -> None:
        """Publish a message from a channel to the agent."""
        self.inbound.put(msg)

    def consume_inbound(self, timeout: float | None = None) -> InboundMessage | None:
        """Consume the next inbound message (blocks until available or timeout)."""
        try:
            return self.inbound.get(timeout=timeout)
        except queue.Empty:
            return None

    def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent/scheduler/subagent to channels."""
        self.outbound.put(msg)

    def consume_outbound(self, timeout: float | None = None) -> OutboundMessage | None:
        """Consume the next outbound message."""
        try:
            return self.outbound.get(timeout=timeout)
        except queue.Empty:
            return None

    def subscribe_outbound(
        self,
        channel: str,
        callback: Callable[[OutboundMessage], None],
    ) -> None:
        """Subscribe to outbound messages for a specific channel."""
        if channel not in self._subscribers:
            self._subscribers[channel] = []
        self._subscribers[channel].append(callback)

    def start_dispatcher(self) -> None:
        """Start the outbound dispatcher in a background thread."""
        if self._running:
            return
        self._running = True
        self._dispatcher_thread = threading.Thread(
            target=self._dispatch_loop,
            name="bus-dispatcher",
            daemon=True,
        )
        self._dispatcher_thread.start()
        print("[bus] Dispatcher started")

    def stop(self) -> None:
        """Stop the dispatcher."""
        self._running = False
        if self._dispatcher_thread:
            self._dispatcher_thread.join(timeout=2)
            self._dispatcher_thread = None
        print("[bus] Dispatcher stopped")

    def _dispatch_loop(self) -> None:
        """Dispatch outbound messages to subscribers."""
        while self._running:
            try:
                msg = self.outbound.get(timeout=1.0)
                subscribers = self._subscribers.get(msg.channel, [])
                for callback in subscribers:
                    try:
                        callback(msg)
                    except Exception as e:
                        print(f"[bus] Error dispatching to {msg.channel}: {e}")
            except queue.Empty:
                continue

    @property
    def inbound_size(self) -> int:
        return self.inbound.qsize()

    @property
    def outbound_size(self) -> int:
        return self.outbound.qsize()


# Singleton
_message_bus: MessageBus | None = None


def get_message_bus() -> MessageBus:
    """Get or create the message bus singleton."""
    global _message_bus
    if _message_bus is None:
        _message_bus = MessageBus()
    return _message_bus


def reset_message_bus() -> None:
    """Reset the singleton (useful for testing)."""
    global _message_bus
    if _message_bus:
        _message_bus.stop()
    _message_bus = None

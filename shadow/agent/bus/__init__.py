"""Message bus for decoupled communication.

Provides InboundMessage/OutboundMessage events and a sync MessageBus
with subscriber-based dispatch.
"""

from .events import InboundMessage, OutboundMessage
from .queue import MessageBus, get_message_bus, reset_message_bus

__all__ = [
    "InboundMessage",
    "OutboundMessage",
    "MessageBus",
    "get_message_bus",
    "reset_message_bus",
]

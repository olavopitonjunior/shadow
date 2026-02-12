"""Message bus events for Shadow agent.

Adapted from nanobot/bus/events.py with Shadow-specific fields.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class InboundMessage:
    """A message coming into the agent from any channel."""
    channel: str          # "whatsapp", "system", "scheduler"
    sender_id: str        # phone E.164 or "system"
    chat_id: str          # WhatsApp JID or internal ID
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    # Shadow-specific fields
    is_owner: bool = False
    sender_name: str | None = None
    chat_type: str = "direct"  # "direct" | "group"
    monitor_only: bool = False
    media_url: str | None = None
    media_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def session_key(self) -> str:
        """Unique key for session routing."""
        return f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    """A message going out from the agent to a channel."""
    channel: str          # "whatsapp"
    chat_id: str          # recipient JID or "owner"
    content: str
    reply_to: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

"""Channel adapter base types and protocol.

Defines the ChannelAdapter Protocol and normalized message types
that abstract away differences between Evolution API and Meta Cloud API.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class ChannelIncoming:
    """Normalized incoming message from any channel adapter."""

    external_id: str  # wamid or Evolution msg id (for dedup)
    phone: str  # E.164: +5511999999999
    display_name: str | None
    text: str
    timestamp: int  # Unix timestamp
    media_url: str | None = None
    media_type: str | None = None  # image, audio, video, document
    raw: dict = field(default_factory=dict)


@dataclass
class SendResult:
    """Result of sending a message via channel adapter."""

    success: bool
    message_id: str | None = None
    error: str | None = None
    raw: dict = field(default_factory=dict)


@runtime_checkable
class ChannelAdapter(Protocol):
    """Protocol for WhatsApp channel adapters (Evolution API, Meta Cloud API)."""

    adapter_type: str  # "evolution" | "meta_cloud"

    async def send_text(self, phone: str, text: str) -> SendResult:
        """Send a text message to a phone number."""
        ...

    async def send_template(
        self, phone: str, template: str, params: list[str]
    ) -> SendResult:
        """Send a template message (required for Meta outside 24h window)."""
        ...

    async def send_media(
        self, phone: str, media_url: str, caption: str | None = None
    ) -> SendResult:
        """Send a media message (image, audio, video, document)."""
        ...

    async def mark_read(self, message_id: str) -> None:
        """Mark a message as read."""
        ...

    def parse_webhook(self, body: dict, headers: dict) -> ChannelIncoming | None:
        """Parse incoming webhook payload into normalized ChannelIncoming."""
        ...

    def verify_webhook(self, params: dict) -> str | None:
        """Verify webhook challenge (Meta Cloud API). Returns challenge string or None."""
        ...


def normalize_phone(phone: str) -> str:
    """Normalize phone to E.164 format (+country code + number).

    Handles:
    - JID format: 5511999999999@s.whatsapp.net -> +5511999999999
    - Raw digits: 5511999999999 -> +5511999999999
    - Already E.164: +5511999999999 -> +5511999999999
    """
    # Strip JID suffix
    if "@" in phone:
        phone = phone.split("@")[0]

    # Remove non-digit characters except leading +
    digits = "".join(c for c in phone if c.isdigit())

    if not digits:
        return phone

    return f"+{digits}"


def verify_hmac_signature(
    payload: bytes, signature: str, secret: str
) -> bool:
    """Verify HMAC-SHA256 signature for Meta Cloud API webhooks."""
    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    sig_value = signature.removeprefix("sha256=")
    return hmac.compare_digest(expected, sig_value)

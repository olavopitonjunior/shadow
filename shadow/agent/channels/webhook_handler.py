"""Webhook handler for channel messages.

Routes incoming webhooks to the correct adapter, handles dedup,
and dispatches to message processing.
"""

from __future__ import annotations

from channels.base import ChannelAdapter, ChannelIncoming


class WebhookHandler:
    """Routes webhook payloads to the correct adapter and handles dedup."""

    def __init__(self, adapter: ChannelAdapter, storage=None) -> None:
        self.adapter = adapter
        self.storage = storage
        self._seen_ids: set[str] = set()
        self._max_seen = 10_000

    def handle_verification(self, params: dict) -> str | None:
        """Handle webhook verification (GET request from Meta)."""
        return self.adapter.verify_webhook(params)

    def parse_and_dedup(self, body: dict, headers: dict) -> ChannelIncoming | None:
        """Parse webhook and deduplicate by external_id.

        Returns None if:
        - Payload is not a valid message
        - Message was already processed (dedup)
        """
        incoming = self.adapter.parse_webhook(body, headers)
        if incoming is None:
            return None

        # Dedup by external_id
        if incoming.external_id:
            # Check DB-level dedup if storage available
            if self.storage and hasattr(self.storage, "get_channel_message_by_external_id"):
                existing = self.storage.get_channel_message_by_external_id(incoming.external_id)
                if existing:
                    return None

            # In-memory dedup fallback
            if incoming.external_id in self._seen_ids:
                return None
            self._seen_ids.add(incoming.external_id)

            # Prevent memory leak
            if len(self._seen_ids) > self._max_seen:
                # Remove oldest half
                to_remove = list(self._seen_ids)[: self._max_seen // 2]
                for item in to_remove:
                    self._seen_ids.discard(item)

        return incoming

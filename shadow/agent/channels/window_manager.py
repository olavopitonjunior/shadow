"""24-hour conversation window manager.

Meta Cloud API requires approved templates for messages sent outside
the 24-hour conversation window. Evolution API has no such restriction.

This manager tracks window state and decides whether to send plain text
or fall back to a template.
"""

from __future__ import annotations

from datetime import datetime, timezone

from channels.base import ChannelAdapter, SendResult


WINDOW_DURATION_SECONDS = 24 * 60 * 60  # 24 hours


class WindowManager:
    """Manages 24h conversation windows for Meta Cloud API."""

    def __init__(self, adapter: ChannelAdapter, storage) -> None:
        self.adapter = adapter
        self.storage = storage

    def can_send_free(self, phone: str) -> bool:
        """Check if we can send a free-form message (within 24h window).

        Evolution API: Always True (no window restriction).
        Meta Cloud API: True only if user messaged within last 24h.
        """
        if self.adapter.adapter_type == "evolution":
            return True

        user = self.storage.get_channel_user_by_phone(phone)
        if not user:
            return False

        last_window = user.get("last_window_opened_at")
        if not last_window:
            return False

        try:
            opened = datetime.fromisoformat(last_window.replace("Z", "+00:00"))
            elapsed = (datetime.now(timezone.utc) - opened).total_seconds()
            return elapsed < WINDOW_DURATION_SECONDS
        except (ValueError, TypeError):
            return False

    async def send_smart(
        self,
        phone: str,
        text: str,
        fallback_template: str,
        params: list[str],
    ) -> SendResult:
        """Send text if within window, otherwise use template.

        Args:
            phone: E.164 phone number
            text: Free-form text to send if window is open
            fallback_template: Template name to use if window is closed
            params: Template parameters ({{1}}, {{2}}, etc.)
        """
        if self.can_send_free(phone):
            return await self.adapter.send_text(phone, text)
        return await self.adapter.send_template(phone, fallback_template, params)

    async def send_text_or_skip(self, phone: str, text: str) -> SendResult | None:
        """Send text only if within window. Skip otherwise (no template fallback)."""
        if self.can_send_free(phone):
            return await self.adapter.send_text(phone, text)
        return None

"""
Suggestion Sender - Sends suggestions to the Shadow group.

This module handles sending suggestions with rate limiting
and batch processing.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from .types import (
    Suggestion,
    SuggestionBatch,
    SuggestionConfig,
    SuggestionPriority,
    SuggestionStatus,
    RateLimitState,
)
from .formatter import format_single_suggestion, format_suggestion_batch


class RateLimiter:
    """
    Simple rate limiter for suggestion sending.

    Tracks messages per time window to avoid overwhelming users.
    """

    def __init__(self, max_per_window: int = 5, window_seconds: int = 600):
        """
        Initialize rate limiter.

        Args:
            max_per_window: Maximum messages per window
            window_seconds: Window duration in seconds
        """
        self.max_per_window = max_per_window
        self.window_seconds = window_seconds
        self.timestamps: list[datetime] = []

    def can_send(self) -> bool:
        """Check if we can send another message."""
        self._cleanup()
        return len(self.timestamps) < self.max_per_window

    def record(self) -> None:
        """Record a sent message."""
        self.timestamps.append(datetime.now(timezone.utc))

    def _cleanup(self) -> None:
        """Remove timestamps outside the window."""
        cutoff = datetime.now(timezone.utc).timestamp() - self.window_seconds
        self.timestamps = [
            ts for ts in self.timestamps
            if ts.timestamp() > cutoff
        ]

    @property
    def remaining(self) -> int:
        """Number of messages remaining in window."""
        self._cleanup()
        return max(0, self.max_per_window - len(self.timestamps))


class SuggestionSender:
    """
    Sends suggestions to the Shadow group.

    Handles:
    - Rate limiting (max N per time window)
    - Daily limits (max N per day)
    - Batch processing
    - Message formatting
    """

    def __init__(
        self,
        gateway_url: str,
        storage: Any,
        max_per_window: int = 5,
        window_seconds: int = 600,
    ):
        """
        Initialize sender.

        Args:
            gateway_url: URL of the Shadow gateway (e.g., http://localhost:18790)
            storage: Storage instance
            max_per_window: Max messages per time window
            window_seconds: Time window in seconds
        """
        self.gateway_url = gateway_url.rstrip("/")
        self.storage = storage
        self.rate_limiter = RateLimiter(max_per_window, window_seconds)

    async def send_pending(
        self,
        owner_id: str,
        config: SuggestionConfig | None = None,
    ) -> int:
        """
        Send pending suggestions for an owner.

        Respects both window rate limits and daily limits.

        Args:
            owner_id: Owner's phone number
            config: Suggestion configuration

        Returns:
            Number of suggestions sent
        """
        if config is None:
            settings = self.storage.get_user_settings(owner_id)
            config = SuggestionConfig.from_settings(settings)

        if not config.enabled:
            return 0

        # Check daily limit
        daily_count = self.storage.get_suggestion_daily_count(owner_id)
        remaining_today = config.max_per_day - daily_count.get("sent_count", 0)
        if remaining_today <= 0:
            print(f"[sender] Daily limit reached for {owner_id[:8]}")
            return 0

        # Expire old suggestions first
        self.storage.expire_old_suggestions(owner_id)

        # Get pending suggestions
        # First, send high-priority ones individually
        high_priority = self.storage.get_pending_suggestions(
            owner_id=owner_id,
            min_priority=SuggestionPriority.HIGH.value,
            limit=min(5, remaining_today),
        )

        sent_count = 0

        # Send high-priority immediately
        for suggestion_dict in high_priority:
            if not self.rate_limiter.can_send():
                print(f"[sender] Rate limit reached, stopping")
                break

            suggestion = Suggestion.from_dict(suggestion_dict)
            success = await self._send_single(suggestion, config)
            if success:
                sent_count += 1
                remaining_today -= 1
                if remaining_today <= 0:
                    break

        # Batch medium-priority suggestions
        if remaining_today > 0 and self.rate_limiter.can_send():
            normal_priority = self.storage.get_pending_suggestions(
                owner_id=owner_id,
                min_priority=SuggestionPriority.NORMAL.value,
                status="pending",
                limit=min(10, remaining_today),
            )

            # Filter out already-sent high priority ones
            high_ids = {s.get("id") for s in high_priority}
            normal_priority = [s for s in normal_priority if s.get("id") not in high_ids]

            if normal_priority:
                batch = SuggestionBatch(
                    batch_id=str(uuid.uuid4()),
                    owner_id=owner_id,
                    suggestions=[Suggestion.from_dict(s) for s in normal_priority],
                )
                batch_sent = await self._send_batch(batch, config)
                if batch_sent:
                    sent_count += len(batch.suggestions)

        print(f"[sender] Sent {sent_count} suggestions for {owner_id[:8]}")
        return sent_count

    async def _send_single(
        self,
        suggestion: Suggestion,
        config: SuggestionConfig,
    ) -> bool:
        """Send a single suggestion."""
        settings = self.storage.get_user_settings(suggestion.owner_id)
        use_emojis = settings.get("use_emojis", True)

        message = format_single_suggestion(suggestion, use_emojis=use_emojis)

        success = await self._send_message(message)
        if success:
            self.storage.mark_suggestion_sent(suggestion.id)
            self.storage.increment_suggestion_count(suggestion.owner_id, "sent")
            self.rate_limiter.record()
            return True

        return False

    async def _send_batch(
        self,
        batch: SuggestionBatch,
        config: SuggestionConfig,
    ) -> bool:
        """Send a batch of suggestions as one message."""
        if not batch.suggestions:
            return False

        settings = self.storage.get_user_settings(batch.owner_id)
        use_emojis = settings.get("use_emojis", True)

        message = format_suggestion_batch(batch, use_emojis=use_emojis)

        success = await self._send_message(message)
        if success:
            for suggestion in batch.suggestions:
                self.storage.mark_suggestion_sent(suggestion.id)
                self.storage.increment_suggestion_count(suggestion.owner_id, "sent")
            self.rate_limiter.record()
            return True

        return False

    async def _send_message(self, text: str) -> bool:
        """
        Send a message via the gateway.

        Args:
            text: Message text to send

        Returns:
            True if successful
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.gateway_url}/send",
                    json={"text": text},
                )

                if response.status_code == 200:
                    return True

                print(f"[sender] Gateway returned {response.status_code}: {response.text[:100]}")
                return False

        except httpx.TimeoutException:
            print(f"[sender] Gateway timeout")
            return False
        except Exception as e:
            print(f"[sender] Error sending message: {e}")
            return False

    async def send_immediate(
        self,
        suggestion: Suggestion,
    ) -> bool:
        """
        Send a single suggestion immediately (bypass batching).

        Used for urgent suggestions.

        Args:
            suggestion: Suggestion to send

        Returns:
            True if successful
        """
        # Check daily limit
        daily_count = self.storage.get_suggestion_daily_count(suggestion.owner_id)
        settings = self.storage.get_user_settings(suggestion.owner_id)
        config = SuggestionConfig.from_settings(settings)

        if daily_count.get("sent_count", 0) >= config.max_per_day:
            print(f"[sender] Daily limit reached, cannot send immediate")
            return False

        if not self.rate_limiter.can_send():
            print(f"[sender] Rate limit reached, cannot send immediate")
            return False

        return await self._send_single(suggestion, config)


# Singleton for scheduler integration
_sender: SuggestionSender | None = None


def get_suggestion_sender(gateway_url: str | None = None, storage: Any = None) -> SuggestionSender:
    """
    Get or create the suggestion sender singleton.

    Args:
        gateway_url: Gateway URL (required on first call)
        storage: Storage instance (required on first call)

    Returns:
        SuggestionSender instance
    """
    global _sender

    if _sender is None:
        if gateway_url is None or storage is None:
            raise ValueError("gateway_url and storage required on first call")
        _sender = SuggestionSender(gateway_url, storage)

    return _sender


def reset_suggestion_sender() -> None:
    """Reset the singleton (useful for testing)."""
    global _sender
    _sender = None

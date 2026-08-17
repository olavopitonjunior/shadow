"""
Z-API REST Client - Low-level HTTP client for WhatsApp data collection.

Handles authentication, rate limiting, and all Z-API endpoints.
Used by both the gateway (send/receive) and the Collector agent (data mining).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx


class ZAPIRateLimiter:
    """Simple rate limiter for Z-API requests (15 req/min default)."""

    def __init__(self, max_requests: int = 15, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: list[float] = []

    def acquire(self) -> float:
        """Wait if needed and return wait time in seconds."""
        now = time.time()
        cutoff = now - self.window_seconds
        self._timestamps = [t for t in self._timestamps if t > cutoff]

        if len(self._timestamps) >= self.max_requests:
            wait = self._timestamps[0] - cutoff
            return max(0, wait)

        self._timestamps.append(now)
        return 0


class ZAPIClient:
    """Z-API REST client for WhatsApp operations.

    Endpoints: https://api.z-api.io/instances/{instance_id}/token/{token}/...

    Usage:
        client = ZAPIClient(instance_id="abc123", token="secret")
        chats = await client.get_chats()
        messages = await client.get_messages("+5511999887766", amount=50)
        await client.send_text("+5511999887766", "Hello!")
    """

    def __init__(
        self,
        instance_id: str,
        token: str,
        base_url: str = "https://api.z-api.io",
        timeout: float = 30.0,
        max_requests_per_min: int = 15,
    ):
        self.instance_id = instance_id
        self.token = token
        self.base_url = f"{base_url}/instances/{instance_id}/token/{token}"
        self.timeout = timeout
        self._limiter = ZAPIRateLimiter(max_requests_per_min, 60)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def _request(
        self, method: str, endpoint: str, json: dict | None = None
    ) -> dict[str, Any]:
        """Make a rate-limited request to Z-API."""
        wait = self._limiter.acquire()
        if wait > 0:
            await asyncio.sleep(wait)

        client = await self._get_client()
        url = f"{self.base_url}{endpoint}"

        if method == "GET":
            resp = await client.get(url)
        else:
            resp = await client.post(url, json=json or {})

        resp.raise_for_status()
        return resp.json()

    async def _get(self, endpoint: str) -> Any:
        return await self._request("GET", endpoint)

    async def _post(self, endpoint: str, payload: dict) -> Any:
        return await self._request("POST", endpoint, json=payload)

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Messaging ──

    async def send_text(self, phone: str, message: str) -> dict:
        """Send a text message."""
        return await self._post("/send-text", {
            "phone": phone,
            "message": message,
        })

    async def send_image(self, phone: str, image_url: str, caption: str = "") -> dict:
        """Send an image message."""
        return await self._post("/send-message-image", {
            "phone": phone,
            "image": image_url,
            "caption": caption,
        })

    async def send_document(self, phone: str, doc_url: str, filename: str) -> dict:
        """Send a document."""
        return await self._post("/send-message-document", {
            "phone": phone,
            "document": doc_url,
            "fileName": filename,
        })

    async def send_audio(self, phone: str, audio_url: str) -> dict:
        """Send an audio message."""
        return await self._post("/send-message-audio", {
            "phone": phone,
            "audio": audio_url,
        })

    # ── Data Collection ──

    async def get_chats(self) -> list[dict]:
        """Get all active chats."""
        return await self._get("/chats")

    async def get_messages(self, phone: str, amount: int = 50) -> list[dict]:
        """Get message history from a specific chat."""
        return await self._get(f"/chat-messages/{phone}?amount={amount}")

    async def get_contacts(self) -> list[dict]:
        """Get all WhatsApp contacts."""
        return await self._get("/contacts")

    async def get_contact(self, phone: str) -> dict:
        """Get a specific contact."""
        return await self._get(f"/contacts/{phone}")

    async def get_groups(self) -> list[dict]:
        """Get all groups."""
        return await self._get("/groups")

    async def get_group_metadata(self, group_id: str) -> dict:
        """Get group info and participants."""
        return await self._post("/group-metadata", {"groupId": group_id})

    # ── Instance Status ──

    async def get_status(self) -> dict:
        """Get instance connection status."""
        return await self._get("/status")

    async def get_device_info(self) -> dict:
        """Get connected device info."""
        return await self._get("/device")

    async def get_me(self) -> dict:
        """Get instance data."""
        return await self._get("/me")

    # ── Chat Management ──

    async def mark_read(self, phone: str) -> dict:
        """Mark chat as read."""
        return await self._post("/read-message", {"phone": phone})

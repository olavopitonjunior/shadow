"""Evolution API adapter for WhatsApp channel.

Evolution API is an open-source WhatsApp API that runs as a Docker container.
It provides a REST API for sending messages and webhooks for receiving them.

Docs: https://doc.evolution-api.com/
"""

from __future__ import annotations

import time

import httpx

from channels.base import ChannelAdapter, ChannelIncoming, SendResult, normalize_phone


class EvolutionAdapter:
    """ChannelAdapter implementation for Evolution API."""

    adapter_type: str = "evolution"

    def __init__(
        self,
        api_url: str,
        api_key: str,
        instance: str,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.instance = instance
        self._client = httpx.AsyncClient(
            base_url=self.api_url,
            headers={"apikey": self.api_key},
            timeout=15,
        )

    async def send_text(self, phone: str, text: str) -> SendResult:
        """Send text message via Evolution API."""
        # Evolution expects phone without + prefix
        number = phone.lstrip("+")
        try:
            resp = await self._client.post(
                f"/message/sendText/{self.instance}",
                json={
                    "number": number,
                    "text": text,
                },
            )
            data = resp.json()
            if resp.status_code == 200 or resp.status_code == 201:
                msg_id = data.get("key", {}).get("id", "")
                return SendResult(success=True, message_id=msg_id, raw=data)
            return SendResult(success=False, error=data.get("message", str(data)), raw=data)
        except Exception as e:
            return SendResult(success=False, error=str(e))

    async def send_template(
        self, phone: str, template: str, params: list[str]
    ) -> SendResult:
        """Evolution API has no template restriction - send as plain text."""
        # Evolution doesn't enforce 24h window, so templates are just text
        text = template
        for i, param in enumerate(params, 1):
            text = text.replace(f"{{{{{i}}}}}", param)
        return await self.send_text(phone, text)

    async def send_media(
        self, phone: str, media_url: str, caption: str | None = None
    ) -> SendResult:
        """Send media message via Evolution API."""
        number = phone.lstrip("+")
        try:
            resp = await self._client.post(
                f"/message/sendMedia/{self.instance}",
                json={
                    "number": number,
                    "mediatype": "image",
                    "media": media_url,
                    "caption": caption or "",
                },
            )
            data = resp.json()
            if resp.status_code in (200, 201):
                msg_id = data.get("key", {}).get("id", "")
                return SendResult(success=True, message_id=msg_id, raw=data)
            return SendResult(success=False, error=data.get("message", str(data)), raw=data)
        except Exception as e:
            return SendResult(success=False, error=str(e))

    async def mark_read(self, message_id: str) -> None:
        """Mark message as read via Evolution API."""
        try:
            await self._client.put(
                f"/chat/markMessageAsRead/{self.instance}",
                json={"readMessages": [{"id": message_id}]},
            )
        except Exception:
            pass  # Best effort

    def parse_webhook(self, body: dict, headers: dict) -> ChannelIncoming | None:
        """Parse Evolution API webhook payload.

        Evolution sends different event types. We only care about:
        - messages.upsert (new message received)

        Payload structure:
        {
            "event": "messages.upsert",
            "instance": "shadow",
            "data": {
                "key": {
                    "remoteJid": "5511999999999@s.whatsapp.net",
                    "fromMe": false,
                    "id": "ABC123"
                },
                "pushName": "John",
                "message": {
                    "conversation": "Hello!",
                    "extendedTextMessage": {"text": "Hello!"}
                },
                "messageTimestamp": 1234567890
            }
        }
        """
        event = body.get("event", "")
        if event != "messages.upsert":
            return None

        data = body.get("data", {})
        key = data.get("key", {})

        # Skip outgoing messages
        if key.get("fromMe", False):
            return None

        # Extract remote JID and normalize to E.164
        remote_jid = key.get("remoteJid", "")
        if not remote_jid or "@g.us" in remote_jid:
            return None  # Skip group messages

        phone = normalize_phone(remote_jid)

        # Extract message text
        message = data.get("message", {})
        text = (
            message.get("conversation")
            or (message.get("extendedTextMessage") or {}).get("text")
            or ""
        )

        if not text:
            return None  # Skip non-text messages for now

        # Extract timestamp
        timestamp = data.get("messageTimestamp", 0)
        if isinstance(timestamp, str):
            try:
                timestamp = int(timestamp)
            except ValueError:
                timestamp = int(time.time())

        return ChannelIncoming(
            external_id=key.get("id", ""),
            phone=phone,
            display_name=data.get("pushName"),
            text=text,
            timestamp=timestamp,
            raw=body,
        )

    def verify_webhook(self, params: dict) -> str | None:
        """Evolution API doesn't require webhook verification."""
        return None

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

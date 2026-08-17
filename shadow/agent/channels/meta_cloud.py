"""Meta Cloud API (WhatsApp Business) adapter.

Official WhatsApp Business API via Meta's Graph API.
Requires Meta Business verification, approved templates for messages
outside the 24-hour conversation window.

Docs: https://developers.facebook.com/docs/whatsapp/cloud-api
"""

from __future__ import annotations

import hashlib
import hmac
import time

import httpx

from channels.base import ChannelAdapter, ChannelIncoming, SendResult, normalize_phone


GRAPH_API_VERSION = "v21.0"


class MetaCloudAdapter:
    """ChannelAdapter implementation for Meta Cloud API (WhatsApp Business)."""

    adapter_type: str = "meta_cloud"

    def __init__(
        self,
        access_token: str,
        phone_number_id: str,
        verify_token: str,
        app_secret: str | None = None,
        waba_id: str | None = None,
    ) -> None:
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.verify_token = verify_token
        self.app_secret = app_secret
        self.waba_id = waba_id
        self._base_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=15,
        )

    async def send_text(self, phone: str, text: str) -> SendResult:
        """Send text message via Meta Cloud API."""
        number = phone.lstrip("+")
        try:
            resp = await self._client.post(
                f"{self._base_url}/{self.phone_number_id}/messages",
                json={
                    "messaging_product": "whatsapp",
                    "to": number,
                    "type": "text",
                    "text": {"body": text},
                },
            )
            data = resp.json()
            if resp.status_code == 200:
                messages = data.get("messages", [])
                msg_id = messages[0]["id"] if messages else None
                return SendResult(success=True, message_id=msg_id, raw=data)
            error = data.get("error", {})
            return SendResult(
                success=False,
                error=error.get("message", str(data)),
                raw=data,
            )
        except Exception as e:
            return SendResult(success=False, error=str(e))

    async def send_template(
        self, phone: str, template: str, params: list[str]
    ) -> SendResult:
        """Send template message via Meta Cloud API.

        Required when messaging outside the 24-hour conversation window.
        Templates must be pre-approved by Meta.
        """
        number = phone.lstrip("+")
        components = []
        if params:
            components.append({
                "type": "body",
                "parameters": [
                    {"type": "text", "text": p} for p in params
                ],
            })

        try:
            resp = await self._client.post(
                f"{self._base_url}/{self.phone_number_id}/messages",
                json={
                    "messaging_product": "whatsapp",
                    "to": number,
                    "type": "template",
                    "template": {
                        "name": template,
                        "language": {"code": "pt_BR"},
                        "components": components,
                    },
                },
            )
            data = resp.json()
            if resp.status_code == 200:
                messages = data.get("messages", [])
                msg_id = messages[0]["id"] if messages else None
                return SendResult(success=True, message_id=msg_id, raw=data)
            error = data.get("error", {})
            return SendResult(
                success=False,
                error=error.get("message", str(data)),
                raw=data,
            )
        except Exception as e:
            return SendResult(success=False, error=str(e))

    async def send_media(
        self, phone: str, media_url: str, caption: str | None = None
    ) -> SendResult:
        """Send media message via Meta Cloud API."""
        number = phone.lstrip("+")
        try:
            payload: dict = {
                "messaging_product": "whatsapp",
                "to": number,
                "type": "image",
                "image": {"link": media_url},
            }
            if caption:
                payload["image"]["caption"] = caption

            resp = await self._client.post(
                f"{self._base_url}/{self.phone_number_id}/messages",
                json=payload,
            )
            data = resp.json()
            if resp.status_code == 200:
                messages = data.get("messages", [])
                msg_id = messages[0]["id"] if messages else None
                return SendResult(success=True, message_id=msg_id, raw=data)
            error = data.get("error", {})
            return SendResult(
                success=False,
                error=error.get("message", str(data)),
                raw=data,
            )
        except Exception as e:
            return SendResult(success=False, error=str(e))

    async def mark_read(self, message_id: str) -> None:
        """Mark message as read via Meta Cloud API."""
        try:
            await self._client.post(
                f"{self._base_url}/{self.phone_number_id}/messages",
                json={
                    "messaging_product": "whatsapp",
                    "status": "read",
                    "message_id": message_id,
                },
            )
        except Exception:
            pass  # Best effort

    def parse_webhook(self, body: dict, headers: dict) -> ChannelIncoming | None:
        """Parse Meta Cloud API webhook payload.

        Payload structure:
        {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "WABA_ID",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "..."},
                        "contacts": [{"profile": {"name": "John"}, "wa_id": "5511999999999"}],
                        "messages": [{
                            "from": "5511999999999",
                            "id": "wamid.HBE...",
                            "timestamp": "1234567890",
                            "type": "text",
                            "text": {"body": "Hello!"}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        """
        if body.get("object") != "whatsapp_business_account":
            return None

        entries = body.get("entry", [])
        if not entries:
            return None

        for entry in entries:
            for change in entry.get("changes", []):
                if change.get("field") != "messages":
                    continue

                value = change.get("value", {})
                messages = value.get("messages", [])
                if not messages:
                    continue

                msg = messages[0]

                # Only handle text messages for now
                if msg.get("type") != "text":
                    continue

                phone = normalize_phone(msg.get("from", ""))
                text = (msg.get("text") or {}).get("body", "")

                if not text:
                    continue

                # Extract contact name
                contacts = value.get("contacts", [])
                display_name = None
                if contacts:
                    profile = contacts[0].get("profile", {})
                    display_name = profile.get("name")

                # Extract timestamp
                timestamp = msg.get("timestamp", "0")
                try:
                    timestamp = int(timestamp)
                except ValueError:
                    timestamp = int(time.time())

                return ChannelIncoming(
                    external_id=msg.get("id", ""),
                    phone=phone,
                    display_name=display_name,
                    text=text,
                    timestamp=timestamp,
                    raw=body,
                )

        return None

    def verify_webhook(self, params: dict) -> str | None:
        """Verify Meta webhook challenge.

        Meta sends a GET request with:
        - hub.mode = "subscribe"
        - hub.verify_token = <your verify token>
        - hub.challenge = <challenge string>
        """
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")

        if mode == "subscribe" and token == self.verify_token:
            return challenge

        return None

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify HMAC-SHA256 signature from X-Hub-Signature-256 header."""
        if not self.app_secret:
            return True  # Skip verification if no secret configured

        expected = hmac.new(
            self.app_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        sig_value = signature.removeprefix("sha256=")
        return hmac.compare_digest(expected, sig_value)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

from typing import Any


class WhatsAppGateway:
    """Placeholder gateway. Configure real provider in production."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = base_url
        self.api_key = api_key

    def send_message(self, phone: str, text: str) -> dict[str, Any]:
        return {"ok": True, "phone": phone, "text": text}

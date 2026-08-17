"""Channel adapters for WhatsApp messaging.

Supports:
- Evolution API (MVP, open-source, Docker)
- Meta Cloud API (Production, official)
"""

from channels.base import ChannelAdapter, ChannelIncoming, SendResult, normalize_phone
from channels.webhook_handler import WebhookHandler

__all__ = [
    "ChannelAdapter",
    "ChannelIncoming",
    "SendResult",
    "WebhookHandler",
    "normalize_phone",
    "get_adapter",
]


def get_adapter(
    adapter_type: str,
    **kwargs,
) -> ChannelAdapter:
    """Factory function to create the appropriate channel adapter.

    Args:
        adapter_type: "evolution" or "meta_cloud"
        **kwargs: Adapter-specific configuration

    Returns:
        ChannelAdapter instance

    Raises:
        ValueError: If adapter_type is unknown
    """
    if adapter_type == "evolution":
        from channels.evolution import EvolutionAdapter

        return EvolutionAdapter(
            api_url=kwargs["api_url"],
            api_key=kwargs["api_key"],
            instance=kwargs["instance"],
        )

    if adapter_type == "meta_cloud":
        from channels.meta_cloud import MetaCloudAdapter

        return MetaCloudAdapter(
            access_token=kwargs["access_token"],
            phone_number_id=kwargs["phone_number_id"],
            verify_token=kwargs["verify_token"],
            app_secret=kwargs.get("app_secret"),
            waba_id=kwargs.get("waba_id"),
        )

    raise ValueError(f"Unknown adapter type: {adapter_type!r}. Use 'evolution' or 'meta_cloud'.")

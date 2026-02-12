"""LLM provider abstraction layer.

Provides a unified interface to multiple LLM providers via LiteLLM.
Adapted from nanobot/providers/.
"""

from .base import LLMProvider, LLMResponse, ToolCallRequest
from .litellm_provider import LiteLLMProvider
from .registry import get_provider, PROVIDER_SPECS, ProviderSpec

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "ToolCallRequest",
    "LiteLLMProvider",
    "get_provider",
    "PROVIDER_SPECS",
    "ProviderSpec",
]

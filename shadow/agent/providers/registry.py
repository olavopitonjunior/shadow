"""Provider registry for auto-detection and selection.

Simplified from nanobot/providers/registry.py.
Supports 4 providers: Anthropic, OpenAI, Gemini, DeepSeek.
"""

import os
from dataclasses import dataclass
from typing import Any

from .base import LLMProvider


@dataclass(frozen=True)
class ProviderSpec:
    """Specification for an LLM provider."""
    name: str
    env_key: str
    litellm_prefix: str
    default_model: str
    display_name: str = ""

    def has_key(self) -> bool:
        """Check if API key is available in environment."""
        return bool(os.getenv(self.env_key))


# Supported providers
PROVIDER_SPECS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        name="anthropic",
        env_key="ANTHROPIC_API_KEY",
        litellm_prefix="",
        default_model="claude-sonnet-4-20250514",
        display_name="Anthropic Claude",
    ),
    "openai": ProviderSpec(
        name="openai",
        env_key="OPENAI_API_KEY",
        litellm_prefix="",
        default_model="gpt-4o",
        display_name="OpenAI GPT",
    ),
    "gemini": ProviderSpec(
        name="gemini",
        env_key="GEMINI_API_KEY",
        litellm_prefix="gemini/",
        default_model="gemini-2.0-flash",
        display_name="Google Gemini",
    ),
    "deepseek": ProviderSpec(
        name="deepseek",
        env_key="DEEPSEEK_API_KEY",
        litellm_prefix="deepseek/",
        default_model="deepseek-chat",
        display_name="DeepSeek",
    ),
}

# Model name → provider mapping for auto-detection
_MODEL_KEYWORDS: dict[str, str] = {
    "claude": "anthropic",
    "gpt": "openai",
    "o1": "openai",
    "o3": "openai",
    "gemini": "gemini",
    "deepseek": "deepseek",
}


def detect_provider_by_model(model: str) -> str | None:
    """Detect provider from model name."""
    model_lower = model.lower()
    for keyword, provider_name in _MODEL_KEYWORDS.items():
        if keyword in model_lower:
            return provider_name
    return None


def detect_provider_by_env() -> str | None:
    """Detect provider from available API keys (priority order)."""
    for name in ("anthropic", "openai", "gemini", "deepseek"):
        if PROVIDER_SPECS[name].has_key():
            return name
    return None


def get_provider(
    provider_name: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> LLMProvider:
    """
    Get an LLM provider instance.

    Detection priority:
    1. Explicit provider_name parameter
    2. SHADOW_LLM_PROVIDER env var
    3. Model name detection
    4. Available API key detection
    5. Error

    Returns:
        Configured LLMProvider instance
    """
    from .litellm_provider import LiteLLMProvider

    # 1. Explicit parameter
    name = provider_name

    # 2. Environment variable
    if not name:
        name = os.getenv("SHADOW_LLM_PROVIDER")

    # 3. Detect by model name
    if not name and model:
        name = detect_provider_by_model(model)

    # 4. Detect by available API key
    if not name:
        name = detect_provider_by_env()

    if not name:
        raise ValueError(
            "No LLM provider detected. Set SHADOW_LLM_PROVIDER or "
            "provide an API key (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)"
        )

    if name not in PROVIDER_SPECS:
        raise ValueError(
            f"Unknown provider '{name}'. "
            f"Available: {', '.join(PROVIDER_SPECS.keys())}"
        )

    spec = PROVIDER_SPECS[name]
    resolved_key = api_key or os.getenv(spec.env_key)
    resolved_model = model or os.getenv("CLAUDE_MODEL") or spec.default_model

    return LiteLLMProvider(
        api_key=resolved_key,
        default_model=resolved_model,
        provider_spec=spec,
    )

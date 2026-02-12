"""LiteLLM provider implementation for multi-provider support.

Adapted from nanobot/providers/litellm_provider.py.
Uses litellm.completion() (sync) for Shadow's synchronous architecture.
"""

import json
from typing import Any

import litellm
from litellm import completion

from .base import LLMProvider, LLMResponse, ToolCallRequest
from .registry import ProviderSpec


class LiteLLMProvider(LLMProvider):
    """
    LLM provider using LiteLLM for multi-provider support.

    Supports Anthropic, OpenAI, Gemini, DeepSeek through a unified
    synchronous interface.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "claude-sonnet-4-20250514",
        provider_spec: ProviderSpec | None = None,
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        self._spec = provider_spec

        # Disable LiteLLM logging noise
        litellm.suppress_debug_info = True
        # Drop unsupported parameters for providers
        litellm.drop_params = True

    def _resolve_model(self, model: str) -> str:
        """Resolve model name by applying provider prefix if needed."""
        if not self._spec or not self._spec.litellm_prefix:
            return model

        prefix = self._spec.litellm_prefix
        # Don't double-prefix
        if model.startswith(prefix):
            return model
        # Don't prefix if model already has a provider prefix
        if "/" in model:
            return model

        return f"{prefix}{model}"

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> LLMResponse:
        """
        Send a synchronous chat completion request via LiteLLM.

        LiteLLM handles format conversion between providers internally.
        Tools should be in OpenAI format.
        """
        resolved_model = self._resolve_model(model or self.default_model)

        # Build messages - inject system prompt if provided
        final_messages = list(messages)
        if system:
            # LiteLLM handles system messages for all providers
            final_messages = [{"role": "system", "content": system}] + final_messages

        kwargs: dict[str, Any] = {
            "model": resolved_model,
            "messages": final_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        # Pass api_key directly
        if self.api_key:
            kwargs["api_key"] = self.api_key

        if self.api_base:
            kwargs["api_base"] = self.api_base

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = completion(**kwargs)
            return self._parse_response(response)
        except Exception as e:
            err_str = str(e).lower()
            if "rate_limit" in err_str or "rate limit" in err_str or "429" in err_str:
                friendly = "Estou sobrecarregado no momento. Tente novamente em alguns segundos."
            elif "timeout" in err_str or "timed out" in err_str:
                friendly = "A requisição demorou demais. Tente novamente."
            elif "authentication" in err_str or "api_key" in err_str or "401" in err_str:
                friendly = "Erro de configuração do assistente. Contate o administrador."
            else:
                friendly = "Desculpe, ocorreu um erro ao processar. Tente novamente."
            print(f"[litellm_provider] Error: {e}")
            return LLMResponse(
                content=friendly,
                finish_reason="error",
            )

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse LiteLLM response into our standard format."""
        choice = response.choices[0]
        message = choice.message

        tool_calls = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args}

                tool_calls.append(ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens or 0,
                "completion_tokens": response.usage.completion_tokens or 0,
                "total_tokens": response.usage.total_tokens or 0,
            }

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
        )

    def get_default_model(self) -> str:
        """Get the default model."""
        return self.default_model

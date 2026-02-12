"""
Tests for the LLM provider abstraction layer.
"""

import os
import pytest


class TestProviderDataclasses:
    """Test provider data structures."""

    def test_tool_call_request_fields(self):
        from providers.base import ToolCallRequest

        tc = ToolCallRequest(id="tc_1", name="create_task", arguments={"title": "Test"})
        assert tc.id == "tc_1"
        assert tc.name == "create_task"
        assert tc.arguments == {"title": "Test"}

    def test_llm_response_no_tool_calls(self):
        from providers.base import LLMResponse

        resp = LLMResponse(
            content="Hello",
            tool_calls=[],
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
        )
        assert resp.content == "Hello"
        assert resp.has_tool_calls is False
        assert resp.input_tokens == 10
        assert resp.output_tokens == 5

    def test_llm_response_with_tool_calls(self):
        from providers.base import LLMResponse, ToolCallRequest

        tc = ToolCallRequest(id="tc_1", name="list_tasks", arguments={})
        resp = LLMResponse(
            content=None,
            tool_calls=[tc],
            finish_reason="tool_calls",
            usage={"prompt_tokens": 20, "completion_tokens": 10},
        )
        assert resp.has_tool_calls is True
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "list_tasks"

    def test_llm_response_missing_usage_keys(self):
        from providers.base import LLMResponse

        resp = LLMResponse(content="Hi", tool_calls=[], finish_reason="stop", usage={})
        assert resp.input_tokens == 0
        assert resp.output_tokens == 0


class TestProviderRegistry:
    """Test provider auto-detection and registry."""

    def test_provider_specs_exist(self):
        from providers.registry import PROVIDER_SPECS

        assert "anthropic" in PROVIDER_SPECS
        assert "openai" in PROVIDER_SPECS
        assert "gemini" in PROVIDER_SPECS
        assert "deepseek" in PROVIDER_SPECS

    def test_provider_spec_fields(self):
        from providers.registry import PROVIDER_SPECS

        spec = PROVIDER_SPECS["anthropic"]
        assert spec.name == "anthropic"
        assert spec.env_key == "ANTHROPIC_API_KEY"
        assert "claude" in spec.default_model

    def test_provider_spec_gemini_prefix(self):
        from providers.registry import PROVIDER_SPECS

        spec = PROVIDER_SPECS["gemini"]
        assert spec.litellm_prefix == "gemini/"

    def test_get_provider_explicit_name(self):
        """get_provider with explicit name creates LiteLLMProvider."""
        from providers.registry import get_provider

        # Should work even without API key in env (key can be passed)
        provider = get_provider(provider_name="anthropic", api_key="test-key")
        assert provider is not None
        assert provider.get_default_model() == "claude-sonnet-4-20250514"

    def test_get_provider_model_detection(self):
        """get_provider detects provider from model name."""
        from providers.registry import get_provider

        provider = get_provider(model="gpt-4o", api_key="test-key")
        assert provider.get_default_model() == "gpt-4o"

    def test_get_provider_gemini_detection(self):
        from providers.registry import get_provider

        provider = get_provider(model="gemini-2.0-flash", api_key="test-key")
        assert provider.get_default_model() == "gemini-2.0-flash"


class TestOpenAIToolFormat:
    """Test tool format conversion for LiteLLM."""

    def test_to_openai_tools_format(self):
        from tools import setup_default_tools
        from tool_adapter import to_openai_tools

        registry = setup_default_tools()
        tools = to_openai_tools(registry, tier=1)

        assert len(tools) > 0
        for tool in tools:
            assert tool["type"] == "function"
            assert "function" in tool
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func

    def test_format_tool_result_openai(self):
        from tool_adapter import format_tool_result_openai

        result = format_tool_result_openai(
            tool_call_id="tc_123",
            tool_name="list_tasks",
            result="Found 3 tasks",
        )
        assert result["role"] == "tool"
        assert result["tool_call_id"] == "tc_123"
        assert result["content"] == "Found 3 tasks"

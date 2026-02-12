"""
Tool Adapter - Converts Shadow tools to LLM-specific formats.

Shadow tools use a custom Tool class with ToolParameter definitions.
This module converts them to the format expected by each provider:
- Claude: native tool_use format (input_schema)
- OpenAI/LiteLLM: function calling format (parameters)
"""

from typing import Any

from tools import Tool, ToolRegistry, get_tool_registry


def tool_to_claude_format(tool: Tool) -> dict[str, Any]:
    """
    Convert a Shadow Tool to Claude tool schema.

    Args:
        tool: Shadow Tool instance

    Returns:
        Dict in Claude's expected tool format:
        {
            "name": "tool_name",
            "description": "Tool description",
            "input_schema": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }
    """
    properties = {}
    required = []

    for param in tool.parameters:
        prop: dict[str, Any] = {
            "type": param.type,
            "description": param.description,
        }

        # Add enum constraint if present
        if param.enum:
            prop["enum"] = param.enum

        # Add default if present
        if param.default is not None:
            prop["default"] = param.default

        properties[param.name] = prop

        if param.required:
            required.append(param.name)

    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def to_claude_tools(
    registry: ToolRegistry | None = None,
    tier: int | None = None,
    extra_tools: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Convert tools in registry to Claude format, optionally filtered by tier.

    Args:
        registry: ToolRegistry instance (uses global if not provided)
        tier: If set, only include tools of this tier (1 = core, 2 = on-demand).
              If None, includes all tools (backward compatible).
        extra_tools: Additional tool names to include regardless of tier.
                     Used for dynamically loaded tools mid-conversation.

    Returns:
        List of tool definitions for Claude's tools parameter
    """
    if registry is None:
        registry = get_tool_registry()

    extra = extra_tools or set()

    tools = []
    for tool_name in registry.list_tools():
        # Apply tier filter if specified
        if tier is not None:
            from tools.meta_tools import get_tier
            tool_tier = get_tier(tool_name)
            if tool_tier != tier and tool_name not in extra:
                continue

        tool = registry.get(tool_name)
        if tool:
            tools.append(tool_to_claude_format(tool))

    return tools


def tool_to_openai_format(tool: Tool) -> dict[str, Any]:
    """
    Convert a Shadow Tool to OpenAI function calling format.

    Used by LiteLLM for non-Anthropic providers.

    Returns:
        Dict in OpenAI's expected format:
        {
            "type": "function",
            "function": {
                "name": "tool_name",
                "description": "...",
                "parameters": {"type": "object", "properties": {...}, "required": [...]}
            }
        }
    """
    properties = {}
    required = []

    for param in tool.parameters:
        prop: dict[str, Any] = {
            "type": param.type,
            "description": param.description,
        }
        if param.enum:
            prop["enum"] = param.enum
        if param.default is not None:
            prop["default"] = param.default

        properties[param.name] = prop

        if param.required:
            required.append(param.name)

    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def to_openai_tools(
    registry: ToolRegistry | None = None,
    tier: int | None = None,
    extra_tools: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Convert tools in registry to OpenAI format, optionally filtered by tier.

    Same filtering logic as to_claude_tools() but outputs OpenAI format.
    """
    if registry is None:
        registry = get_tool_registry()

    extra = extra_tools or set()

    tools = []
    for tool_name in registry.list_tools():
        if tier is not None:
            from tools.meta_tools import get_tier
            tool_tier = get_tier(tool_name)
            if tool_tier != tier and tool_name not in extra:
                continue

        tool = registry.get(tool_name)
        if tool:
            tools.append(tool_to_openai_format(tool))

    return tools


def format_tool_result_openai(
    tool_call_id: str,
    tool_name: str,
    result: Any,
) -> dict[str, Any]:
    """
    Format a tool result for OpenAI's tool message format.

    Returns:
        Dict in OpenAI's tool result format
    """
    content = result if isinstance(result, str) else str(result)

    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": content,
    }


def format_tool_result(tool_use_id: str, result: Any, is_error: bool = False) -> dict[str, Any]:
    """
    Format a tool result for Claude's tool_result message.

    Args:
        tool_use_id: The ID from Claude's tool_use block
        result: The result content (string or dict)
        is_error: Whether this is an error result

    Returns:
        Dict in Claude's tool_result format
    """
    content = result if isinstance(result, str) else str(result)

    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
        "is_error": is_error,
    }

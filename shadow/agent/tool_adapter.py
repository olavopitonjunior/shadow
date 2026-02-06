"""
Tool Adapter - Converts Shadow tools to Claude tool format.

Shadow tools use a custom Tool class with ToolParameter definitions.
This module converts them to the format expected by Claude's tool_use API.
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


def to_claude_tools(registry: ToolRegistry | None = None) -> list[dict[str, Any]]:
    """
    Convert all tools in registry to Claude format.

    Args:
        registry: ToolRegistry instance (uses global if not provided)

    Returns:
        List of tool definitions for Claude's tools parameter
    """
    if registry is None:
        registry = get_tool_registry()

    tools = []
    for tool_name in registry.list_tools():
        tool = registry.get(tool_name)
        if tool:
            tools.append(tool_to_claude_format(tool))

    return tools


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

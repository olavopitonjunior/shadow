"""
Tool Registry - Central registry for all agent tools.

Inspired by moltbot's createOpenClawTools pattern.
"""

import time
from typing import Any

from .base import Tool, ToolContext, ToolResult


class ToolRegistry:
    """
    Central registry for agent tools.

    Provides:
    - Tool registration and discovery
    - Tool execution with validation
    - Schema generation for LLM
    - Category-based filtering

    Example:
        registry = ToolRegistry()
        registry.register(CreateTaskTool())
        registry.register(ListTasksTool())

        # Execute a tool
        result = registry.execute("create_task", {"title": "Buy milk"}, context)

        # Get all tools for LLM
        schemas = registry.get_all_schemas()
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._categories: dict[str, list[str]] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool instance."""
        if tool.name in self._tools:
            print(f"[tools] Warning: Overwriting tool '{tool.name}'")

        self._tools[tool.name] = tool

        # Track by category
        if tool.category not in self._categories:
            self._categories[tool.category] = []
        if tool.name not in self._categories[tool.category]:
            self._categories[tool.category].append(tool.name)

        print(f"[tools] Registered: {tool.name} ({tool.category})")

    def unregister(self, name: str) -> bool:
        """Unregister a tool by name."""
        if name not in self._tools:
            return False

        tool = self._tools.pop(name)
        if tool.category in self._categories:
            self._categories[tool.category] = [
                n for n in self._categories[tool.category] if n != name
            ]
        return True

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def list_by_category(self, category: str) -> list[str]:
        """List tool names in a category."""
        return self._categories.get(category, [])

    def get_categories(self) -> list[str]:
        """List all categories."""
        return list(self._categories.keys())

    def execute(
        self,
        name: str,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """
        Execute a tool by name.

        Args:
            name: Tool name
            params: Parameters for the tool
            context: Execution context

        Returns:
            ToolResult with outcome
        """
        tool = self._tools.get(name)
        if not tool:
            return ToolResult.error(f"Tool not found: {name}")

        # Validate parameters
        is_valid, error = tool.validate_params(params)
        if not is_valid:
            return ToolResult.error(error or "Invalid parameters")

        # Execute with timing
        start = time.time()
        try:
            result = tool.execute(params, context)
            result.tool_name = name
            result.duration_ms = int((time.time() - start) * 1000)
            return result
        except Exception as e:
            print(f"[tools] Error executing {name}: {e}")
            return ToolResult.error(f"Tool execution failed: {str(e)}")

    def get_schema(self, name: str) -> dict[str, Any] | None:
        """Get JSON schema for a tool."""
        tool = self._tools.get(name)
        return tool.to_schema() if tool else None

    def get_all_schemas(self) -> list[dict[str, Any]]:
        """Get JSON schemas for all tools (for LLM function calling)."""
        return [tool.to_schema() for tool in self._tools.values()]

    def get_tools_description(self) -> str:
        """
        Get human-readable description of all tools.

        Useful for including in system prompts.
        """
        lines = ["Available tools:"]
        for name, tool in sorted(self._tools.items()):
            params = ", ".join(
                f"{p.name}: {p.type}{'?' if not p.required else ''}"
                for p in tool.parameters
            )
            lines.append(f"- {name}({params}): {tool.description}")
        return "\n".join(lines)

    def find_tool_for_intent(self, intent: str) -> Tool | None:
        """
        Find a tool that matches an intent.

        Maps common intents to tools:
        - create_task -> create_task
        - list_tasks -> list_tasks
        - etc.
        """
        # Direct mapping
        intent_to_tool = {
            "create_task": "create_task",
            "list_tasks": "list_tasks",
            "create_appointment": "create_appointment",
            "list_appointments": "list_appointments",
            "create_reminder": "create_reminder",
            "send_message": "send_message",
        }

        tool_name = intent_to_tool.get(intent)
        if tool_name:
            return self._tools.get(tool_name)

        # Fallback: try exact match
        return self._tools.get(intent)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


# === Global registry singleton ===

_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def register_tool(tool: Tool) -> None:
    """Convenience function to register a tool globally."""
    get_tool_registry().register(tool)

"""
Tool Base Classes - Inspired by moltbot ChannelAgentTool

Provides a unified interface for agent tools/skills.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


@dataclass
class ToolContext:
    """Context provided to tools during execution."""

    # User info
    user_phone: str | None = None
    user_name: str | None = None

    # Session info
    session_id: str | None = None
    chat_id: str | None = None

    # Request info
    message_text: str | None = None
    timestamp: str | None = None

    # Storage reference (set by registry)
    storage: Any = None

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def now_iso(self) -> str:
        """Returns current UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()


@dataclass
class ToolResult:
    """Result returned by tool execution."""

    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    # For LLM feedback
    display_text: str | None = None

    # Metadata
    tool_name: str | None = None
    duration_ms: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "display_text": self.display_text,
            "tool_name": self.tool_name,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }

    @classmethod
    def ok(
        cls,
        message: str,
        data: dict[str, Any] | None = None,
        display_text: str | None = None,
    ) -> "ToolResult":
        """Create a successful result."""
        return cls(
            success=True,
            message=message,
            data=data or {},
            display_text=display_text or message,
        )

    @classmethod
    def error(cls, message: str, error: str | None = None) -> "ToolResult":
        """Create an error result."""
        return cls(
            success=False,
            message=message,
            error=error or message,
            display_text=f"Erro: {message}",
        )


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""

    name: str
    type: Literal["string", "number", "boolean", "array", "object"]
    description: str
    required: bool = False
    default: Any = None
    enum: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "required": self.required,
        }
        if self.default is not None:
            d["default"] = self.default
        if self.enum:
            d["enum"] = self.enum
        return d


class Tool(ABC):
    """
    Base class for all agent tools.

    Inspired by moltbot's ChannelAgentTool interface.

    Example:
        class GreetTool(Tool):
            name = "greet"
            description = "Greets the user"
            parameters = [
                ToolParameter("name", "string", "Name to greet", required=True)
            ]

            def execute(self, params, context):
                name = params.get("name", "friend")
                return ToolResult.ok(f"Hello, {name}!")
    """

    # Tool metadata (must be overridden)
    name: str = "unnamed_tool"
    description: str = "No description"
    parameters: list[ToolParameter] = []

    # Optional: category for grouping
    category: str = "general"

    # Optional: whether tool requires confirmation
    requires_confirmation: bool = False

    @abstractmethod
    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        """
        Execute the tool with given parameters.

        Args:
            params: Dictionary of parameter values
            context: Execution context with user/session info

        Returns:
            ToolResult with success/error and data
        """
        pass

    def validate_params(self, params: dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validate parameters against schema.

        Returns:
            Tuple of (is_valid, error_message)
        """
        for param in self.parameters:
            if param.required and param.name not in params:
                return False, f"Missing required parameter: {param.name}"

            if param.name in params:
                value = params[param.name]

                # Type validation
                if param.type == "string" and not isinstance(value, str):
                    return False, f"Parameter {param.name} must be a string"
                if param.type == "number" and not isinstance(value, (int, float)):
                    return False, f"Parameter {param.name} must be a number"
                if param.type == "boolean" and not isinstance(value, bool):
                    return False, f"Parameter {param.name} must be a boolean"

                # Enum validation
                if param.enum and value not in param.enum:
                    return False, f"Parameter {param.name} must be one of: {param.enum}"

        return True, None

    def to_schema(self) -> dict[str, Any]:
        """
        Convert tool to JSON schema for LLM function calling.

        Compatible with OpenAI/Anthropic tool format.
        """
        properties = {}
        required = []

        for param in self.parameters:
            prop = {"type": param.type, "description": param.description}
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def __repr__(self) -> str:
        return f"<Tool {self.name}>"

"""
LangChain Tool Adapter - Wraps Shadow tools as LangChain StructuredTools.

Bridges the existing Tool.execute(params, context) interface to
LangChain's StructuredTool format for use in LangGraph worker subgraphs.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool

from tools import Tool, ToolContext, ToolRegistry, get_tool_registry
from tools import setup_default_tools
from storage import Storage

# Ensure tools are registered
setup_default_tools()

# ── Tool Loadouts per Worker ──

WORKER_TOOLS: dict[str, list[str]] = {
    "crm": [
        "get_contact", "list_contacts", "create_contact", "update_contact",
        "delete_contact", "restore_contact", "merge_contacts", "find_duplicates",
        "search_contact_history", "get_contact_tasks",
        "recall_memory", "store_memory", "forget_memory",
        "contact_history",
    ],
    "planner": [
        "create_task", "list_tasks", "update_task", "complete_task", "delete_task",
        "create_appointment", "list_appointments", "update_appointment",
        "delete_appointment", "create_reminder",
        "list_categories", "create_category",
    ],
    "analytics": [
        "preview_summary", "list_alerts", "create_alert", "delete_alert",
        "list_tasks", "list_appointments", "list_contacts",
        "conversation_summary",
    ],
    "docgen": [
        "get_contact", "list_contacts", "recall_memory",
        "list_tasks", "list_appointments",
        "search_contact_history",
    ],
    "collector": [
        "create_contact", "update_contact", "store_memory",
        "get_contact", "list_contacts",
    ],
}


def _build_tool_func(tool_name: str, registry: ToolRegistry, context: ToolContext):
    """Create a callable function that wraps a Shadow tool."""
    def invoke(**kwargs) -> str:
        result = registry.execute(tool_name, kwargs, context)
        return result.display_text or result.message or str(result.data)
    invoke.__name__ = tool_name
    return invoke


def _build_args_schema(tool: Tool) -> dict[str, Any]:
    """Convert Shadow ToolParameters to JSON Schema for LangChain."""
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
        "type": "object",
        "properties": properties,
        "required": required,
    }


def wrap_shadow_tool(
    tool_name: str,
    registry: ToolRegistry,
    context: ToolContext,
) -> StructuredTool | None:
    """Wrap a single Shadow tool as a LangChain StructuredTool.

    Returns None if the tool is not found in the registry.
    """
    tool = registry.get(tool_name)
    if not tool:
        return None

    func = _build_tool_func(tool_name, registry, context)

    return StructuredTool.from_function(
        func=func,
        name=tool.name,
        description=tool.description,
        args_schema=None,  # Let LangChain infer from function signature
        return_direct=False,
    )


def get_worker_tools(
    worker_name: str,
    context: ToolContext | None = None,
) -> list[StructuredTool]:
    """Get all LangChain tools for a specific worker.

    Args:
        worker_name: Worker identifier (crm, planner, analytics, docgen, collector)
        context: ToolContext for tool execution. If None, creates a default.

    Returns:
        List of LangChain StructuredTool instances
    """
    tool_names = WORKER_TOOLS.get(worker_name, [])
    if not tool_names:
        return []

    registry = get_tool_registry()
    if context is None:
        context = ToolContext(storage=Storage())

    tools = []
    for name in tool_names:
        wrapped = wrap_shadow_tool(name, registry, context)
        if wrapped:
            tools.append(wrapped)

    # Add worker-specific extra tools
    if worker_name == "docgen":
        from graph.adapters.docgen_tools import get_docgen_tools
        tools.extend(get_docgen_tools())

    if worker_name == "collector":
        from graph.adapters.collector_tools import get_collector_tools
        tools.extend(get_collector_tools())

    return tools


def make_tool_context_from_state(state: dict[str, Any]) -> ToolContext:
    """Create a ToolContext from ShadowState fields."""
    return ToolContext(
        user_phone=state.get("sender_phone") or "",
        user_name=state.get("sender_name") or "",
        session_id=state.get("session_id") or "",
        chat_id=state.get("chat_id") or "",
        message_text=state.get("body") or state.get("worker_task") or "",
        timestamp="",
        storage=Storage(),
        metadata={},
    )

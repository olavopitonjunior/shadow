"""
Shadow Tools Module - Agent tool system inspired by moltbot.

Provides:
- Tool base class for creating new tools
- ToolRegistry for managing and executing tools
- Built-in tools for tasks, appointments, reminders

Usage:
    from tools import get_tool_registry, ToolContext

    registry = get_tool_registry()
    context = ToolContext(user_phone="+55...", storage=storage)

    result = registry.execute("create_task", {"title": "Buy milk"}, context)
    if result.success:
        print(result.display_text)
"""

from .base import Tool, ToolContext, ToolParameter, ToolResult
from .registry import ToolRegistry, get_tool_registry, register_tool

# Import built-in tools
from .create_task import CreateTaskTool
from .list_tasks import ListTasksTool
from .update_task import UpdateTaskTool
from .complete_task import CompleteTaskTool
from .delete_task import DeleteTaskTool
from .create_appointment import CreateAppointmentTool
from .list_appointments import ListAppointmentsTool
from .update_appointment import UpdateAppointmentTool
from .delete_appointment import DeleteAppointmentTool
from .create_reminder import CreateReminderTool

# Phase 4: Contact tools
from .get_contact import GetContactTool
from .list_contacts import ListContactsTool
from .create_contact import CreateContactTool
from .update_contact import UpdateContactTool
from .search_contact_history import SearchContactHistoryTool
from .get_contact_tasks import GetContactTasksTool

# Phase 6: Memory tools
from .recall_memory import RecallMemoryTool
from .store_memory import StoreMemoryTool
from .forget_memory import ForgetMemoryTool

# Phase 1 CRM: Advanced Contact Management
from .delete_contact import DeleteContactTool
from .restore_contact import RestoreContactTool
from .merge_contacts import MergeContactsTool
from .find_duplicates import FindDuplicatesTool

# Phase 2: Categories
from .list_categories import ListCategoriesTool
from .create_category import CreateCategoryTool

# Phase 3: User Settings
from .get_settings import GetSettingsTool
from .update_settings import UpdateSettingsTool

# Phase 4: Scheduled Alerts
from .create_alert import CreateAlertTool
from .list_alerts import ListAlertsTool
from .delete_alert import DeleteAlertTool
from .preview_summary import PreviewSummaryTool

__all__ = [
    # Base classes
    "Tool",
    "ToolContext",
    "ToolParameter",
    "ToolResult",
    # Registry
    "ToolRegistry",
    "get_tool_registry",
    "register_tool",
    # Built-in tools - Tasks
    "CreateTaskTool",
    "ListTasksTool",
    "UpdateTaskTool",
    "CompleteTaskTool",
    "DeleteTaskTool",
    # Built-in tools - Appointments
    "CreateAppointmentTool",
    "ListAppointmentsTool",
    "UpdateAppointmentTool",
    "DeleteAppointmentTool",
    # Built-in tools - Reminders
    "CreateReminderTool",
    # Contact tools (Phase 4)
    "GetContactTool",
    "ListContactsTool",
    "CreateContactTool",
    "UpdateContactTool",
    "SearchContactHistoryTool",
    "GetContactTasksTool",
    # Memory tools (Phase 6)
    "RecallMemoryTool",
    "StoreMemoryTool",
    "ForgetMemoryTool",
    # Contact Management (Phase 1 CRM)
    "DeleteContactTool",
    "RestoreContactTool",
    "MergeContactsTool",
    "FindDuplicatesTool",
    # Categories (Phase 2)
    "ListCategoriesTool",
    "CreateCategoryTool",
    # User Settings (Phase 3)
    "GetSettingsTool",
    "UpdateSettingsTool",
    # Scheduled Alerts (Phase 4)
    "CreateAlertTool",
    "ListAlertsTool",
    "DeleteAlertTool",
    "PreviewSummaryTool",
    # Setup function
    "setup_default_tools",
]


def setup_default_tools(registry: ToolRegistry | None = None) -> ToolRegistry:
    """
    Register all default tools in the registry.

    Args:
        registry: Optional registry instance. If None, uses global registry.

    Returns:
        The registry with tools registered.
    """
    if registry is None:
        registry = get_tool_registry()

    # Register built-in tools - Tasks
    registry.register(CreateTaskTool())
    registry.register(ListTasksTool())
    registry.register(UpdateTaskTool())
    registry.register(CompleteTaskTool())
    registry.register(DeleteTaskTool())

    # Register built-in tools - Appointments
    registry.register(CreateAppointmentTool())
    registry.register(ListAppointmentsTool())
    registry.register(UpdateAppointmentTool())
    registry.register(DeleteAppointmentTool())

    # Register built-in tools - Reminders
    registry.register(CreateReminderTool())

    # Register contact tools (Phase 4)
    registry.register(GetContactTool())
    registry.register(ListContactsTool())
    registry.register(CreateContactTool())
    registry.register(UpdateContactTool())
    registry.register(SearchContactHistoryTool())
    registry.register(GetContactTasksTool())

    # Register memory tools (Phase 6)
    registry.register(RecallMemoryTool())
    registry.register(StoreMemoryTool())
    registry.register(ForgetMemoryTool())

    # Register contact management tools (Phase 1 CRM)
    registry.register(DeleteContactTool())
    registry.register(RestoreContactTool())
    registry.register(MergeContactsTool())
    registry.register(FindDuplicatesTool())

    # Register category tools (Phase 2)
    registry.register(ListCategoriesTool())
    registry.register(CreateCategoryTool())

    # Register settings tools (Phase 3)
    registry.register(GetSettingsTool())
    registry.register(UpdateSettingsTool())

    # Register alert tools (Phase 4)
    registry.register(CreateAlertTool())
    registry.register(ListAlertsTool())
    registry.register(DeleteAlertTool())
    registry.register(PreviewSummaryTool())

    print(f"[tools] Registered {len(registry)} default tools")
    return registry

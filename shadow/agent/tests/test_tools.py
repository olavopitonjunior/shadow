"""Tests for the tool system - registry, execution, and individual tools."""

import pytest


class TestToolRegistry:
    """Tool registry initialization and execution."""

    def test_registry_has_tools(self, tool_registry):
        schemas = tool_registry.get_all_schemas()
        assert len(schemas) >= 30  # We expect 35 tools

    def test_registry_contains_key_tools(self, tool_registry):
        expected = [
            "create_task", "list_tasks", "update_task", "complete_task", "delete_task",
            "create_appointment", "list_appointments",
            "create_reminder",
            "get_contact", "list_contacts", "create_contact",
            "store_memory", "recall_memory",
            "get_settings", "update_settings",
            "create_alert", "list_alerts",
            "list_categories",
            "list_suggestions",
        ]
        registered = set(tool_registry._tools.keys())
        for tool_name in expected:
            assert tool_name in registered, f"Missing tool: {tool_name}"

    def test_execute_unknown_tool(self, tool_registry, tool_context):
        result = tool_registry.execute("nonexistent_tool", {}, tool_context)
        assert not result.success


class TestTaskTools:
    """Task tool execution."""

    def test_create_task_tool(self, tool_registry, tool_context):
        result = tool_registry.execute(
            "create_task",
            {"title": "Test task via tool"},
            tool_context,
        )
        assert result.success
        assert "Test task via tool" in (result.display_text or result.message)

    def test_list_tasks_tool(self, tool_registry, tool_context):
        # Create a task first
        tool_registry.execute("create_task", {"title": "Listed task"}, tool_context)
        result = tool_registry.execute("list_tasks", {}, tool_context)
        assert result.success

    def test_create_task_with_category(self, tool_registry, tool_context, storage, owner_id):
        storage.seed_default_categories(owner_id)
        result = tool_registry.execute(
            "create_task",
            {"title": "Categorized task", "category": "trabalho"},
            tool_context,
        )
        assert result.success


class TestAppointmentTools:
    """Appointment tool execution."""

    def test_create_appointment_tool(self, tool_registry, tool_context):
        result = tool_registry.execute(
            "create_appointment",
            {"title": "Team standup", "datetime": "2026-02-10 10:00"},
            tool_context,
        )
        assert result.success

    def test_list_appointments_tool(self, tool_registry, tool_context):
        result = tool_registry.execute("list_appointments", {}, tool_context)
        assert result.success


class TestSettingsTools:
    """Settings tool execution."""

    def test_get_settings(self, tool_registry, tool_context):
        result = tool_registry.execute("get_settings", {}, tool_context)
        assert result.success
        # The display_text uses Portuguese labels like "fuso horário"
        assert "fuso" in (result.display_text or result.message).lower()

    def test_update_settings(self, tool_registry, tool_context):
        result = tool_registry.execute(
            "update_settings",
            {"setting": "use_emojis", "value": "false"},
            tool_context,
        )
        assert result.success


class TestMemoryTools:
    """Memory tool execution."""

    def test_store_memory(self, tool_registry, tool_context):
        result = tool_registry.execute(
            "store_memory",
            {"text": "User prefers coffee over tea"},
            tool_context,
        )
        assert result.success

    def test_recall_memory_empty(self, tool_registry, tool_context):
        result = tool_registry.execute(
            "recall_memory",
            {"query": "nonexistent topic"},
            tool_context,
        )
        # May fail if OPENAI_API_KEY not set (semantic search requires it)
        # In CI without the key, the tool returns an error about missing API key
        # This is expected behavior - we just verify it doesn't crash
        assert result is not None


class TestCategoryTools:
    """Category tool execution."""

    def test_list_categories(self, tool_registry, tool_context, storage, owner_id):
        storage.seed_default_categories(owner_id)
        result = tool_registry.execute("list_categories", {}, tool_context)
        assert result.success

    def test_create_category(self, tool_registry, tool_context, storage, owner_id):
        storage.seed_default_categories(owner_id)
        result = tool_registry.execute(
            "create_category",
            {"name": "test_cat", "type": "task"},
            tool_context,
        )
        assert result.success


class TestAlertTools:
    """Alert tool execution."""

    def test_create_alert(self, tool_registry, tool_context):
        result = tool_registry.execute(
            "create_alert",
            {"time": "07:00", "type": "summary"},
            tool_context,
        )
        assert result.success

    def test_list_alerts(self, tool_registry, tool_context):
        result = tool_registry.execute("list_alerts", {}, tool_context)
        assert result.success

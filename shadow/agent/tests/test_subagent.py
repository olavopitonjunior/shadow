"""
Tests for the subagent system.
"""

import pytest


class TestSubagentManager:
    """Test SubagentManager."""

    def test_subagent_manager_creation(self):
        from subagent import SubagentManager

        manager = SubagentManager()
        assert manager.get_running_count() == 0

    def test_subagent_status(self):
        from subagent import SubagentManager

        manager = SubagentManager()
        status = manager.status()
        assert status["running"] == []
        assert status["completed"] == 0
        assert status["max_concurrent"] == 3

    def test_subagent_read_only_tools(self):
        from subagent import SUBAGENT_ALLOWED_TOOLS

        # Verify no write tools are allowed
        write_tools = {
            "create_task", "update_task", "complete_task", "delete_task",
            "create_appointment", "update_appointment", "delete_appointment",
            "create_contact", "update_contact", "delete_contact",
            "store_memory", "forget_memory",
            "create_reminder", "create_alert", "delete_alert",
            "spawn_task",
        }
        overlap = SUBAGENT_ALLOWED_TOOLS & write_tools
        assert len(overlap) == 0, f"Write tools found in allowed list: {overlap}"

    def test_subagent_allowed_tools_are_read_only(self):
        from subagent import SUBAGENT_ALLOWED_TOOLS

        expected = {
            "list_tasks", "list_appointments", "get_contact", "list_contacts",
            "recall_memory", "contact_history", "preview_summary",
            "get_settings", "list_categories", "list_alerts",
            "list_suggestions", "list_available_tools",
        }
        assert SUBAGENT_ALLOWED_TOOLS == expected

    def test_subagent_max_concurrent_limit(self):
        from subagent import MAX_CONCURRENT_SUBAGENTS

        assert MAX_CONCURRENT_SUBAGENTS == 3

    def test_subagent_max_iterations(self):
        from subagent import MAX_SUBAGENT_ITERATIONS

        assert MAX_SUBAGENT_ITERATIONS == 10

    def test_subagent_result_dataclass(self):
        from subagent import SubagentResult

        result = SubagentResult(
            task_id="abc123",
            label="Test task",
            status="ok",
            result="Done",
            elapsed_s=1.5,
        )
        assert result.task_id == "abc123"
        assert result.status == "ok"
        assert result.elapsed_s == 1.5

    def test_build_read_only_registry(self):
        """Verify read-only registry only contains allowed tools."""
        from subagent import SubagentManager, SUBAGENT_ALLOWED_TOOLS
        from tools import setup_default_tools

        # Ensure full registry is populated
        setup_default_tools()

        manager = SubagentManager()
        read_only = manager._build_read_only_registry(context=None)

        tool_names = set(read_only.list_tools())
        # All tools in registry should be in the allowed set
        assert tool_names.issubset(SUBAGENT_ALLOWED_TOOLS)
        # Should have registered at least some tools
        assert len(tool_names) > 0


class TestSubagentSingleton:
    """Test singleton pattern."""

    def test_get_subagent_manager_returns_same(self):
        from subagent import get_subagent_manager, reset_subagent_manager

        reset_subagent_manager()
        m1 = get_subagent_manager()
        m2 = get_subagent_manager()
        assert m1 is m2
        reset_subagent_manager()

    def test_reset_clears_singleton(self):
        from subagent import get_subagent_manager, reset_subagent_manager

        m1 = get_subagent_manager()
        reset_subagent_manager()
        m2 = get_subagent_manager()
        assert m1 is not m2
        reset_subagent_manager()


class TestSpawnTaskTool:
    """Test the spawn_task tool."""

    def test_spawn_task_tool_exists(self):
        from tools import setup_default_tools

        registry = setup_default_tools()
        tool = registry.get("spawn_task")
        assert tool is not None
        assert tool.name == "spawn_task"

    def test_spawn_task_in_tier2(self):
        from tools.meta_tools import TIER_2_TOOLS

        assert "spawn_task" in TIER_2_TOOLS

    def test_spawn_task_in_categories(self):
        from tools.meta_tools import TOOL_CATEGORIES

        assert "sistema" in TOOL_CATEGORIES
        assert "spawn_task" in TOOL_CATEGORIES["sistema"]

    def test_spawn_task_requires_task_param(self):
        from tools.spawn_task import SpawnTaskTool
        from tools import ToolContext

        tool = SpawnTaskTool()
        context = ToolContext(
            user_phone="+5511999990000",
            session_id="test",
            timestamp="2026-02-10T12:00:00Z",
            storage=None,
        )
        result = tool.execute({"task": ""}, context)
        assert result.success is False

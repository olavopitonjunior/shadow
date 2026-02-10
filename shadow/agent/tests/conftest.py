"""
Shared pytest fixtures for Shadow agent tests.
"""

import os
import sys
import tempfile

import pytest

# Ensure the agent directory is on sys.path
_agent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _agent_dir not in sys.path:
    sys.path.insert(0, _agent_dir)

# Force SQLite backend for tests
os.environ["SHADOW_USE_SUPABASE"] = "false"
os.environ.setdefault("SHADOW_OWNER_E164", "+5511999990000")


@pytest.fixture
def owner_id():
    """Standard test owner phone number."""
    return "+5511999990000"


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite database path."""
    return str(tmp_path / "test_shadow.db")


@pytest.fixture
def sqlite_storage(tmp_db):
    """Fresh SqliteStorage with an isolated temp database."""
    from storage.sqlite_storage import SqliteStorage

    return SqliteStorage(db_path=tmp_db)


@pytest.fixture
def storage(sqlite_storage):
    """Alias for sqlite_storage - the default storage for tests."""
    return sqlite_storage


@pytest.fixture
def tool_context(storage, owner_id):
    """ToolContext wired to the test storage."""
    from tools import ToolContext

    return ToolContext(
        user_phone=owner_id,
        session_id="test-session",
        timestamp="2026-02-09T12:00:00Z",
        storage=storage,
    )


@pytest.fixture
def tool_registry():
    """Initialized tool registry with all default tools."""
    from tools import setup_default_tools

    return setup_default_tools()

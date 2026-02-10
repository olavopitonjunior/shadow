"""Fixtures for admin-api tests."""
import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _no_admin_token(monkeypatch):
    """Ensure ADMIN_API_TOKEN is not set so auth is skipped."""
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)


@pytest.fixture(autouse=True)
def _no_supabase(monkeypatch):
    """Ensure Supabase is not configured (use agent/sqlite fallback)."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)


@pytest.fixture()
def _with_storage(monkeypatch, tmp_path):
    """Set up real SQLite storage via agent import and seed usage data."""
    agent_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "..",
        "..",
        "shadow",
        "agent",
    )
    agent_dir = os.path.normpath(agent_dir)
    if agent_dir not in sys.path:
        sys.path.insert(0, agent_dir)

    db_path = str(tmp_path / "test_shadow.db")
    monkeypatch.setenv("SHADOW_DB_PATH", db_path)

    from storage import Storage

    storage = Storage()

    # Seed api usage data
    if hasattr(storage, "record_api_usage"):
        storage.record_api_usage(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            input_tokens=1500,
            output_tokens=500,
            session_id="test-session-1",
            operation="chat",
            cost_usd=0.012,
            latency_ms=1200,
            success=True,
        )
        storage.record_api_usage(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            input_tokens=2000,
            output_tokens=800,
            session_id="test-session-2",
            operation="chat",
            cost_usd=0.018,
            latency_ms=1500,
            success=True,
        )
        storage.record_api_usage(
            provider="google",
            model="gemini-2.5-flash-lite",
            input_tokens=500,
            output_tokens=200,
            session_id="test-session-1",
            operation="entity_extraction",
            cost_usd=0.001,
            latency_ms=400,
            success=True,
        )
        storage.record_api_usage(
            provider="openai",
            model="text-embedding-3-small",
            input_tokens=300,
            output_tokens=0,
            session_id="test-session-1",
            operation="embedding",
            cost_usd=0.0001,
            latency_ms=200,
            success=True,
        )
        storage.record_api_usage(
            provider="google",
            model="gemini-2.0-flash",
            input_tokens=1000,
            output_tokens=400,
            session_id="test-session-3",
            operation="summarization",
            cost_usd=0.002,
            latency_ms=600,
            success=False,
            error_message="Rate limit exceeded",
        )

    return storage


@pytest.fixture()
def client():
    """Create a TestClient for the admin-api app."""
    from main import app

    return TestClient(app)

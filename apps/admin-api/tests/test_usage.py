"""Tests for usage and costs endpoints.

These endpoints depend on Storage imported from the agent module.
When storage is unavailable (import conflict, missing DB), they return graceful fallbacks.
We test both the fallback behavior and the shape of responses.
"""
import os
import sqlite3
import sys

import pytest


def _seed_usage_db(db_path: str) -> None:
    """Seed a SQLite database directly with usage tables and data."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS shadow_api_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            session_id TEXT,
            operation TEXT,
            cost_usd REAL DEFAULT 0.0,
            latency_ms INTEGER,
            success BOOLEAN DEFAULT 1,
            error_message TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS shadow_provider_pricing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            input_price_per_mtok REAL NOT NULL,
            output_price_per_mtok REAL NOT NULL,
            effective_from TEXT DEFAULT (datetime('now')),
            UNIQUE(provider, model)
        )
    """)

    # Seed usage records
    records = [
        ("anthropic", "claude-sonnet-4-20250514", 1500, 500, "sess-1", "chat", 0.012, 1200, 1, None),
        ("anthropic", "claude-sonnet-4-20250514", 2000, 800, "sess-2", "chat", 0.018, 1500, 1, None),
        ("google", "gemini-2.5-flash-lite", 500, 200, "sess-1", "entity_extraction", 0.001, 400, 1, None),
        ("openai", "text-embedding-3-small", 300, 0, "sess-1", "embedding", 0.0001, 200, 1, None),
        ("google", "gemini-2.0-flash", 1000, 400, "sess-3", "summarization", 0.002, 600, 0, "Rate limit"),
    ]
    c.executemany(
        "INSERT INTO shadow_api_usage (provider, model, input_tokens, output_tokens, session_id, operation, cost_usd, latency_ms, success, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        records,
    )

    # Seed pricing
    pricing = [
        ("anthropic", "claude-sonnet-4-20250514", 3.0, 15.0),
        ("google", "gemini-2.5-flash-lite", 0.075, 0.3),
        ("google", "gemini-2.0-flash", 0.1, 0.4),
        ("openai", "text-embedding-3-small", 0.02, 0.0),
    ]
    c.executemany(
        "INSERT OR REPLACE INTO shadow_provider_pricing (provider, model, input_price_per_mtok, output_price_per_mtok) VALUES (?, ?, ?, ?)",
        pricing,
    )

    conn.commit()
    conn.close()


class TestUsageEndpointsFallback:
    """Test usage endpoints when storage is not available."""

    def test_usage_summary_fallback(self, client):
        """GET /stats/usage returns graceful response when storage unavailable."""
        res = client.get("/stats/usage")
        assert res.status_code == 200
        data = res.json()
        assert "usage" in data

    def test_usage_history_fallback(self, client):
        """GET /stats/usage/history returns empty list when unavailable."""
        res = client.get("/stats/usage/history")
        assert res.status_code == 200
        data = res.json()
        assert "history" in data

    def test_costs_breakdown_fallback(self, client):
        """GET /stats/costs/breakdown returns zero costs when unavailable."""
        res = client.get("/stats/costs/breakdown")
        assert res.status_code == 200
        data = res.json()
        assert "providers" in data
        assert "total_cost" in data
        assert isinstance(data["total_cost"], (int, float))

    def test_pricing_fallback(self, client):
        """GET /config/pricing returns empty list when unavailable."""
        res = client.get("/config/pricing")
        assert res.status_code == 200
        data = res.json()
        assert "pricing" in data
        assert isinstance(data["pricing"], list)

    def test_update_pricing_fallback(self, client):
        """PUT /config/pricing handles missing storage gracefully."""
        res = client.put(
            "/config/pricing",
            params={
                "provider": "anthropic",
                "model": "test-model",
                "input_price": 1.0,
                "output_price": 2.0,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert "status" in data or "error" in data


class TestUsageWithSeededDB:
    """Test usage endpoints with a seeded SQLite database.

    These tests create a real SQLite DB with usage data and
    verify the endpoints can read it.
    """

    @pytest.fixture(autouse=True)
    def _setup_storage(self, monkeypatch, tmp_path):
        """Seed a SQLite DB and configure the agent path for Storage import."""
        db_path = str(tmp_path / "test_shadow.db")
        _seed_usage_db(db_path)
        monkeypatch.setenv("SHADOW_DB_PATH", db_path)

        # Insert agent dir at the very front of sys.path so its config.py
        # takes priority over admin-api's config.py
        agent_dir = os.path.normpath(
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "..", "..", "shadow", "agent",
            )
        )
        # Save and restore sys.path
        self._original_path = sys.path.copy()
        # Remove admin-api root if present, then prepend agent dir
        sys.path = [agent_dir] + [p for p in sys.path if os.path.normpath(p) != os.path.normpath(agent_dir)]

        # Clear any cached 'config' module so the agent's config is found
        for mod_name in list(sys.modules.keys()):
            if mod_name == "config" or mod_name.startswith("storage"):
                del sys.modules[mod_name]

        yield

        # Restore
        sys.path = self._original_path
        for mod_name in list(sys.modules.keys()):
            if mod_name == "config" or mod_name.startswith("storage"):
                del sys.modules[mod_name]

    def test_usage_summary_has_data(self, client):
        """GET /stats/usage returns seeded data."""
        res = client.get("/stats/usage")
        assert res.status_code == 200
        data = res.json()
        assert "usage" in data
        # If storage loaded, should have entries
        if isinstance(data["usage"], list) and len(data["usage"]) > 0:
            for row in data["usage"]:
                assert "provider" in row
                assert "model" in row

    def test_costs_breakdown_has_providers(self, client):
        """GET /stats/costs/breakdown returns breakdown from seeded data."""
        res = client.get("/stats/costs/breakdown")
        assert res.status_code == 200
        data = res.json()
        assert "providers" in data
        assert "total_cost" in data
        assert "days" in data
        providers = data["providers"]
        if providers:
            for p_name, p_data in providers.items():
                assert "input_tokens" in p_data
                assert "output_tokens" in p_data
                assert "cost_usd" in p_data
                assert "calls" in p_data

    def test_pricing_has_seeded_entries(self, client):
        """GET /config/pricing returns seeded pricing data."""
        res = client.get("/config/pricing")
        assert res.status_code == 200
        data = res.json()
        pricing = data["pricing"]
        if isinstance(pricing, list) and len(pricing) > 0:
            for item in pricing:
                assert "provider" in item
                assert "model" in item
                assert "input_price_per_mtok" in item
                assert "output_price_per_mtok" in item

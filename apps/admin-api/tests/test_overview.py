"""Tests for overview endpoints."""


def test_stats_overview_returns_shape(client):
    """GET /stats/overview returns expected fields even without Supabase/Agent."""
    res = client.get("/stats/overview")
    assert res.status_code == 200
    data = res.json()
    assert "users_total" in data
    assert "users_active_24h" in data
    assert "messages_total" in data
    assert "messages_24h" in data
    assert "tasks_pending" in data
    assert "appointments_upcoming" in data
    assert "timestamp" in data


def test_stats_integrations(client):
    """GET /stats/integrations returns provider status."""
    res = client.get("/stats/integrations")
    assert res.status_code == 200
    data = res.json()
    assert "baileys" in data
    assert "enabled" in data["baileys"]


def test_stats_whatsapp(client):
    """GET /stats/whatsapp returns connections list."""
    res = client.get("/stats/whatsapp")
    assert res.status_code == 200
    data = res.json()
    assert "connections" in data
    assert isinstance(data["connections"], list)
    # Baileys always present (even if error)
    assert len(data["connections"]) >= 1
    conn = data["connections"][0]
    assert conn["provider"] == "baileys"
    assert "status" in conn
    assert "checked_at" in conn


def test_stats_tables_no_supabase(client):
    """GET /stats/tables returns zeros without Supabase."""
    res = client.get("/stats/tables")
    assert res.status_code == 200
    data = res.json()
    assert "tables" in data
    assert data["source"] == "no_storage"


def test_stats_costs_fallback(client):
    """GET /stats/costs returns token counts (fallback without Supabase)."""
    res = client.get("/stats/costs")
    assert res.status_code == 200
    data = res.json()
    assert "input_tokens" in data
    assert "output_tokens" in data
    assert isinstance(data["input_tokens"], int)
    assert isinstance(data["output_tokens"], int)

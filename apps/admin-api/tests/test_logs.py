"""Tests for logs endpoints."""


def test_webhook_logs_no_supabase(client):
    """GET /logs/webhooks returns empty list without Supabase."""
    res = client.get("/logs/webhooks")
    assert res.status_code == 200
    data = res.json()
    assert "logs" in data
    assert isinstance(data["logs"], list)
    assert data["source"] == "no_storage"


def test_error_logs(client):
    """GET /logs/errors returns placeholder."""
    res = client.get("/logs/errors")
    assert res.status_code == 200
    data = res.json()
    assert "errors" in data
    assert isinstance(data["errors"], list)

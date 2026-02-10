"""Tests for config endpoints."""
import os


def test_config_environment(client):
    """GET /config/environment returns env var status."""
    res = client.get("/config/environment")
    assert res.status_code == 200
    data = res.json()
    assert "variables" in data
    variables = data["variables"]
    # Should check all 11 expected vars
    expected_vars = [
        "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
        "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY",
        "SHADOW_GATEWAY_URL", "SHADOW_GATEWAY_PORT", "SHADOW_AGENT_PORT",
        "OWNER_PHONE", "ADMIN_API_TOKEN",
    ]
    for var in expected_vars:
        assert var in variables, f"{var} missing from environment response"
        assert "configured" in variables[var]
        assert isinstance(variables[var]["configured"], bool)


def test_config_environment_masks_values(client, monkeypatch):
    """Configured vars show masked preview, not full value."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-1234567890abcdef")
    res = client.get("/config/environment")
    data = res.json()
    anthropic = data["variables"]["ANTHROPIC_API_KEY"]
    assert anthropic["configured"] is True
    assert "preview" in anthropic
    # Should NOT contain full key
    assert anthropic["preview"] != "sk-ant-1234567890abcdef"
    assert "..." in anthropic["preview"]


def test_config_providers(client):
    """GET /config/providers returns provider status."""
    res = client.get("/config/providers")
    assert res.status_code == 200
    data = res.json()
    assert "providers" in data
    providers = data["providers"]
    assert "anthropic" in providers
    assert "google" in providers
    assert "openai" in providers
    for name, info in providers.items():
        assert "configured" in info
        assert "models" in info
        assert isinstance(info["models"], list)

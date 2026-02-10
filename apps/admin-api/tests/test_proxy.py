"""Tests for proxy endpoints (graceful failure when services are off)."""


def test_proxy_agent_status_unavailable(client):
    """GET /proxy/agent/status returns error when agent is off."""
    res = client.get("/proxy/agent/status")
    assert res.status_code == 200
    data = res.json()
    # Either real response or graceful error
    assert "status" in data or "error" in data


def test_proxy_gateway_status_unavailable(client):
    """GET /proxy/gateway/status returns a response (error or data)."""
    res = client.get("/proxy/gateway/status")
    assert res.status_code == 200
    data = res.json()
    # Gateway may return {connected, phone, ...} or {status, ...} or {error, ...}
    assert isinstance(data, dict)


def test_proxy_agent_sessions_unavailable(client):
    """GET /proxy/agent/sessions handles agent being offline."""
    res = client.get("/proxy/agent/sessions")
    assert res.status_code == 200
    data = res.json()
    assert "sessions" in data or "error" in data

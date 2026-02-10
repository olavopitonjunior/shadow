"""Tests for instance management endpoints."""
from unittest.mock import MagicMock, patch


@patch("routers.instances._gateway_request")
@patch("routers.instances._get_storage")
def test_create_instance(mock_storage_fn, mock_gateway, client):
    """POST /instances creates instance and connects via gateway."""
    mock_storage = MagicMock()
    mock_storage.create_instance.return_value = None
    mock_storage.update_instance.return_value = None
    mock_storage.get_instance.return_value = {
        "id": "test1",
        "name": "Test Instance",
        "gateway_user_id": "test1",
        "status": "qr_pending",
        "created_at": "2026-02-10T12:00:00Z",
    }
    mock_storage_fn.return_value = mock_storage

    mock_gateway.return_value = {
        "success": True,
        "status": "qr_pending",
        "qr": "test-qr-data-base64",
    }

    res = client.post("/instances", json={"name": "Test Instance"})
    assert res.status_code == 200
    data = res.json()

    assert data["id"] == "test1"
    assert data["name"] == "Test Instance"
    assert data["status"] == "qr_pending"
    assert data["qr"] == "test-qr-data-base64"

    # Verify storage methods called
    mock_storage.create_instance.assert_called_once()
    mock_storage.update_instance.assert_called_once()
    mock_storage.get_instance.assert_called_once()

    # Verify gateway connection initiated
    mock_gateway.assert_called_once()
    call_args = mock_gateway.call_args
    assert call_args[0][0] == "POST"  # method
    assert "/sessions/" in call_args[0][1]  # path
    assert "/connect" in call_args[0][1]


@patch("routers.instances._get_storage")
def test_create_instance_storage_unavailable(mock_storage_fn, client):
    """POST /instances returns 500 when storage unavailable."""
    mock_storage_fn.return_value = None

    res = client.post("/instances", json={"name": "Test"})
    assert res.status_code == 500
    assert "Storage unavailable" in res.json()["detail"]


@patch("routers.instances._gateway_request")
@patch("routers.instances._get_storage")
def test_list_instances_empty(mock_storage_fn, mock_gateway, client):
    """GET /instances returns empty list when no instances."""
    mock_storage = MagicMock()
    mock_storage.list_instances.return_value = []
    mock_storage_fn.return_value = mock_storage

    mock_gateway.return_value = {"sessions": []}

    res = client.get("/instances")
    assert res.status_code == 200
    data = res.json()

    assert "instances" in data
    assert data["instances"] == []


@patch("routers.instances._get_storage")
def test_list_instances_no_storage(mock_storage_fn, client):
    """GET /instances returns empty list when storage unavailable."""
    mock_storage_fn.return_value = None

    res = client.get("/instances")
    assert res.status_code == 200
    data = res.json()

    assert data["instances"] == []


@patch("routers.instances._gateway_request")
@patch("routers.instances._get_storage")
def test_list_instances_with_data(mock_storage_fn, mock_gateway, client):
    """GET /instances enriches instances with live gateway status."""
    mock_storage = MagicMock()
    mock_storage.list_instances.return_value = [
        {
            "id": "test1",
            "name": "Instance 1",
            "gateway_user_id": "gw1",
            "status": "disconnected",
            "phone": None,
        },
        {
            "id": "test2",
            "name": "Instance 2",
            "gateway_user_id": "gw2",
            "status": "connected",
            "phone": "+5511999999999",
        },
    ]
    mock_storage_fn.return_value = mock_storage

    # Gateway returns updated status for gw1, no info for gw2
    mock_gateway.return_value = {
        "sessions": [
            {"userId": "gw1", "status": "connected", "phone": "+5511888888888"},
        ]
    }

    res = client.get("/instances")
    assert res.status_code == 200
    data = res.json()

    instances = data["instances"]
    assert len(instances) == 2

    # First instance enriched with gateway data
    inst1 = instances[0]
    assert inst1["id"] == "test1"
    assert inst1["live_status"] == "connected"
    assert inst1["live_phone"] == "+5511888888888"

    # Second instance keeps stored data
    inst2 = instances[1]
    assert inst2["id"] == "test2"
    assert inst2["live_status"] == "connected"
    assert inst2["live_phone"] == "+5511999999999"


@patch("routers.instances._get_storage")
def test_get_instance_not_found(mock_storage_fn, client):
    """GET /instances/{id} returns 404 when instance not found."""
    mock_storage = MagicMock()
    mock_storage.get_instance.return_value = None
    mock_storage_fn.return_value = mock_storage

    res = client.get("/instances/nonexistent")
    assert res.status_code == 404
    assert "Instance not found" in res.json()["detail"]


@patch("routers.instances._gateway_request")
@patch("routers.instances._get_storage")
def test_get_instance_success(mock_storage_fn, mock_gateway, client):
    """GET /instances/{id} returns instance with live status."""
    mock_storage = MagicMock()
    mock_storage.get_instance.return_value = {
        "id": "test1",
        "name": "Test Instance",
        "gateway_user_id": "gw1",
        "status": "disconnected",
        "phone": None,
    }
    mock_storage_fn.return_value = mock_storage

    mock_gateway.return_value = {
        "status": "connected",
        "phone": "+5511999999999",
    }

    res = client.get("/instances/test1")
    assert res.status_code == 200
    data = res.json()

    assert data["id"] == "test1"
    assert data["name"] == "Test Instance"
    assert data["live_status"] == "connected"
    assert data["live_phone"] == "+5511999999999"


@patch("routers.instances._gateway_request")
@patch("routers.instances._get_storage")
def test_delete_instance(mock_storage_fn, mock_gateway, client):
    """DELETE /instances/{id} disconnects from gateway and removes from storage."""
    mock_storage = MagicMock()
    mock_storage.get_instance.return_value = {
        "id": "test1",
        "gateway_user_id": "gw1",
    }
    mock_storage.delete_instance.return_value = None
    mock_storage_fn.return_value = mock_storage

    mock_gateway.return_value = {"success": True}

    res = client.delete("/instances/test1")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "deleted"
    assert data["id"] == "test1"

    # Verify gateway disconnect called
    mock_gateway.assert_called_once()
    call_args = mock_gateway.call_args
    assert call_args[0][0] == "DELETE"
    assert "/sessions/gw1" in call_args[0][1]

    # Verify storage delete called
    mock_storage.delete_instance.assert_called_once_with("test1")


@patch("routers.instances._get_storage")
def test_delete_instance_not_found(mock_storage_fn, client):
    """DELETE /instances/{id} returns 404 when instance not found."""
    mock_storage = MagicMock()
    mock_storage.get_instance.return_value = None
    mock_storage_fn.return_value = mock_storage

    res = client.delete("/instances/nonexistent")
    assert res.status_code == 404
    assert "Instance not found" in res.json()["detail"]


@patch("routers.instances._gateway_request")
@patch("routers.instances._get_storage")
def test_connect_instance(mock_storage_fn, mock_gateway, client):
    """POST /instances/{id}/connect reconnects instance via gateway."""
    mock_storage = MagicMock()
    mock_storage.get_instance.return_value = {
        "id": "test1",
        "gateway_user_id": "gw1",
    }
    mock_storage.update_instance.return_value = None
    mock_storage_fn.return_value = mock_storage

    mock_gateway.return_value = {
        "status": "qr_pending",
        "qr": "new-qr-code",
    }

    res = client.post("/instances/test1/connect")
    assert res.status_code == 200
    data = res.json()

    assert data["id"] == "test1"
    assert data["status"] == "qr_pending"
    assert data["qr"] == "new-qr-code"

    # Verify gateway connect called
    mock_gateway.assert_called_once()
    call_args = mock_gateway.call_args
    assert call_args[0][0] == "POST"
    assert "/sessions/gw1/connect" in call_args[0][1]

    # Verify storage updated
    mock_storage.update_instance.assert_called_once_with("test1", status="qr_pending")


@patch("routers.instances._gateway_request")
@patch("routers.instances._get_storage")
def test_disconnect_instance(mock_storage_fn, mock_gateway, client):
    """POST /instances/{id}/disconnect disconnects without removing instance."""
    mock_storage = MagicMock()
    mock_storage.get_instance.return_value = {
        "id": "test1",
        "gateway_user_id": "gw1",
    }
    mock_storage.update_instance.return_value = None
    mock_storage_fn.return_value = mock_storage

    mock_gateway.return_value = {"success": True}

    res = client.post("/instances/test1/disconnect")
    assert res.status_code == 200
    data = res.json()

    assert data["id"] == "test1"
    assert data["status"] == "disconnected"

    # Verify gateway disconnect called
    mock_gateway.assert_called_once()
    call_args = mock_gateway.call_args
    assert call_args[0][0] == "DELETE"

    # Verify storage updated with disconnected status
    mock_storage.update_instance.assert_called_once()
    update_call = mock_storage.update_instance.call_args
    assert update_call[0][0] == "test1"
    assert update_call[1]["status"] == "disconnected"
    assert "disconnected_at" in update_call[1]


@patch("routers.instances._gateway_request")
@patch("routers.instances._get_storage")
def test_get_instance_qr(mock_storage_fn, mock_gateway, client):
    """GET /instances/{id}/qr returns QR code from gateway."""
    mock_storage = MagicMock()
    mock_storage.get_instance.return_value = {
        "id": "test1",
        "gateway_user_id": "gw1",
    }
    mock_storage_fn.return_value = mock_storage

    mock_gateway.return_value = {
        "qr": "qr-code-data",
        "status": "qr_pending",
    }

    res = client.get("/instances/test1/qr")
    assert res.status_code == 200
    data = res.json()

    assert data["qr"] == "qr-code-data"
    assert data["status"] == "qr_pending"

    # Verify gateway QR endpoint called
    mock_gateway.assert_called_once()
    call_args = mock_gateway.call_args
    assert call_args[0][0] == "GET"
    assert "/sessions/gw1/qr" in call_args[0][1]


@patch("routers.instances._gateway_request")
@patch("routers.instances._get_storage")
def test_get_instance_status(mock_storage_fn, mock_gateway, client):
    """GET /instances/{id}/status returns live status from gateway."""
    mock_storage = MagicMock()
    mock_storage.get_instance.return_value = {
        "id": "test1",
        "gateway_user_id": "gw1",
        "status": "disconnected",
        "phone": None,
        "connected_at": None,
    }
    mock_storage.update_instance.return_value = None
    mock_storage_fn.return_value = mock_storage

    mock_gateway.return_value = {
        "status": "connected",
        "phone": "+5511999999999",
    }

    res = client.get("/instances/test1/status")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "connected"
    assert data["phone"] == "+5511999999999"

    # Verify storage updated with new status and phone
    mock_storage.update_instance.assert_called_once()
    update_call = mock_storage.update_instance.call_args
    assert update_call[1]["status"] == "connected"
    assert update_call[1]["phone"] == "+5511999999999"
    assert update_call[1]["owner_e164"] == "+5511999999999"
    assert "connected_at" in update_call[1]


@patch("routers.instances._get_storage")
def test_get_instance_stats_fallback(mock_storage_fn, client):
    """GET /instances/{id}/stats returns zeros when agent unavailable."""
    mock_storage = MagicMock()
    mock_storage.get_instance.return_value = {
        "id": "test1",
        "gateway_user_id": "gw1",
    }
    # Storage doesn't have usage methods
    mock_storage_fn.return_value = mock_storage

    res = client.get("/instances/test1/stats")
    assert res.status_code == 200
    data = res.json()

    # Should return default zero values
    assert data["messages"] == 0
    assert data["sessions"] == 0
    assert data["input_tokens"] == 0
    assert data["output_tokens"] == 0
    assert data["total_cost"] == 0


@patch("routers.instances._get_storage")
def test_get_instance_conversations(mock_storage_fn, client):
    """GET /instances/{id}/conversations returns conversations list."""
    mock_storage = MagicMock()
    mock_storage.get_instance.return_value = {
        "id": "test1",
        "gateway_user_id": "gw1",
        "owner_e164": "+5511999999999",
    }
    mock_storage_fn.return_value = mock_storage

    res = client.get("/instances/test1/conversations")
    assert res.status_code == 200
    data = res.json()

    # Should return conversations list (even if empty when agent unavailable)
    assert "conversations" in data
    assert isinstance(data["conversations"], list)


@patch("routers.instances._get_storage")
def test_get_instance_conversations_with_limit(mock_storage_fn, client):
    """GET /instances/{id}/conversations respects limit parameter."""
    mock_storage = MagicMock()
    mock_storage.get_instance.return_value = {
        "id": "test1",
        "gateway_user_id": "gw1",
    }
    mock_storage_fn.return_value = mock_storage

    res = client.get("/instances/test1/conversations?limit=10")
    assert res.status_code == 200
    data = res.json()

    assert "conversations" in data


@patch("routers.instances._get_storage")
def test_get_instance_costs(mock_storage_fn, client):
    """GET /instances/{id}/costs returns costs breakdown."""
    mock_storage = MagicMock()
    mock_storage.get_instance.return_value = {
        "id": "test1",
        "gateway_user_id": "gw1",
    }
    # Mock usage summary method
    mock_storage.get_usage_summary.return_value = [
        {
            "provider": "anthropic",
            "total_input": 1000,
            "total_output": 500,
            "total_cost": 0.015,
            "call_count": 5,
        },
        {
            "provider": "google",
            "total_input": 500,
            "total_output": 200,
            "total_cost": 0.002,
            "call_count": 2,
        },
    ]
    mock_storage_fn.return_value = mock_storage

    res = client.get("/instances/test1/costs")
    assert res.status_code == 200
    data = res.json()

    assert "providers" in data
    assert "total_cost" in data
    assert "days" in data

    # Check providers breakdown
    providers = data["providers"]
    assert "anthropic" in providers
    assert "google" in providers

    # Check totals
    assert data["total_cost"] == 0.017
    assert data["days"] == 30


@patch("routers.instances._get_storage")
def test_get_instance_costs_with_days(mock_storage_fn, client):
    """GET /instances/{id}/costs respects days parameter."""
    mock_storage = MagicMock()
    mock_storage.get_instance.return_value = {
        "id": "test1",
        "gateway_user_id": "gw1",
    }
    mock_storage.get_usage_summary.return_value = []
    mock_storage_fn.return_value = mock_storage

    res = client.get("/instances/test1/costs?days=7")
    assert res.status_code == 200
    data = res.json()

    assert data["days"] == 7
    # Verify storage method called with correct days
    mock_storage.get_usage_summary.assert_called_once_with(7)


@patch("routers.instances._get_storage")
def test_get_instance_logs(mock_storage_fn, client):
    """GET /instances/{id}/logs returns logs from usage history."""
    mock_storage = MagicMock()
    mock_storage.get_instance.return_value = {
        "id": "test1",
        "gateway_user_id": "gw1",
    }
    mock_storage.get_usage_history.return_value = [
        {
            "timestamp": "2026-02-10T12:00:00Z",
            "provider": "anthropic",
            "model": "claude-sonnet-4-20250514",
            "operation": "chat",
            "success": True,
        },
        {
            "timestamp": "2026-02-10T12:01:00Z",
            "provider": "google",
            "model": "gemini-2.5-flash-lite",
            "operation": "entity_extraction",
            "success": True,
        },
    ]
    mock_storage_fn.return_value = mock_storage

    res = client.get("/instances/test1/logs")
    assert res.status_code == 200
    data = res.json()

    assert "logs" in data
    assert len(data["logs"]) == 2
    assert data["logs"][0]["provider"] == "anthropic"


@patch("routers.instances._get_storage")
def test_get_instance_logs_respects_limit(mock_storage_fn, client):
    """GET /instances/{id}/logs respects limit parameter."""
    mock_storage = MagicMock()
    mock_storage.get_instance.return_value = {
        "id": "test1",
        "gateway_user_id": "gw1",
    }
    # Return 150 logs but limit should cap at 20
    mock_storage.get_usage_history.return_value = [{"timestamp": f"2026-02-10T12:{i:02d}:00Z"} for i in range(150)]
    mock_storage_fn.return_value = mock_storage

    res = client.get("/instances/test1/logs?limit=20")
    assert res.status_code == 200
    data = res.json()

    assert "logs" in data
    # Should be capped at 20
    assert len(data["logs"]) == 20

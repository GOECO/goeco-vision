import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def _create_delivery(tracking="TRK-001"):
    return client.post("/api/v1/deliveries/", json={
        "tracking_code": tracking,
        "shipper_id": "shipper-1",
        "recipient_id": "resident-42",
        "building_id": "building-A",
        "unit_number": "12B",
    })


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_delivery():
    r = _create_delivery("TRK-100")
    assert r.status_code == 201
    data = r.json()
    assert data["tracking_code"] == "TRK-100"
    assert data["status"] == "pending"


def test_get_delivery_not_found():
    r = client.get("/api/v1/deliveries/9999")
    assert r.status_code == 404


def test_delivery_event_history_created_on_delivery():
    r = _create_delivery("TRK-200")
    delivery_id = r.json()["id"]

    events_r = client.get(f"/api/v1/deliveries/{delivery_id}/events")
    assert events_r.status_code == 200
    events = events_r.json()
    assert len(events) == 1
    assert events[0]["event_type"] == "created"


def test_add_manual_event():
    r = _create_delivery("TRK-300")
    delivery_id = r.json()["id"]

    add_r = client.post(f"/api/v1/deliveries/{delivery_id}/events", json={
        "event_type": "dispute",
        "description": "Package arrived damaged",
        "actor_id": "resident-42",
        "actor_role": "recipient",
    })
    assert add_r.status_code == 201
    event = add_r.json()
    assert event["event_type"] == "dispute"
    assert event["actor_role"] == "recipient"

    events_r = client.get(f"/api/v1/deliveries/{delivery_id}/events")
    assert len(events_r.json()) == 2


def test_status_change_creates_event():
    r = _create_delivery("TRK-400")
    delivery_id = r.json()["id"]

    client.patch(f"/api/v1/deliveries/{delivery_id}", json={"status": "arrived"})

    events = client.get(f"/api/v1/deliveries/{delivery_id}/events").json()
    event_types = [e["event_type"] for e in events]
    assert "status_changed" in event_types

from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import List
from datetime import datetime

from app.schemas.delivery import (
    DeliveryCreate,
    DeliveryUpdate,
    DeliveryResponse,
    DeliveryEventCreate,
    DeliveryEventResponse,
)
from app.services.verification import verify_delivery_image

router = APIRouter(prefix="/deliveries", tags=["deliveries"])

# In-memory store — TODO: replace with async SQLAlchemy session (see models/delivery.py)
_deliveries: dict = {}
_events: dict = {}
_next_id: int = 1
_next_event_id: int = 1


@router.post("/", response_model=DeliveryResponse, status_code=201)
async def create_delivery(payload: DeliveryCreate):
    global _next_id
    now = datetime.utcnow()
    delivery = {
        "id": _next_id,
        "tracking_code": payload.tracking_code,
        "shipper_id": payload.shipper_id,
        "recipient_id": payload.recipient_id,
        "building_id": payload.building_id,
        "unit_number": payload.unit_number,
        "status": "pending",
        "camera_snapshot_url": None,
        "ai_confidence_score": None,
        "verified_at": None,
        "verification_note": None,
        "created_at": now,
        "updated_at": now,
    }
    _deliveries[_next_id] = delivery
    _next_id += 1
    _log_event(delivery["id"], "created", "Delivery registered", actor_id=payload.shipper_id, actor_role="shipper")
    return delivery


@router.get("/{delivery_id}", response_model=DeliveryResponse)
async def get_delivery(delivery_id: int):
    delivery = _deliveries.get(delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    return delivery


@router.patch("/{delivery_id}", response_model=DeliveryResponse)
async def update_delivery(delivery_id: int, payload: DeliveryUpdate):
    delivery = _deliveries.get(delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")

    old_status = delivery["status"]
    updates = payload.model_dump(exclude_none=True)
    delivery.update(updates)
    delivery["updated_at"] = datetime.utcnow()

    if "status" in updates and updates["status"] != old_status:
        _log_event(delivery_id, "status_changed", f"Status changed: {old_status} → {updates['status']}")

    return delivery


@router.post("/{delivery_id}/verify", response_model=DeliveryResponse)
async def verify_delivery(delivery_id: int, image: UploadFile = File(...)):
    """Verify a delivery by uploading a camera snapshot for AI analysis."""
    delivery = _deliveries.get(delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")

    image_bytes = await image.read()
    result = await verify_delivery_image(image_bytes, delivery["shipper_id"])

    delivery["ai_confidence_score"] = result.confidence
    delivery["verification_note"] = result.note
    delivery["updated_at"] = datetime.utcnow()

    if result.verified:
        delivery["status"] = "verified"
        delivery["verified_at"] = datetime.utcnow()
        _log_event(delivery_id, "ai_verified", f"AI verified with confidence {result.confidence:.2f}")
    else:
        _log_event(delivery_id, "ai_unverified", result.note)

    return delivery


@router.get("/{delivery_id}/events", response_model=List[DeliveryEventResponse])
async def get_delivery_events(delivery_id: int):
    """Return the full event history for a delivery."""
    if delivery_id not in _deliveries:
        raise HTTPException(status_code=404, detail="Delivery not found")
    return [e for e in _events.values() if e["delivery_id"] == delivery_id]


@router.post("/{delivery_id}/events", response_model=DeliveryEventResponse, status_code=201)
async def add_delivery_event(delivery_id: int, payload: DeliveryEventCreate):
    """Manually append an event to a delivery's history (e.g. dispute, note)."""
    if delivery_id not in _deliveries:
        raise HTTPException(status_code=404, detail="Delivery not found")
    return _log_event(
        delivery_id,
        payload.event_type,
        payload.description,
        actor_id=payload.actor_id,
        actor_role=payload.actor_role,
        snapshot_url=payload.snapshot_url,
    )


def _log_event(
    delivery_id: int,
    event_type: str,
    description: str = None,
    actor_id: str = None,
    actor_role: str = None,
    snapshot_url: str = None,
) -> dict:
    global _next_event_id
    event = {
        "id": _next_event_id,
        "delivery_id": delivery_id,
        "event_type": event_type,
        "description": description,
        "actor_id": actor_id,
        "actor_role": actor_role,
        "snapshot_url": snapshot_url,
        "occurred_at": datetime.utcnow(),
    }
    _events[_next_event_id] = event
    _next_event_id += 1
    return event

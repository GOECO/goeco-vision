import json
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.delivery import Delivery, DeliveryEvent, DeliveryStatus
from app.schemas.delivery import (
    DeliveryCreate,
    DeliveryUpdate,
    DeliveryResponse,
    DeliveryEventCreate,
    DeliveryEventResponse,
    VerifyResponse,
)
from app.services.verification import verify_delivery_image

router = APIRouter(prefix="/deliveries", tags=["deliveries"])


async def _get_or_404(delivery_id: int, db: AsyncSession) -> Delivery:
    result = await db.execute(
        select(Delivery)
        .where(Delivery.id == delivery_id)
        .options(selectinload(Delivery.events))
    )
    delivery = result.scalar_one_or_none()
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    return delivery


async def _log_event(
    db: AsyncSession,
    delivery_id: int,
    event_type: str,
    description: str = None,
    actor_id: str = None,
    actor_role: str = None,
    snapshot_url: str = None,
) -> DeliveryEvent:
    event = DeliveryEvent(
        delivery_id=delivery_id,
        event_type=event_type,
        description=description,
        actor_id=actor_id,
        actor_role=actor_role,
        snapshot_url=snapshot_url,
        occurred_at=datetime.utcnow(),
    )
    db.add(event)
    await db.flush()
    return event


@router.post("/", response_model=DeliveryResponse, status_code=201)
async def create_delivery(payload: DeliveryCreate, db: AsyncSession = Depends(get_db)):
    delivery = Delivery(
        tracking_code=payload.tracking_code,
        shipper_id=payload.shipper_id,
        recipient_id=payload.recipient_id,
        building_id=payload.building_id,
        unit_number=payload.unit_number,
        status=DeliveryStatus.PENDING,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(delivery)
    await db.flush()
    await _log_event(db, delivery.id, "created", "Delivery registered", actor_id=payload.shipper_id, actor_role="shipper")
    await db.commit()
    await db.refresh(delivery)
    return delivery


@router.get("/", response_model=List[DeliveryResponse])
async def list_deliveries(
    building_id: str = None,
    status: DeliveryStatus = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    query = select(Delivery)
    if building_id:
        query = query.where(Delivery.building_id == building_id)
    if status:
        query = query.where(Delivery.status == status)
    query = query.order_by(Delivery.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{delivery_id}", response_model=DeliveryResponse)
async def get_delivery(delivery_id: int, db: AsyncSession = Depends(get_db)):
    return await _get_or_404(delivery_id, db)


@router.patch("/{delivery_id}", response_model=DeliveryResponse)
async def update_delivery(
    delivery_id: int, payload: DeliveryUpdate, db: AsyncSession = Depends(get_db)
):
    delivery = await _get_or_404(delivery_id, db)
    updates = payload.model_dump(exclude_none=True)

    old_status = delivery.status
    for key, value in updates.items():
        setattr(delivery, key, value)
    delivery.updated_at = datetime.utcnow()

    if "status" in updates and updates["status"] != old_status:
        await _log_event(
            db, delivery_id, "status_changed",
            f"Status: {old_status.value} → {updates['status']}"
        )

    await db.commit()
    await db.refresh(delivery)
    return delivery


@router.post("/{delivery_id}/verify", response_model=VerifyResponse)
async def verify_delivery(
    delivery_id: int,
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload ảnh camera — YOLO phân tích và xác thực giao nhận tự động."""
    delivery = await _get_or_404(delivery_id, db)
    image_bytes = await image.read()

    result = await verify_delivery_image(image_bytes, delivery.shipper_id)

    delivery.ai_confidence_score = result.confidence
    delivery.verification_note = result.note
    delivery.ai_detection_detail = json.dumps(result.detail, ensure_ascii=False)
    delivery.updated_at = datetime.utcnow()

    if result.verified:
        delivery.status = DeliveryStatus.VERIFIED
        delivery.verified_at = datetime.utcnow()
        await _log_event(
            db, delivery_id, "ai_verified",
            f"YOLO xác thực — confidence {result.confidence:.0%}",
            snapshot_url=image.filename,
        )
    else:
        await _log_event(db, delivery_id, "ai_unverified", result.note)

    await db.commit()
    await db.refresh(delivery)
    return VerifyResponse(delivery=delivery, detection=result.detail)


@router.get("/{delivery_id}/events", response_model=List[DeliveryEventResponse])
async def get_delivery_events(delivery_id: int, db: AsyncSession = Depends(get_db)):
    await _get_or_404(delivery_id, db)
    result = await db.execute(
        select(DeliveryEvent)
        .where(DeliveryEvent.delivery_id == delivery_id)
        .order_by(DeliveryEvent.occurred_at)
    )
    return result.scalars().all()


@router.post("/{delivery_id}/events", response_model=DeliveryEventResponse, status_code=201)
async def add_delivery_event(
    delivery_id: int, payload: DeliveryEventCreate, db: AsyncSession = Depends(get_db)
):
    """Thêm sự kiện thủ công (khiếu nại, ghi chú, tranh chấp...)."""
    await _get_or_404(delivery_id, db)
    event = await _log_event(
        db, delivery_id,
        payload.event_type,
        payload.description,
        actor_id=payload.actor_id,
        actor_role=payload.actor_role,
        snapshot_url=payload.snapshot_url,
    )
    await db.commit()
    await db.refresh(event)
    return event

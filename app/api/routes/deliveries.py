import json
import os
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.delivery import Delivery, DeliveryEvent, DeliveryStatus
from app.models.shipper import ShipperProfile
from app.schemas.delivery import (
    DeliveryCreate,
    DeliveryUpdate,
    DeliveryResponse,
    DeliveryEventCreate,
    DeliveryEventResponse,
    VerifyResponse,
)
from app.services.verification import verify_delivery_image
from app.services.image_utils import draw_detections, image_to_base64
from app.api.routes.ws import manager as ws_manager

router = APIRouter(prefix="/deliveries", tags=["deliveries"])

SNAPSHOT_DIR = "uploads/verifications"
os.makedirs(SNAPSHOT_DIR, exist_ok=True)


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
    await ws_manager.broadcast("delivery_created", {"id": delivery.id, "tracking_code": delivery.tracking_code, "building_id": delivery.building_id})
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
    await ws_manager.broadcast("delivery_updated", {"id": delivery.id, "status": delivery.status.value, "building_id": delivery.building_id})
    return delivery


@router.post("/{delivery_id}/verify", response_model=VerifyResponse)
async def verify_delivery(
    delivery_id: int,
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload ảnh camera — YOLO + Face ID phân tích và xác thực giao nhận tự động."""
    delivery = await _get_or_404(delivery_id, db)
    image_bytes = await image.read()

    # Lưu ảnh gốc vào disk
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    snapshot_filename = f"{delivery_id}_{ts}.jpg"
    snapshot_path = os.path.join(SNAPSHOT_DIR, snapshot_filename)
    with open(snapshot_path, "wb") as f:
        f.write(image_bytes)
    snapshot_url = f"/uploads/verifications/{snapshot_filename}"

    # Lấy face reference nếu shipper đã đăng ký Face ID
    shipper_result = await db.execute(
        select(ShipperProfile).where(ShipperProfile.shipper_id == delivery.shipper_id)
    )
    shipper = shipper_result.scalar_one_or_none()
    face_ref = shipper.face_embedding if shipper else None

    result = await verify_delivery_image(image_bytes, delivery.shipper_id, face_reference_json=face_ref)

    # Lưu ảnh đã annotate (bboxes) vào disk
    try:
        annotated_bytes = draw_detections(image_bytes, result.detail)
        annotated_path = os.path.join(SNAPSHOT_DIR, f"{delivery_id}_{ts}_annotated.jpg")
        with open(annotated_path, "wb") as f:
            f.write(annotated_bytes)
        annotated_url = f"/uploads/verifications/{delivery_id}_{ts}_annotated.jpg"
    except Exception:
        annotated_url = snapshot_url

    delivery.ai_confidence_score = result.confidence
    delivery.verification_note = result.note
    delivery.ai_detection_detail = json.dumps(result.detail, ensure_ascii=False)
    delivery.camera_snapshot_url = annotated_url
    delivery.updated_at = datetime.utcnow()

    if result.verified:
        delivery.status = DeliveryStatus.VERIFIED
        delivery.verified_at = datetime.utcnow()
        await _log_event(
            db, delivery_id, "ai_verified",
            f"YOLO xác thực — confidence {result.confidence:.0%}",
            snapshot_url=annotated_url,
        )
    else:
        await _log_event(db, delivery_id, "ai_unverified", result.note, snapshot_url=snapshot_url)

    await db.commit()
    await db.refresh(delivery)
    await ws_manager.broadcast(
        "delivery_verified",
        {"id": delivery.id, "verified": result.verified, "confidence": result.confidence, "building_id": delivery.building_id},
    )

    # Đính kèm ảnh annotated dạng base64 vào detail để UI hiển thị ngay
    detail_with_img = dict(result.detail)
    try:
        detail_with_img["annotated_image_b64"] = image_to_base64(annotated_bytes)
    except Exception:
        pass

    return VerifyResponse(delivery=delivery, detection=detail_with_img)


@router.get("/{delivery_id}/annotated-snapshot", response_class=Response)
async def get_annotated_snapshot(delivery_id: int, db: AsyncSession = Depends(get_db)):
    """Trả về ảnh xác thực đã vẽ bounding box (JPEG)."""
    delivery = await _get_or_404(delivery_id, db)
    if not delivery.camera_snapshot_url:
        raise HTTPException(status_code=404, detail="Chưa có ảnh xác thực")

    path = delivery.camera_snapshot_url.lstrip("/")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File ảnh không tìm thấy")

    with open(path, "rb") as f:
        data = f.read()

    if delivery.ai_detection_detail:
        try:
            detail = json.loads(delivery.ai_detection_detail)
            data = draw_detections(data, detail)
        except Exception:
            pass

    return Response(content=data, media_type="image/jpeg")


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

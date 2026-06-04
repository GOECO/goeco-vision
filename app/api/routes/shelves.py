import secrets
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.shelf import SmartShelf, ShelfSlot, ShelfEvent, SlotStatus, AlertLevel
from app.schemas.shelf import (
    ShelfCreate,
    ShelfResponse,
    ShelfSummary,
    SlotResponse,
    OccupySlotRequest,
    ReleaseSlotRequest,
    PickupRequest,
    ShelfEventResponse,
)

from app.api.routes.ws import manager as ws_manager

router = APIRouter(prefix="/shelves", tags=["smart-shelf"])


async def _get_shelf_or_404(shelf_id: int, db: AsyncSession) -> SmartShelf:
    result = await db.execute(
        select(SmartShelf)
        .where(SmartShelf.id == shelf_id)
        .options(selectinload(SmartShelf.slots), selectinload(SmartShelf.events))
    )
    shelf = result.scalar_one_or_none()
    if not shelf:
        raise HTTPException(status_code=404, detail="Shelf not found")
    return shelf


async def _get_slot_or_404(shelf: SmartShelf, slot_number: int) -> ShelfSlot:
    slot = next((s for s in shelf.slots if s.slot_number == slot_number), None)
    if not slot:
        raise HTTPException(status_code=404, detail=f"Slot {slot_number} not found")
    return slot


def _log_shelf_event(
    db: AsyncSession,
    shelf_id: int,
    slot_number: int,
    event_type: str,
    actor_id: str = None,
    actor_role: str = None,
    delivery_id: int = None,
    notes: str = None,
) -> ShelfEvent:
    event = ShelfEvent(
        shelf_id=shelf_id,
        slot_number=slot_number,
        event_type=event_type,
        actor_id=actor_id,
        actor_role=actor_role,
        delivery_id=delivery_id,
        notes=notes,
        occurred_at=datetime.utcnow(),
    )
    db.add(event)
    return event


@router.post("/", response_model=ShelfResponse, status_code=201)
async def create_shelf(payload: ShelfCreate, db: AsyncSession = Depends(get_db)):
    """Tạo kệ thông minh mới và khởi tạo tất cả các slot."""
    shelf = SmartShelf(
        building_id=payload.building_id,
        floor=payload.floor,
        name=payload.name,
        location_note=payload.location_note,
        total_slots=payload.total_slots,
        created_at=datetime.utcnow(),
    )
    db.add(shelf)
    await db.flush()

    for i in range(1, payload.total_slots + 1):
        slot = ShelfSlot(shelf_id=shelf.id, slot_number=i, status=SlotStatus.EMPTY)
        db.add(slot)

    await db.commit()
    result = await db.execute(
        select(SmartShelf).where(SmartShelf.id == shelf.id)
        .options(selectinload(SmartShelf.slots), selectinload(SmartShelf.events))
    )
    return result.scalar_one()


@router.get("/", response_model=List[ShelfSummary])
async def list_shelves(building_id: str = None, db: AsyncSession = Depends(get_db)):
    query = select(SmartShelf).options(selectinload(SmartShelf.slots))
    if building_id:
        query = query.where(SmartShelf.building_id == building_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/alerts", response_model=List[ShelfSummary])
async def get_shelf_alerts(db: AsyncSession = Depends(get_db)):
    """Trả về danh sách kệ đang ở mức WARNING (>=80%) hoặc FULL (100%)."""
    result = await db.execute(
        select(SmartShelf).options(selectinload(SmartShelf.slots))
    )
    shelves = result.scalars().all()

    def _alert_level(shelf: SmartShelf) -> AlertLevel:
        occupied = sum(1 for s in shelf.slots if s.status == SlotStatus.OCCUPIED)
        ratio = occupied / shelf.total_slots if shelf.total_slots else 0
        if ratio >= 1.0:
            return AlertLevel.FULL
        if ratio >= 0.8:
            return AlertLevel.WARNING
        return AlertLevel.OK

    return [s for s in shelves if _alert_level(s) != AlertLevel.OK]


@router.get("/{shelf_id}", response_model=ShelfResponse)
async def get_shelf(shelf_id: int, db: AsyncSession = Depends(get_db)):
    return await _get_shelf_or_404(shelf_id, db)


@router.get("/{shelf_id}/slots", response_model=List[SlotResponse])
async def get_slots(shelf_id: int, db: AsyncSession = Depends(get_db)):
    shelf = await _get_shelf_or_404(shelf_id, db)
    return shelf.slots


@router.post("/{shelf_id}/slots/{slot_number}/occupy", response_model=SlotResponse)
async def occupy_slot(
    shelf_id: int,
    slot_number: int,
    payload: OccupySlotRequest,
    db: AsyncSession = Depends(get_db),
):
    """Shipper đặt kiện hàng vào slot — sinh access token cho cư dân."""
    shelf = await _get_shelf_or_404(shelf_id, db)
    slot = await _get_slot_or_404(shelf, slot_number)

    if slot.status != SlotStatus.EMPTY:
        raise HTTPException(
            status_code=409,
            detail=f"Slot {slot_number} đang ở trạng thái '{slot.status.value}', không thể đặt hàng vào."
        )

    # Sinh mã PIN 6 chữ số cho cư dân
    pin = str(secrets.randbelow(900000) + 100000)
    slot.status = SlotStatus.OCCUPIED
    slot.current_delivery_id = payload.delivery_id
    slot.access_token = pin
    slot.occupied_since = datetime.utcnow()
    slot.notes = payload.notes

    _log_shelf_event(
        db, shelf_id, slot_number, "item_in",
        actor_id=payload.actor_id, actor_role="shipper",
        delivery_id=payload.delivery_id,
        notes=f"Mã lấy hàng: {pin}",
    )

    # Cập nhật trạng thái đơn → arrived và thông báo cư dân
    if payload.delivery_id:
        from app.models.delivery import Delivery, DeliveryStatus
        from app.models.user import User
        from app.api.routes.notifications import push_notification

        d_res = await db.execute(select(Delivery).where(Delivery.id == payload.delivery_id))
        delivery = d_res.scalar_one_or_none()
        if delivery:
            delivery.status = DeliveryStatus.ARRIVED
            delivery.updated_at = datetime.utcnow()

            u_res = await db.execute(select(User).where(User.username == delivery.recipient_id))
            resident = u_res.scalar_one_or_none()
            if resident:
                await push_notification(
                    db, user_id=resident.id,
                    title=f"📦 Đơn {delivery.tracking_code} đã đến kệ",
                    body=f"Kệ {shelf.name} · Slot {slot_number}\nMã lấy hàng: {pin}\nVui lòng xuống nhận trong 24 giờ.",
                    notif_type="delivery_arrived",
                    delivery_id=delivery.id,
                )

    occupied_count = sum(1 for s in shelf.slots if s.status == SlotStatus.OCCUPIED or s.id == slot.id)
    ratio = occupied_count / shelf.total_slots if shelf.total_slots else 0
    if ratio >= 1.0:
        _log_shelf_event(db, shelf_id, slot_number, "alert_full",
                         notes=f"Kệ đầy: {occupied_count}/{shelf.total_slots} slot")
    elif ratio >= 0.8:
        _log_shelf_event(db, shelf_id, slot_number, "alert_warning",
                         notes=f"Kệ gần đầy: {occupied_count}/{shelf.total_slots} slot")

    await db.commit()
    result = await db.execute(select(ShelfSlot).where(ShelfSlot.id == slot.id))
    updated_slot = result.scalar_one()
    await ws_manager.broadcast("shelf_occupied", {"shelf_id": shelf_id, "slot": slot_number, "building_id": shelf.building_id, "delivery_id": payload.delivery_id})
    return updated_slot


@router.post("/{shelf_id}/slots/{slot_number}/release", response_model=SlotResponse)
async def release_slot(
    shelf_id: int,
    slot_number: int,
    payload: ReleaseSlotRequest,
    db: AsyncSession = Depends(get_db),
):
    """Cư dân lấy hàng khỏi slot — xác thực bằng access token."""
    shelf = await _get_shelf_or_404(shelf_id, db)
    slot = await _get_slot_or_404(shelf, slot_number)

    if slot.status != SlotStatus.OCCUPIED:
        raise HTTPException(
            status_code=409,
            detail=f"Slot {slot_number} hiện đang trống, không có hàng để lấy."
        )

    if payload.access_token and slot.access_token != payload.access_token:
        raise HTTPException(status_code=403, detail="Access token không đúng.")

    delivery_id = slot.current_delivery_id
    slot.status = SlotStatus.EMPTY
    slot.current_delivery_id = None
    slot.access_token = None
    slot.occupied_since = None
    slot.notes = payload.notes

    _log_shelf_event(
        db, shelf_id, slot_number, "item_out",
        actor_id=payload.actor_id, actor_role="recipient",
        delivery_id=delivery_id,
    )

    await db.commit()
    result = await db.execute(select(ShelfSlot).where(ShelfSlot.id == slot.id))
    updated_slot = result.scalar_one()
    await ws_manager.broadcast("shelf_released", {"shelf_id": shelf_id, "slot": slot_number, "building_id": shelf.building_id})
    return updated_slot


@router.post("/{shelf_id}/slots/{slot_number}/pickup")
async def pickup_slot(
    shelf_id: int,
    slot_number: int,
    payload: PickupRequest,
    db: AsyncSession = Depends(get_db),
):
    """Cư dân lấy hàng — kiểm tra đúng chủ và mã PIN. Cảnh báo nếu lấy nhầm."""
    from app.models.delivery import Delivery, DeliveryStatus
    from app.models.user import User
    from app.api.routes.notifications import push_notification

    shelf = await _get_shelf_or_404(shelf_id, db)
    slot = await _get_slot_or_404(shelf, slot_number)

    if slot.status != SlotStatus.OCCUPIED:
        raise HTTPException(status_code=409, detail="Slot này đang trống, không có hàng để lấy.")

    # Lấy thông tin đơn hàng trong slot
    delivery = None
    if slot.current_delivery_id:
        d_res = await db.execute(select(Delivery).where(Delivery.id == slot.current_delivery_id))
        delivery = d_res.scalar_one_or_none()

    # Kiểm tra đúng chủ hàng
    if delivery and delivery.recipient_id != payload.resident_id:
        _log_shelf_event(
            db, shelf_id, slot_number, "wrong_pickup",
            actor_id=payload.resident_id, actor_role="resident",
            delivery_id=slot.current_delivery_id,
            notes=f"⚠️ {payload.resident_id} cố lấy hàng của {delivery.recipient_id}",
        )

        # Cảnh báo tất cả manager/admin
        q = select(User).where(
            User.building_id == shelf.building_id,
            User.role.in_(["manager", "admin"]),
            User.is_active == True,  # noqa: E712
        )
        managers = (await db.execute(q)).scalars().all()
        alert_title = f"🚨 LẤY NHẦM HÀNG — {shelf.name} Slot {slot_number}"
        alert_body = (
            f"Cư dân '{payload.resident_id}' cố lấy đơn {delivery.tracking_code} "
            f"(của '{delivery.recipient_id}').\n"
            f"Kệ: {shelf.name} · Slot: {slot_number} · Tòa: {shelf.building_id}"
        )
        for mgr in managers:
            await push_notification(
                db, user_id=mgr.id,
                title=alert_title, body=alert_body,
                notif_type="wrong_pickup", delivery_id=delivery.id,
            )

        await ws_manager.broadcast("wrong_pickup", {
            "shelf_id": shelf_id, "slot": slot_number,
            "resident": payload.resident_id,
            "owner": delivery.recipient_id,
            "tracking_code": delivery.tracking_code,
            "building_id": shelf.building_id,
        })
        await db.commit()

        raise HTTPException(
            status_code=403,
            detail={
                "type": "wrong_pickup",
                "message": f"⚠️ Đây KHÔNG phải hàng của bạn! Đơn này thuộc về '{delivery.recipient_id}'.",
                "tracking_code": delivery.tracking_code,
                "owner": delivery.recipient_id,
                "alert_sent": True,
            },
        )

    # Kiểm tra mã PIN
    if slot.access_token != payload.pickup_pin:
        raise HTTPException(status_code=403, detail="Mã lấy hàng không đúng. Vui lòng kiểm tra lại.")

    # Thành công — giải phóng slot và cập nhật đơn
    delivery_id = slot.current_delivery_id
    slot.status = SlotStatus.EMPTY
    slot.current_delivery_id = None
    slot.access_token = None
    slot.occupied_since = None
    slot.notes = None

    if delivery:
        delivery.status = DeliveryStatus.COLLECTED
        delivery.updated_at = datetime.utcnow()

    _log_shelf_event(
        db, shelf_id, slot_number, "item_out",
        actor_id=payload.resident_id, actor_role="resident",
        delivery_id=delivery_id,
        notes="✅ Lấy hàng thành công",
    )

    await db.commit()
    await ws_manager.broadcast("shelf_released", {
        "shelf_id": shelf_id, "slot": slot_number,
        "building_id": shelf.building_id, "delivery_id": delivery_id,
    })

    return {
        "success": True,
        "message": f"✅ Lấy hàng thành công! Đơn {delivery.tracking_code if delivery else delivery_id}.",
        "delivery_id": delivery_id,
        "tracking_code": delivery.tracking_code if delivery else None,
    }


@router.get("/{shelf_id}/events", response_model=List[ShelfEventResponse])
async def get_shelf_events(
    shelf_id: int,
    slot_number: int = None,
    db: AsyncSession = Depends(get_db),
):
    """Lịch sử toàn bộ sự kiện trên kệ (lọc theo slot nếu cần)."""
    await _get_shelf_or_404(shelf_id, db)
    query = (
        select(ShelfEvent)
        .where(ShelfEvent.shelf_id == shelf_id)
        .order_by(ShelfEvent.occurred_at.desc())
    )
    if slot_number is not None:
        query = query.where(ShelfEvent.slot_number == slot_number)
    result = await db.execute(query)
    return result.scalars().all()

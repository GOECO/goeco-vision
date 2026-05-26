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

    token = secrets.token_urlsafe(16)
    slot.status = SlotStatus.OCCUPIED
    slot.current_delivery_id = payload.delivery_id
    slot.access_token = token
    slot.occupied_since = datetime.utcnow()
    slot.notes = payload.notes

    _log_shelf_event(
        db, shelf_id, slot_number, "item_in",
        actor_id=payload.actor_id, actor_role="shipper",
        delivery_id=payload.delivery_id,
        notes=f"Access token: {token}",
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

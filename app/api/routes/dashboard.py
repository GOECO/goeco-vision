from datetime import datetime
from typing import Any

import pathlib

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.delivery import Delivery, DeliveryEvent, DeliveryStatus
from app.models.shelf import SmartShelf, ShelfSlot, ShelfEvent, SlotStatus

from jinja2 import Environment, FileSystemLoader

# Jinja2 3.1.5+ bug: async env dùng dict làm cache key → unhashable.
# Fix: khởi tạo Environment với enable_async=False.
_TEMPLATES_DIR = pathlib.Path(__file__).parent.parent.parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
    enable_async=False,
    cache_size=0,  # Jinja2 3.1.5+ bug: dict cache key → unhashable; disable cache
)
templates = Jinja2Templates(env=_jinja_env)
router = APIRouter(tags=["dashboard"])


async def _get_delivery_stats(db: AsyncSession) -> dict:
    result = await db.execute(select(Delivery.status, func.count()).group_by(Delivery.status))
    rows = result.all()
    counts = {r[0]: r[1] for r in rows}
    total = sum(counts.values())
    return {
        "total": total,
        "pending": counts.get(DeliveryStatus.PENDING, 0),
        "in_transit": counts.get(DeliveryStatus.IN_TRANSIT, 0),
        "arrived": counts.get(DeliveryStatus.ARRIVED, 0),
        "verified": counts.get(DeliveryStatus.VERIFIED, 0),
        "collected": counts.get(DeliveryStatus.COLLECTED, 0),
        "disputed": counts.get(DeliveryStatus.DISPUTED, 0),
    }


async def _get_shelves_summary(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(SmartShelf).options(selectinload(SmartShelf.slots))
    )
    shelves = result.scalars().all()
    out = []
    for s in shelves:
        occupied = sum(1 for slot in s.slots if slot.status == SlotStatus.OCCUPIED)
        ratio = occupied / s.total_slots if s.total_slots else 0
        alert = "full" if ratio >= 1.0 else ("warning" if ratio >= 0.8 else "ok")
        out.append({
            "id": s.id,
            "name": s.name,
            "building_id": s.building_id,
            "floor": s.floor,
            "total_slots": s.total_slots,
            "occupied_slots": occupied,
            "alert_level": alert,
        })
    return out


async def _get_recent_events(db: AsyncSession, limit: int = 10) -> list[dict]:
    result = await db.execute(
        select(DeliveryEvent).order_by(DeliveryEvent.occurred_at.desc()).limit(limit)
    )
    events = result.scalars().all()
    out = []
    for e in events:
        out.append({
            "delivery_id": e.delivery_id,
            "shelf_id": None,
            "event_type": e.event_type,
            "description": e.description,
            "actor_role": e.actor_role,
            "occurred_at": e.occurred_at,
        })

    result2 = await db.execute(
        select(ShelfEvent).order_by(ShelfEvent.occurred_at.desc()).limit(limit)
    )
    for e in result2.scalars().all():
        out.append({
            "delivery_id": e.delivery_id,
            "shelf_id": e.shelf_id,
            "event_type": e.event_type,
            "description": e.notes,
            "actor_role": e.actor_role,
            "occurred_at": e.occurred_at,
        })

    out.sort(key=lambda x: x["occurred_at"], reverse=True)
    return out[:limit]


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    stats = await _get_delivery_stats(db)
    shelves = await _get_shelves_summary(db)
    recent_events = await _get_recent_events(db)
    alerts = [s for s in shelves if s["alert_level"] != "ok"]

    # Starlette 1.0+ API: TemplateResponse(request, name, context)
    return templates.TemplateResponse(request, "dashboard.html", {
        "stats": stats,
        "shelves": shelves,
        "recent_events": recent_events,
        "alerts": alerts,
    })


@router.get("/api/v1/dashboard/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """JSON endpoint cho frontend polling."""
    return {
        "deliveries": await _get_delivery_stats(db),
        "shelves": await _get_shelves_summary(db),
        "generated_at": datetime.utcnow().isoformat(),
    }

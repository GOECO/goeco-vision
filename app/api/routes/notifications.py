from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/", response_model=List[NotificationResponse])
async def get_my_notifications(
    unread_only: bool = False,
    limit: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        query = query.where(Notification.is_read == False)  # noqa: E712
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{notif_id}/read", response_model=NotificationResponse)
async def mark_as_read(
    notif_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notif_id,
            Notification.user_id == current_user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Thông báo không tồn tại.")

    notif.is_read = True
    notif.read_at = datetime.utcnow()
    await db.commit()
    await db.refresh(notif)
    return notif


@router.post("/read-all")
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    now = datetime.utcnow()
    for notif in result.scalars().all():
        notif.is_read = True
        notif.read_at = now
    await db.commit()
    return {"marked_read": True}


async def push_notification(
    db: AsyncSession,
    user_id: int,
    title: str,
    body: str,
    notif_type: str,
    delivery_id: int | None = None,
    shelf_id: int | None = None,
) -> Notification:
    notif = Notification(
        user_id=user_id,
        title=title,
        body=body,
        notif_type=notif_type,
        delivery_id=delivery_id,
        shelf_id=shelf_id,
    )
    db.add(notif)
    await db.flush()
    return notif

from sqlalchemy import String, DateTime, Boolean, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.models.base import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text)
    notif_type: Mapped[str] = mapped_column(String(32))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    delivery_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shelf_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

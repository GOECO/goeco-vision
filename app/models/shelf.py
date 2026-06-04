from sqlalchemy import String, DateTime, Enum, Text, Integer, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum

from app.models.base import Base


class SlotStatus(str, enum.Enum):
    EMPTY = "empty"
    OCCUPIED = "occupied"
    RESERVED = "reserved"
    MAINTENANCE = "maintenance"


class AlertLevel(str, enum.Enum):
    OK = "ok"
    WARNING = "warning"   # >= 80% đầy
    FULL = "full"         # 100% đầy


class SmartShelf(Base):
    __tablename__ = "smart_shelves"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    building_id: Mapped[str] = mapped_column(String(32), index=True)
    floor: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(64))
    location_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_slots: Mapped[int] = mapped_column(Integer, default=10)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    slots: Mapped[list["ShelfSlot"]] = relationship(
        back_populates="shelf", cascade="all, delete-orphan", order_by="ShelfSlot.slot_number"
    )
    events: Mapped[list["ShelfEvent"]] = relationship(
        back_populates="shelf", cascade="all, delete-orphan"
    )



class ShelfSlot(Base):
    __tablename__ = "shelf_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    shelf_id: Mapped[int] = mapped_column(Integer, ForeignKey("smart_shelves.id"), index=True)
    slot_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[SlotStatus] = mapped_column(Enum(SlotStatus, values_callable=lambda x: [e.value for e in x]), default=SlotStatus.EMPTY)
    current_delivery_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    access_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occupied_since: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    shelf: Mapped["SmartShelf"] = relationship(back_populates="slots")


class ShelfEvent(Base):
    __tablename__ = "shelf_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    shelf_id: Mapped[int] = mapped_column(Integer, ForeignKey("smart_shelves.id"), index=True)
    slot_number: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(64))
    delivery_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    shelf: Mapped["SmartShelf"] = relationship(back_populates="events")

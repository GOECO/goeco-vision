from sqlalchemy import String, DateTime, Enum, Text, Float, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum

from app.models.base import Base


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    IN_TRANSIT = "in_transit"
    ARRIVED = "arrived"
    VERIFIED = "verified"
    COLLECTED = "collected"
    DISPUTED = "disputed"


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tracking_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    shipper_id: Mapped[str] = mapped_column(String(64))
    recipient_id: Mapped[str] = mapped_column(String(64))
    building_id: Mapped[str] = mapped_column(String(32))
    unit_number: Mapped[str] = mapped_column(String(16))
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, values_callable=lambda x: [e.value for e in x]), default=DeliveryStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    camera_snapshot_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ai_confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_detection_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    events: Mapped[list["DeliveryEvent"]] = relationship(
        back_populates="delivery", cascade="all, delete-orphan"
    )


class DeliveryEvent(Base):
    __tablename__ = "delivery_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    delivery_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("deliveries.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    snapshot_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    delivery: Mapped["Delivery"] = relationship(back_populates="events")

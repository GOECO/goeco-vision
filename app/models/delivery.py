from sqlalchemy import Column, Integer, String, DateTime, Enum, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum

Base = declarative_base()


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    IN_TRANSIT = "in_transit"
    ARRIVED = "arrived"
    VERIFIED = "verified"
    COLLECTED = "collected"
    DISPUTED = "disputed"


class Delivery(Base):
    __tablename__ = "deliveries"

    id = Column(Integer, primary_key=True, index=True)
    tracking_code = Column(String(64), unique=True, index=True, nullable=False)
    shipper_id = Column(String(64), nullable=False)
    recipient_id = Column(String(64), nullable=False)
    building_id = Column(String(32), nullable=False)
    unit_number = Column(String(16), nullable=False)
    status = Column(Enum(DeliveryStatus), default=DeliveryStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Camera verification fields
    camera_snapshot_url = Column(String(512), nullable=True)
    ai_confidence_score = Column(Float, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    verification_note = Column(Text, nullable=True)


class DeliveryEvent(Base):
    __tablename__ = "delivery_events"

    id = Column(Integer, primary_key=True, index=True)
    delivery_id = Column(Integer, nullable=False, index=True)
    event_type = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    actor_id = Column(String(64), nullable=True)
    actor_role = Column(String(32), nullable=True)
    snapshot_url = Column(String(512), nullable=True)
    occurred_at = Column(DateTime, default=datetime.utcnow)

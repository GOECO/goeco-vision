from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.delivery import DeliveryStatus


class DeliveryCreate(BaseModel):
    tracking_code: str
    shipper_id: str
    recipient_id: str
    building_id: str
    unit_number: str


class DeliveryUpdate(BaseModel):
    status: Optional[DeliveryStatus] = None
    camera_snapshot_url: Optional[str] = None
    ai_confidence_score: Optional[float] = None
    verification_note: Optional[str] = None


class DeliveryResponse(BaseModel):
    id: int
    tracking_code: str
    shipper_id: str
    recipient_id: str
    building_id: str
    unit_number: str
    status: DeliveryStatus
    camera_snapshot_url: Optional[str]
    ai_confidence_score: Optional[float]
    verified_at: Optional[datetime]
    verification_note: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DeliveryEventCreate(BaseModel):
    event_type: str
    description: Optional[str] = None
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None
    snapshot_url: Optional[str] = None


class DeliveryEventResponse(BaseModel):
    id: int
    delivery_id: int
    event_type: str
    description: Optional[str]
    actor_id: Optional[str]
    actor_role: Optional[str]
    snapshot_url: Optional[str]
    occurred_at: datetime

    class Config:
        from_attributes = True

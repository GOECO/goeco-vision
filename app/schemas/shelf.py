from pydantic import BaseModel, ConfigDict, Field, computed_field
from datetime import datetime
from typing import Optional
from app.models.shelf import SlotStatus, AlertLevel


class ShelfCreate(BaseModel):
    building_id: str
    floor: str
    name: str
    total_slots: int = 10
    location_note: Optional[str] = None


class SlotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slot_number: int
    status: SlotStatus
    current_delivery_id: Optional[int]
    access_token: Optional[str]
    occupied_since: Optional[datetime]
    notes: Optional[str]


def _compute_occupied(slots: list[SlotResponse]) -> int:
    return sum(1 for s in slots if s.status == SlotStatus.OCCUPIED)


def _compute_alert(occupied: int, total: int) -> AlertLevel:
    if total == 0:
        return AlertLevel.OK
    ratio = occupied / total
    if ratio >= 1.0:
        return AlertLevel.FULL
    if ratio >= 0.8:
        return AlertLevel.WARNING
    return AlertLevel.OK


class ShelfResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    building_id: str
    floor: str
    name: str
    location_note: Optional[str]
    total_slots: int
    created_at: datetime
    slots: list[SlotResponse] = []

    @computed_field
    @property
    def occupied_slots(self) -> int:
        return _compute_occupied(self.slots)

    @computed_field
    @property
    def alert_level(self) -> AlertLevel:
        return _compute_alert(self.occupied_slots, self.total_slots)


class ShelfSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    building_id: str
    floor: str
    name: str
    total_slots: int
    # slots chỉ dùng để tính toán, không trả về trong response
    slots: list[SlotResponse] = Field(default=[], exclude=True)

    @computed_field
    @property
    def occupied_slots(self) -> int:
        return _compute_occupied(self.slots)

    @computed_field
    @property
    def alert_level(self) -> AlertLevel:
        return _compute_alert(self.occupied_slots, self.total_slots)


class OccupySlotRequest(BaseModel):
    delivery_id: Optional[int] = None
    actor_id: str
    notes: Optional[str] = None


class ReleaseSlotRequest(BaseModel):
    actor_id: str
    access_token: Optional[str] = None
    notes: Optional[str] = None


class PickupRequest(BaseModel):
    resident_id: str
    pickup_pin: str


class ShelfEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shelf_id: int
    slot_number: int
    event_type: str
    delivery_id: Optional[int]
    actor_id: Optional[str]
    actor_role: Optional[str]
    notes: Optional[str]
    occurred_at: datetime

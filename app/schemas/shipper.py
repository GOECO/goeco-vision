from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


class ShipperCreate(BaseModel):
    shipper_id: str
    name: str
    phone: Optional[str] = None
    company: Optional[str] = None


class ShipperResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shipper_id: str
    name: str
    phone: Optional[str]
    company: Optional[str]
    photo_path: Optional[str]
    has_face_id: bool = False
    is_active: bool
    registered_at: datetime
    last_seen_at: Optional[datetime]

    @classmethod
    def from_orm_with_flags(cls, obj):
        data = cls.model_validate(obj)
        data.has_face_id = obj.face_embedding is not None
        return data


class FaceVerifyResponse(BaseModel):
    shipper_id: str
    matched: bool
    confidence: float
    note: str
    detection_detail: Optional[dict] = None

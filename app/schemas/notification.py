from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    notif_type: str
    is_read: bool
    delivery_id: Optional[int]
    shelf_id: Optional[int]
    created_at: datetime
    read_at: Optional[datetime]

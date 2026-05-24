from sqlalchemy import String, DateTime, Text, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.models.base import Base


class ShipperProfile(Base):
    __tablename__ = "shipper_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    shipper_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    company: Mapped[str | None] = mapped_column(String(128), nullable=True)
    photo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    face_embedding: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON float array
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

from sqlalchemy import String, DateTime, Enum, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
import enum

from app.models.base import Base


class UserRole(str, enum.Enum):
    RESIDENT = "resident"
    SHIPPER = "shipper"
    MANAGER = "manager"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128))
    hashed_password: Mapped[str] = mapped_column(String(256))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.RESIDENT)
    building_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    unit_number: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

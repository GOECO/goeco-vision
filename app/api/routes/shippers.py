import os
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.shipper import ShipperProfile
from app.schemas.shipper import ShipperCreate, ShipperResponse, FaceVerifyResponse
from app.services import face_service

UPLOAD_DIR = "uploads/shippers"
os.makedirs(UPLOAD_DIR, exist_ok=True)

router = APIRouter(prefix="/shippers", tags=["shippers"])


async def _get_shipper_or_404(shipper_id: str, db: AsyncSession) -> ShipperProfile:
    result = await db.execute(
        select(ShipperProfile).where(ShipperProfile.shipper_id == shipper_id)
    )
    shipper = result.scalar_one_or_none()
    if not shipper:
        raise HTTPException(status_code=404, detail=f"Shipper '{shipper_id}' chưa đăng ký.")
    return shipper


@router.post("/", response_model=ShipperResponse, status_code=201)
async def register_shipper(payload: ShipperCreate, db: AsyncSession = Depends(get_db)):
    """Đăng ký shipper mới (chưa có Face ID — upload ảnh qua /shippers/{id}/face)."""
    existing = await db.execute(
        select(ShipperProfile).where(ShipperProfile.shipper_id == payload.shipper_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Shipper ID đã tồn tại.")

    shipper = ShipperProfile(
        shipper_id=payload.shipper_id,
        name=payload.name,
        phone=payload.phone,
        company=payload.company,
        registered_at=datetime.utcnow(),
    )
    db.add(shipper)
    await db.commit()
    await db.refresh(shipper)
    return shipper


@router.get("/", response_model=List[ShipperResponse])
async def list_shippers(active_only: bool = True, db: AsyncSession = Depends(get_db)):
    query = select(ShipperProfile)
    if active_only:
        query = query.where(ShipperProfile.is_active == True)  # noqa: E712
    result = await db.execute(query.order_by(ShipperProfile.registered_at.desc()))
    return result.scalars().all()


@router.get("/{shipper_id}", response_model=ShipperResponse)
async def get_shipper(shipper_id: str, db: AsyncSession = Depends(get_db)):
    return await _get_shipper_or_404(shipper_id, db)


@router.post("/{shipper_id}/face", response_model=ShipperResponse)
async def register_face(
    shipper_id: str,
    photo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload ảnh khuôn mặt shipper để đăng ký Face ID.
    Ảnh phải rõ mặt, đủ sáng, nhìn thẳng vào camera.
    """
    shipper = await _get_shipper_or_404(shipper_id, db)
    image_bytes = await photo.read()

    embedding = face_service.extract_embedding(image_bytes)
    if embedding is None:
        raise HTTPException(
            status_code=422,
            detail="Không phát hiện khuôn mặt trong ảnh. Vui lòng chụp lại rõ mặt hơn.",
        )

    photo_path = os.path.join(UPLOAD_DIR, f"{shipper_id}.jpg")
    with open(photo_path, "wb") as f:
        f.write(image_bytes)

    shipper.face_embedding = face_service.embedding_to_json(embedding)
    shipper.photo_path = photo_path
    await db.commit()
    await db.refresh(shipper)
    return shipper


@router.post("/{shipper_id}/verify-face", response_model=FaceVerifyResponse)
async def verify_shipper_face(
    shipper_id: str,
    photo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Xác thực khuôn mặt shipper qua ảnh camera — dùng để kiểm tra độc lập."""
    shipper = await _get_shipper_or_404(shipper_id, db)

    if not shipper.face_embedding:
        raise HTTPException(
            status_code=400,
            detail="Shipper chưa đăng ký Face ID. Gọi POST /shippers/{id}/face trước.",
        )

    image_bytes = await photo.read()
    matched, confidence, note = face_service.verify_face_against_reference(
        image_bytes, shipper.face_embedding
    )

    if matched:
        shipper.last_seen_at = datetime.utcnow()
        await db.commit()

    return FaceVerifyResponse(
        shipper_id=shipper_id,
        matched=matched,
        confidence=confidence,
        note=note,
    )

"""
Delivery verification service — kết hợp YOLO object detection + Face ID.
"""
from app.services.yolo_service import detect_objects
from app.services import face_service
from app.core.config import settings


class VerificationResult:
    def __init__(self, verified: bool, confidence: float, note: str = "", detail: dict | None = None):
        self.verified = verified
        self.confidence = confidence
        self.note = note
        self.detail = detail or {}


async def verify_delivery_image(
    image_bytes: bytes,
    shipper_id: str,
    face_reference_json: str | None = None,
) -> VerificationResult:
    """
    Phân tích ảnh camera giao nhận:
      1. YOLO detect người + kiện hàng
      2. Nếu shipper có Face ID: so sánh khuôn mặt (InsightFace)
      3. Trả về kết quả xác thực tổng hợp
    """
    detection = await detect_objects(image_bytes)
    detail = detection.to_dict()

    person_conf = detection.max_person_confidence
    package_conf = detection.max_package_confidence
    threshold = settings.yolo_confidence_threshold

    # Bước 1: kiểm tra có người và hàng trong khung hình
    if person_conf < threshold:
        return VerificationResult(
            verified=False, confidence=0.0,
            note="Không phát hiện người trong khung hình — cần kiểm tra thủ công.",
            detail=detail,
        )

    if package_conf < threshold:
        return VerificationResult(
            verified=False, confidence=person_conf,
            note="Phát hiện người nhưng không thấy kiện hàng — nghi ngờ bất thường.",
            detail=detail,
        )

    # Bước 2: Face ID nếu shipper đã đăng ký
    if face_reference_json:
        matched, face_conf, face_note = face_service.verify_face_against_reference(
            image_bytes, face_reference_json
        )
        detail["face_verification"] = {"matched": matched, "confidence": face_conf, "note": face_note}

        if not matched:
            return VerificationResult(
                verified=False, confidence=face_conf,
                note=f"YOLO OK nhưng Face ID không khớp — {face_note}",
                detail=detail,
            )

        combined = round((person_conf + package_conf + face_conf) / 3, 3)
        return VerificationResult(
            verified=True, confidence=combined,
            note=f"✅ YOLO + Face ID xác thực — confidence {combined:.0%}",
            detail=detail,
        )

    # Bước 3: không có Face ID — chỉ dùng YOLO
    combined = round((person_conf + package_conf) / 2, 3)
    return VerificationResult(
        verified=True, confidence=combined,
        note=f"YOLO xác thực (chưa có Face ID) — confidence {combined:.0%}",
        detail=detail,
    )


async def check_locker_tamper(camera_id: str, image_bytes: bytes) -> bool:
    """
    TODO: implement frame-differencing hoặc anomaly detection.
    """
    return False

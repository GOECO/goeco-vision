"""
Delivery verification service — dùng YOLO để phân tích ảnh camera giao nhận.
"""
from app.services.yolo_service import detect_objects
from app.core.config import settings


class VerificationResult:
    def __init__(self, verified: bool, confidence: float, note: str = "", detail: dict | None = None):
        self.verified = verified
        self.confidence = confidence
        self.note = note
        self.detail = detail or {}


async def verify_delivery_image(image_bytes: bytes, shipper_id: str) -> VerificationResult:
    """
    Phân tích ảnh camera:
      - Phát hiện có người (shipper) trong khung hình không
      - Phát hiện có kiện hàng không
      - Trả về confidence score tổng hợp

    TODO: thêm face matching — so sánh khuôn mặt trong ảnh với ảnh đại diện
          shipper lưu trong DB (dùng deepface hoặc InsightFace).
    """
    detection = await detect_objects(image_bytes)
    detail = detection.to_dict()

    person_conf = detection.max_person_confidence
    package_conf = detection.max_package_confidence
    threshold = settings.yolo_confidence_threshold

    if person_conf >= threshold and package_conf >= threshold:
        combined = round((person_conf + package_conf) / 2, 3)
        return VerificationResult(
            verified=True,
            confidence=combined,
            note=(
                f"YOLO xác thực: {detection.persons_count} người, "
                f"{detection.packages_count} kiện hàng — confidence {combined:.0%}"
            ),
            detail=detail,
        )

    if person_conf >= threshold and package_conf < threshold:
        return VerificationResult(
            verified=False,
            confidence=person_conf,
            note="Phát hiện người nhưng không thấy kiện hàng — cần kiểm tra thủ công.",
            detail=detail,
        )

    if person_conf < threshold and package_conf >= threshold:
        return VerificationResult(
            verified=False,
            confidence=package_conf,
            note="Phát hiện kiện hàng nhưng không thấy shipper — nghi ngờ giao nhận bất thường.",
            detail=detail,
        )

    return VerificationResult(
        verified=False,
        confidence=0.0,
        note="Không phát hiện người hoặc kiện hàng — cần xem xét thủ công.",
        detail=detail,
    )


async def check_locker_tamper(camera_id: str, image_bytes: bytes) -> bool:
    """
    Phát hiện can thiệp bất thường tại khu vực kệ/tủ.

    TODO: implement frame-differencing hoặc anomaly detection — hiện tại
          trả về False (không phát hiện) để tránh false positive.
    """
    return False

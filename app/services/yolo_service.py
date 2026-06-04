"""
YOLO local inference service.

Dùng YOLOv8n (nano, ~6MB) để detect người và kiện hàng trong ảnh camera.
Model tự download lần đầu chạy từ ultralytics CDN.
"""
import asyncio
import io
import logging
from typing import Optional

from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)

_model = None

# COCO class IDs liên quan đến giao nhận
PERSON_CLASS = 0
PACKAGE_CLASSES = {
    24: "backpack",
    26: "handbag",
    28: "suitcase",
}

_MAX_INFERENCE_DIM = 640


def _get_model():
    global _model
    if _model is None:
        try:
            import torch

            # PyTorch 2.6 changed weights_only default to True, which blocks ultralytics globals.
            # Temporarily allow weights_only=False for the trusted ultralytics checkpoint.
            _orig_load = torch.load
            def _patched_load(*args, **kwargs):
                kwargs.setdefault("weights_only", False)
                return _orig_load(*args, **kwargs)
            torch.load = _patched_load
            try:
                from ultralytics import YOLO
                _model = YOLO(settings.yolo_model)
            finally:
                torch.load = _orig_load

            logger.info("YOLO model loaded: %s", settings.yolo_model)
        except Exception as e:
            logger.error("Failed to load YOLO model: %s", e)
            raise
    return _model


class DetectionResult:
    def __init__(self, persons: list, packages: list):
        self.persons = persons
        self.packages = packages
        self.persons_count = len(persons)
        self.packages_count = len(packages)
        self.max_person_confidence: float = max(
            (p["confidence"] for p in persons), default=0.0
        )
        self.max_package_confidence: float = max(
            (p["confidence"] for p in packages), default=0.0
        )

    def to_dict(self) -> dict:
        return {
            "persons_detected": self.persons_count,
            "packages_detected": self.packages_count,
            "max_person_confidence": round(self.max_person_confidence, 3),
            "max_package_confidence": round(self.max_package_confidence, 3),
            "persons": self.persons,
            "packages": self.packages,
        }

    @classmethod
    def merge(cls, results: list["DetectionResult"]) -> "DetectionResult":
        """Merge nhiều frame: dùng detections của frame tốt nhất, average confidence."""
        if not results:
            return cls(persons=[], packages=[])

        best = max(results, key=lambda r: r.max_person_confidence + r.max_package_confidence)
        merged = cls(persons=best.persons, packages=best.packages)

        # Override với average confidence qua tất cả frames
        merged.max_person_confidence = round(
            sum(r.max_person_confidence for r in results) / len(results), 3
        )
        merged.max_package_confidence = round(
            sum(r.max_package_confidence for r in results) / len(results), 3
        )
        return merged


async def detect_objects(image_bytes: bytes) -> DetectionResult:
    """Chạy YOLO inference trên ảnh bytes, trả về kết quả detect người và kiện hàng."""

    def _run_sync() -> DetectionResult:
        import numpy as np

        model = _get_model()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        w, h = image.size
        if max(w, h) > _MAX_INFERENCE_DIM:
            scale = _MAX_INFERENCE_DIM / max(w, h)
            image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        arr = np.array(image)
        results = model(arr, verbose=False, conf=settings.yolo_confidence_threshold)[0]

        persons = []
        packages = []

        for box in results.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            bbox = {"x1": round(x1), "y1": round(y1), "x2": round(x2), "y2": round(y2)}

            if cls_id == PERSON_CLASS:
                persons.append({"confidence": round(conf, 3), "bbox": bbox})
            elif cls_id in PACKAGE_CLASSES:
                packages.append({
                    "class": PACKAGE_CLASSES[cls_id],
                    "confidence": round(conf, 3),
                    "bbox": bbox,
                })

        return DetectionResult(persons=persons, packages=packages)

    return await asyncio.to_thread(_run_sync)


async def detect_multiframe_from_camera(
    camera_url: str,
    n_frames: int = 3,
    interval_ms: int = 400,
) -> tuple[bytes | None, DetectionResult | None]:
    """
    Chụp n frame từ RTSP/camera URL, chạy YOLO song song, merge kết quả.
    Trả về (best_frame_bytes, merged_result) — best_frame là frame có confidence cao nhất.
    """
    def _capture_frames() -> list[bytes]:
        import cv2
        import time

        cap = cv2.VideoCapture(camera_url)
        frames: list[bytes] = []
        try:
            for i in range(n_frames):
                ret, frame = cap.read()
                if ret:
                    ok, buf = cv2.imencode(".jpg", frame)
                    if ok:
                        frames.append(buf.tobytes())
                if interval_ms > 0 and i < n_frames - 1:
                    time.sleep(interval_ms / 1000.0)
        finally:
            cap.release()
        return frames

    try:
        frame_bytes_list = await asyncio.to_thread(_capture_frames)
    except ImportError:
        logger.warning("opencv-python chưa được cài — không thể đọc RTSP stream.")
        return None, None

    if not frame_bytes_list:
        logger.warning("Không chụp được frame từ camera: %s", camera_url)
        return None, None

    # Chạy YOLO song song trên tất cả frames
    results = await asyncio.gather(*[detect_objects(fb) for fb in frame_bytes_list])
    merged = DetectionResult.merge(list(results))

    # Chọn frame tốt nhất để lưu và vẽ bboxes
    best_idx = max(
        range(len(results)),
        key=lambda i: results[i].max_person_confidence + results[i].max_package_confidence,
    )
    return frame_bytes_list[best_idx], merged


async def detect_objects_from_camera(camera_url: str) -> Optional[DetectionResult]:
    """Single-frame camera capture (backward compat). Dùng detect_multiframe_from_camera cho production."""
    _, result = await detect_multiframe_from_camera(camera_url, n_frames=1, interval_ms=0)
    return result

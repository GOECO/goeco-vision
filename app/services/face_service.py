"""
Face ID Service — trích xuất và so sánh face embedding cho xác thực shipper.

Dùng InsightFace (buffalo_sc model, ~30MB, ONNX, không cần GPU).
Nếu insightface chưa cài, tất cả hàm trả về None/False gracefully.
"""
import io
import json
import logging
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

_face_app = None
SIMILARITY_THRESHOLD = 0.35  # cosine similarity threshold cho ArcFace embeddings


def _get_face_app():
    global _face_app
    if _face_app is None:
        from insightface.app import FaceAnalysis
        _face_app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
        _face_app.prepare(ctx_id=0, det_size=(320, 320))
        logger.info("InsightFace buffalo_sc model loaded.")
    return _face_app


def _image_to_array(image_bytes: bytes) -> np.ndarray:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return np.array(image)


def extract_embedding(image_bytes: bytes) -> Optional[list[float]]:
    """
    Phát hiện khuôn mặt lớn nhất trong ảnh và trả về embedding vector.
    Trả về None nếu không tìm thấy khuôn mặt.
    """
    try:
        app = _get_face_app()
        arr = _image_to_array(image_bytes)
        faces = app.get(arr)
        if not faces:
            return None
        largest = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        return largest.embedding.tolist()
    except ImportError:
        logger.warning("insightface chưa cài — Face ID không khả dụng.")
        return None
    except Exception as e:
        logger.error("Lỗi extract embedding: %s", e)
        return None


def embedding_to_json(embedding: list[float]) -> str:
    return json.dumps(embedding)


def embedding_from_json(json_str: str) -> np.ndarray:
    return np.array(json.loads(json_str), dtype=np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def verify_face_against_reference(
    probe_bytes: bytes,
    reference_json: str,
) -> tuple[bool, float, str]:
    """
    So sánh khuôn mặt trong ảnh với embedding tham chiếu đã lưu.
    Trả về: (matched, confidence, note)
    """
    probe_embedding = extract_embedding(probe_bytes)
    if probe_embedding is None:
        return False, 0.0, "Không phát hiện khuôn mặt trong ảnh camera."

    ref_embedding = embedding_from_json(reference_json)
    sim = cosine_similarity(np.array(probe_embedding, dtype=np.float32), ref_embedding)

    matched = sim >= SIMILARITY_THRESHOLD
    note = (
        f"Face match: {sim:.0%} — {'✅ Xác thực thành công' if matched else '❌ Không khớp'}"
    )
    return matched, round(sim, 4), note

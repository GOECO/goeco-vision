"""
Image annotation utility — vẽ bounding boxes YOLO lên ảnh giao nhận.
"""
import io
import base64
from PIL import Image, ImageDraw, ImageFont


_PERSON_COLOR = (59, 130, 246)    # xanh dương
_PACKAGE_COLOR = (245, 158, 11)   # cam
_LABEL_BG_ALPHA = 180


def draw_detections(image_bytes: bytes, detection_detail: dict) -> bytes:
    """Vẽ bounding boxes từ detection_detail lên ảnh, trả về JPEG bytes."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    except Exception:
        font = ImageFont.load_default()

    for person in detection_detail.get("persons", []):
        _draw_box(draw, person["bbox"], _PERSON_COLOR, f"Person {person['confidence']:.0%}", font)

    for pkg in detection_detail.get("packages", []):
        label = f"{pkg['class']} {pkg['confidence']:.0%}"
        _draw_box(draw, pkg["bbox"], _PACKAGE_COLOR, label, font)

    face = detection_detail.get("face_verification")
    if face:
        matched = face.get("matched", False)
        conf = face.get("confidence", 0)
        color = (34, 197, 94) if matched else (239, 68, 68)
        text = f"Face {'✓' if matched else '✗'} {conf:.0%}"
        draw.text((8, 8), text, fill=(*color, 255), font=font)

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def image_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode()


def _draw_box(draw: ImageDraw.ImageDraw, bbox: dict, color: tuple, label: str, font):
    x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
    draw.rectangle([x1, y1, x2, y2], outline=(*color, 255), width=3)

    tw, th = 0, 0
    try:
        bbox_text = font.getbbox(label)
        tw = bbox_text[2] - bbox_text[0]
        th = bbox_text[3] - bbox_text[1]
    except Exception:
        tw, th = len(label) * 7, 14

    pad = 4
    draw.rectangle(
        [x1, y1 - th - pad * 2, x1 + tw + pad * 2, y1],
        fill=(*color, _LABEL_BG_ALPHA),
    )
    draw.text((x1 + pad, y1 - th - pad), label, fill=(255, 255, 255, 255), font=font)

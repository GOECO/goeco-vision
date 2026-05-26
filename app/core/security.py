"""
JWT HS256 implementation using only Python stdlib (hmac + hashlib).
Avoids dependency on cryptography/python-jose which have Rust/cffi issues
in certain environments.
"""
import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}${digest}"


def verify_password(plain: str, hashed: str) -> bool:
    try:
        salt, digest = hashed.split("$", 1)
        expected = hashlib.sha256(f"{salt}{plain}".encode()).hexdigest()
        return hmac.compare_digest(expected, digest)
    except Exception:
        return False


def _b64enc(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64dec(data: str) -> bytes:
    pad = 4 - len(data) % 4
    return base64.urlsafe_b64decode(data + "=" * pad)


def _sign(header_b64: str, payload_b64: str, secret: str) -> str:
    msg = f"{header_b64}.{payload_b64}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
    return _b64enc(sig)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload["exp"] = int(expire.timestamp())
    header = _b64enc(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64enc(json.dumps(payload).encode())
    sig = _sign(header, body, settings.jwt_secret)
    return f"{header}.{body}.{sig}"


def decode_token(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token format")
    header, body, sig = parts
    expected = _sign(header, body, settings.jwt_secret)
    if not hmac.compare_digest(expected, sig):
        raise ValueError("Invalid token signature")
    payload = json.loads(_b64dec(body))
    if "exp" in payload and payload["exp"] < datetime.now(timezone.utc).timestamp():
        raise ValueError("Token expired")
    return payload

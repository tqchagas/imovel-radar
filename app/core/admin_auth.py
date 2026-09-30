"""Password-only session authentication for the private admin panel."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException, Request, Response

from app.core.config import settings

ADMIN_COOKIE = "imovel_radar_admin"


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_session() -> tuple[str, int]:
    ttl = max(60, settings.admin_session_ttl_seconds)
    expires = int(time.time()) + ttl
    payload = f"{expires}.{secrets.token_urlsafe(18)}".encode("ascii")
    signature = hmac.new(settings.admin_password.encode("utf-8"), payload, hashlib.sha256).digest()
    return f"{_b64encode(payload)}.{_b64encode(signature)}", ttl


def valid_session(token: str | None) -> bool:
    if not settings.admin_password or not token or len(token) > 512:
        return False
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        payload = _b64decode(encoded_payload)
        supplied_signature = _b64decode(encoded_signature)
        expires_text, nonce = payload.decode("ascii").split(".", 1)
        expires = int(expires_text)
        if not nonce or expires <= int(time.time()):
            return False
    except (ValueError, UnicodeDecodeError):
        return False

    expected_signature = hmac.new(
        settings.admin_password.encode("utf-8"), payload, hashlib.sha256
    ).digest()
    return hmac.compare_digest(supplied_signature, expected_signature)


def require_admin(request: Request, response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    if not settings.admin_password:
        raise HTTPException(status_code=503, detail="acesso administrativo não configurado")
    if not valid_session(request.cookies.get(ADMIN_COOKIE)):
        raise HTTPException(status_code=401, detail="faça login para continuar")

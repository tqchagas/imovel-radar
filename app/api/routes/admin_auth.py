"""Login endpoints for the password-only admin panel."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.core.admin_auth import ADMIN_COOKIE, issue_session, valid_session
from app.core.config import settings

router = APIRouter(prefix="/admin/api", tags=["admin-auth"])


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=512)


def _cookie_secure(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return forwarded_proto.split(",", 1)[0].strip().lower() == "https"


@router.get("/session")
def session_status(request: Request, response: Response) -> dict[str, bool]:
    response.headers["Cache-Control"] = "no-store"
    return {
        "configured": bool(settings.admin_password),
        "authenticated": valid_session(request.cookies.get(ADMIN_COOKIE)),
    }


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, bool]:
    response.headers["Cache-Control"] = "no-store"
    configured_password = settings.admin_password
    if not configured_password:
        raise HTTPException(status_code=503, detail="configure ADMIN_PASSWORD para habilitar o painel")
    if not hmac.compare_digest(
        payload.password.encode("utf-8"), configured_password.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="senha incorreta")

    token, ttl = issue_session()
    response.set_cookie(
        ADMIN_COOKIE,
        token,
        max_age=ttl,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="strict",
        path="/admin",
    )
    return {"authenticated": True}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    response.headers["Cache-Control"] = "no-store"
    response.delete_cookie(
        ADMIN_COOKIE,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="strict",
        path="/admin",
    )
    return {"authenticated": False}

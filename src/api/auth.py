"""
Lightweight API auth helpers for capstone use.

Supports optional API, admin, and metrics tokens via headers.
"""

from fastapi import Header, HTTPException, status

from ..config import settings


def _extract_token(authorization: str | None, x_api_key: str | None) -> str | None:
    if x_api_key:
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def require_api_token(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    """Require API token if configured."""
    if not settings.api_token:
        return
    token = _extract_token(authorization, x_api_key)
    if token != settings.api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def require_admin_token(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    """Require admin token if configured."""
    if not settings.admin_token:
        return
    token = _extract_token(authorization, x_api_key)
    if token != settings.admin_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def require_metrics_token(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    """Require metrics token if configured."""
    if not settings.metrics_token:
        return
    token = _extract_token(authorization, x_api_key)
    if token != settings.metrics_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

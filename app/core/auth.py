"""
Keycloak JWT Authentication middleware.

Validates Bearer tokens from Flowable against the Keycloak JWKS endpoint.
Disabled in development via AUTH_ENABLED=false.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

import httpx
import structlog
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import Settings, get_settings

logger = structlog.get_logger()
security = HTTPBearer(auto_error=False)

_jwks_cache: Optional[dict] = None


async def _fetch_jwks(keycloak_url: str) -> dict:
    global _jwks_cache
    if _jwks_cache:
        return _jwks_cache
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{keycloak_url}/protocol/openid-connect/certs")
        resp.raise_for_status()
        _jwks_cache = resp.json()
        return _jwks_cache


async def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    settings: Settings = Depends(get_settings),
) -> dict:
    """
    FastAPI dependency: extracts and validates the JWT.
    Returns the decoded token payload (claims).
    """
    if not settings.auth_enabled:
        return {"sub": "dev-user", "roles": ["risk-engine-admin"]}

    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = credentials.credentials
    try:
        jwks = await _fetch_jwks(settings.keycloak_url)
        unverified_header = jwt.get_unverified_header(token)
        key = next(
            (k for k in jwks.get("keys", []) if k["kid"] == unverified_header.get("kid")),
            None,
        )
        if not key:
            raise HTTPException(status_code=401, detail="Invalid token signing key")

        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.keycloak_audience,
            issuer=settings.keycloak_url,
        )
        return payload

    except JWTError as e:
        logger.warning("jwt_validation_failed", error=str(e))
        raise HTTPException(status_code=401, detail=f"Token validation failed: {e}")

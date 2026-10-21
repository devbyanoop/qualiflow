import time

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .settings import settings

# auto_error=False so a missing header falls through to our own 401 below,
# instead of FastAPI's HTTPBearer default of 403 for "no credentials at
# all" — one status code for "not authenticated", whatever the reason.
_security = HTTPBearer(auto_error=False)

_JWKS_TTL_SECONDS = 300
_jwks_cache: dict = {"keys": None, "fetched_at": 0.0}


def _get_jwks() -> dict:
    """Fetch Keycloak's public signing keys, re-fetching at most every
    5 minutes. Keycloak rotates keys occasionally; a short TTL means we
    notice a rotation within minutes without hitting the discovery
    endpoint on every single request."""
    now = time.time()
    if _jwks_cache["keys"] is None or (now - _jwks_cache["fetched_at"]) > _JWKS_TTL_SECONDS:
        discovery = httpx.get(
            f"{settings.keycloak_issuer}/.well-known/openid-configuration", timeout=5
        ).json()
        _jwks_cache["keys"] = httpx.get(discovery["jwks_uri"], timeout=5).json()
        _jwks_cache["fetched_at"] = now
    return _jwks_cache["keys"]


def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> dict:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    token = credentials.credentials
    try:
        unverified_header = jwt.get_unverified_header(token)
        jwks = _get_jwks()
        key_data = next(k for k in jwks["keys"] if k["kid"] == unverified_header["kid"])
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
        payload = jwt.decode(
            token,
            key=public_key,
            algorithms=["RS256"],
            issuer=settings.keycloak_issuer,
            # This client-credentials token's aud is "account" (Keycloak's
            # default), not this API — not checking it here. Revisit with
            # a dedicated audience once there's more than one client.
            options={"verify_aud": False},
            # Keycloak runs on a different machine (the remote Fedora
            # host) with a few seconds of normal clock drift from this
            # one — 10s leeway absorbs that without masking a real
            # problem (iat/exp off by minutes would still fail).
            leeway=10,
        )
    except (jwt.PyJWTError, StopIteration) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc

    return payload

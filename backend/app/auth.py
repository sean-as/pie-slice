"""
Password hashing (bcrypt) and session handling. Every route that isn't
POST /auth/signup or POST /auth/login depends on `get_current_user`, which is
what makes an endpoint "require auth" — see ../openapi.yaml's `security`
blocks, which this mirrors 1:1.

The browser session is an HttpOnly cookie, so page scripts can never read the
token. `Authorization: Bearer` is still accepted for tests and tools.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

import bcrypt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.models import Group
from app.store import StoredUser, store, token_ttl

bearer_scheme = HTTPBearer(auto_error=False)

SESSION_COOKIE = "pie_session"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# Defaults to the Vite dev/preview servers. Set CORS_ORIGINS (comma-separated)
# only if the frontend is served from a different origin than the API; the
# single-container deployment is same-origin and needs none.
_DEV_ORIGINS = "http://localhost:5173,http://localhost:4173,http://127.0.0.1:5173,http://127.0.0.1:4173"


def allowed_origins() -> list[str]:
    return [o.strip() for o in os.environ.get("CORS_ORIGINS", _DEV_ORIGINS).split(",") if o.strip()]


def _cookie_secure() -> bool:
    # Secure by default. Set COOKIE_SECURE=false only for plain-http local dev
    # (Safari refuses Secure cookies on http://localhost).
    return os.environ.get("COOKIE_SECURE", "true").strip().lower() in ("1", "true", "yes", "on")


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(token_ttl().total_seconds()),
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE, httponly=True, secure=_cookie_secure(), samesite="lax", path="/"
    )


def _reject_cross_site_write(request: Request) -> None:
    """
    SameSite=Lax already keeps the browser from attaching the cookie to
    cross-site POST/PUT/DELETE; this is the second layer. A state-changing
    request authenticated by cookie must come from this site (or a configured
    CORS origin), judged by the Origin header browsers send on such requests.
    """
    if request.method in _SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin is None:
        return  # not a browser cross-origin request
    if urlparse(origin).netloc == request.headers.get("host") or origin in allowed_origins():
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-site request blocked.")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def require_same_site(request: Request) -> None:
    """Dependency for the auth endpoints, which are state-changing but not cookie-authenticated."""
    _reject_cross_site_write(request)


def optional_session_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str | None:
    """Like get_session_token, but None instead of 401 when nobody is logged in."""
    if credentials is not None:
        return credentials.credentials
    return request.cookies.get(SESSION_COOKIE) or None


def get_session_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    """The caller's token: the Authorization header if sent, otherwise the session cookie."""
    if credentials is not None:
        return credentials.credentials
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        _reject_cross_site_write(request)
        return cookie
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")


def get_current_user(token: str = Depends(get_session_token)) -> StoredUser:
    user_id = store.user_id_for_token(token)
    user = store.get_user(user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")

    return user


def require_group_membership(group_id: str, current_user: StoredUser = Depends(get_current_user)) -> Group:
    """
    Shared by every /groups/{group_id}/... route. 404 for both "doesn't
    exist" and "exists but you're not a linked member" — see
    ../openapi.yaml's Authentication section for why those collapse to one
    response.
    """
    group = store.get_group_for_member(group_id, current_user.id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")
    return group


def require_members(group: Group, member_ids: list[str]) -> None:
    """
    Rejects any member id that isn't in this group. Without this an expense
    could name a payer (or split participant) belonging to a *different*
    group: the row would land in this group's list, but compute_balances
    only tallies ids in this group's member list, so the money would
    silently vanish from the group's totals.
    """
    known = {m.id for m in group.members}
    unknown = [member_id for member_id in member_ids if member_id not in known]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not a member of this group.",
        )

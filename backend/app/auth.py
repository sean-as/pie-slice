"""
Password hashing (bcrypt) and bearer-token session handling. Every route
that isn't POST /auth/signup or POST /auth/login depends on
`get_current_user`, which is what makes an endpoint "require auth" — see
../openapi.yaml's `security` blocks, which this mirrors 1:1.
"""

from __future__ import annotations

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.models import Group
from app.store import StoredUser, store

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> StoredUser:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")

    user_id = store.user_id_for_token(credentials.credentials)
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

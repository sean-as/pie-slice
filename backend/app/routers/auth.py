from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from app.auth import bearer_scheme, get_current_user, hash_password, verify_password
from app.models import AuthResponse, LoginInput, SignupInput, User
from app.store import StoredUser, store

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupInput) -> AuthResponse:
    if store.find_user_by_email(body.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An account with that email already exists."
        )

    user = store.create_user(body.email, body.display_name, hash_password(body.password))
    token = store.issue_token(user.id)
    return AuthResponse(user=user.to_public(), token=token)


@router.post("/login", response_model=AuthResponse)
def login(body: LoginInput) -> AuthResponse:
    user = store.find_user_by_email(body.email)
    # Generic error either way — never reveal whether the email exists.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    token = store.issue_token(user.id)
    return AuthResponse(user=user.to_public(), token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    _current_user: StoredUser = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> None:
    store.revoke_token(credentials.credentials)


@router.get("/me", response_model=User)
def get_me(current_user: StoredUser = Depends(get_current_user)) -> User:
    return current_user.to_public()

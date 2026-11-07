from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth import (
    clear_session_cookie,
    get_current_user,
    hash_password,
    optional_session_token,
    require_same_site,
    set_session_cookie,
    verify_password,
)
from app.models import AuthResponse, LoginInput, SignupInput, User
from app.store import StoredUser, store

# Signup, login and logout change session state without a cookie to check, so
# a cross-site page must not be able to trigger them (login CSRF).
router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(require_same_site)])


def _end_existing_session(request: Request) -> None:
    """Logging in or signing up replaces whatever session the browser already had."""
    existing = optional_session_token(request, None)
    if existing:
        store.revoke_token(existing)


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupInput, request: Request, response: Response) -> AuthResponse:
    if store.find_user_by_email(body.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An account with that email already exists."
        )

    user = store.create_user(body.email, body.display_name, hash_password(body.password))
    _end_existing_session(request)
    set_session_cookie(response, store.issue_token(user.id))
    return AuthResponse(user=user.to_public())


@router.post("/login", response_model=AuthResponse)
def login(body: LoginInput, request: Request, response: Response) -> AuthResponse:
    user = store.find_user_by_email(body.email)
    # Generic error either way — never reveal whether the email exists.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    _end_existing_session(request)
    set_session_cookie(response, store.issue_token(user.id))
    return AuthResponse(user=user.to_public())


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, token: str | None = Depends(optional_session_token)) -> None:
    """Idempotent: always clears the cookie, even if the session already expired."""
    if token:
        store.revoke_token(token)
    clear_session_cookie(response)


@router.get("/me", response_model=User)
def get_me(current_user: StoredUser = Depends(get_current_user)) -> User:
    return current_user.to_public()

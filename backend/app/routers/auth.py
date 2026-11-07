from __future__ import annotations

import os
import secrets

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
from app.ratelimit import client_ip, login_email_limiter, login_ip_limiter, signup_limiter
from app.store import StoredUser, store

# Signup, login and logout change session state without a cookie to check, so
# a cross-site page must not be able to trigger them (login CSRF).
# Verified against when the email is unknown, so a miss costs the same bcrypt
# time as a wrong password and response time does not reveal which emails exist.
_DUMMY_HASH = hash_password("not-a-real-password")

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(require_same_site)])


def _check_invite_code(supplied: str | None) -> None:
    """
    When SIGNUP_CODE is set, signup needs it; unset (dev, tests) leaves signup
    open. Checked before the duplicate-email lookup so an outsider cannot use
    the 409 to find out which emails have accounts.
    """
    required = os.environ.get("SIGNUP_CODE", "").strip()
    if not required:
        return
    if not secrets.compare_digest((supplied or "").strip().encode(), required.encode()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid invite code.")


def _end_existing_session(request: Request) -> None:
    """Logging in or signing up replaces whatever session the browser already had."""
    existing = optional_session_token(request, None)
    if existing:
        store.revoke_token(existing)


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupInput, request: Request, response: Response) -> AuthResponse:
    ip = client_ip(request)
    if ip:
        signup_limiter.attempt(ip)  # counted up front; given back once the code checks out
    _check_invite_code(body.invite_code)
    if ip:
        signup_limiter.forgive(ip)

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
    # Count the attempt before the slow bcrypt check, so concurrent guesses cannot
    # all pass the limit; it is given back below if the login succeeds. Unknown
    # emails count too, so the limit cannot reveal which emails have accounts.
    ip = client_ip(request)
    email = body.email.strip().lower()
    if ip:
        login_ip_limiter.attempt(ip)
    try:
        login_email_limiter.attempt(email)
    except HTTPException:
        if ip:
            login_ip_limiter.forgive(ip)
        raise

    user = store.find_user_by_email(body.email)
    password_ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    # Generic error either way — never reveal whether the email exists.
    if user is None or not password_ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    if ip:
        login_ip_limiter.forgive(ip)
    login_email_limiter.reset(email)

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

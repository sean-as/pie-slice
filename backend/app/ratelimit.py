"""
Brute-force protection for login and signup: count attempts per key in a
sliding window and refuse further ones while a key is full.

An attempt is counted *before* the slow work (bcrypt) and given back with
`forgive` if it turns out to be legitimate, so a burst of concurrent requests
cannot all slip under the limit.

State is in memory, which is correct for the deployed shape (one uvicorn
worker, see the Dockerfile) and simply resets on restart. A second worker
would need a shared store.
"""

from __future__ import annotations

import ipaddress
import logging
import threading
import time
from collections import OrderedDict, deque

from fastapi import HTTPException, Request, status

logger = logging.getLogger("pieslice.ratelimit")


def _now() -> float:  # a seam for tests
    return time.monotonic()


class FailureLimiter:
    def __init__(self, name: str, limit: int, window_seconds: float, max_keys: int = 10_000) -> None:
        self.name = name
        self.limit = limit
        self.window = window_seconds
        self.max_keys = max_keys
        # Oldest-touched first, so the cap can evict from the front.
        self._attempts: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def _live(self, key: str, now: float) -> deque[float]:
        attempts = self._attempts.get(key)
        if attempts is None:
            return deque()
        while attempts and now - attempts[0] > self.window:
            attempts.popleft()
        if not attempts:
            del self._attempts[key]
            return deque()
        return attempts

    def attempt(self, *keys: str) -> None:
        """Counts an attempt for every key, or raises 429 (counting nothing) if any key is full."""
        now = _now()
        with self._lock:
            for key in keys:
                attempts = self._live(key, now)
                if len(attempts) >= self.limit:
                    retry_after = max(1, int(self.window - (now - attempts[0])) + 1)
                    logger.warning("rate limit %s reached for %s", self.name, key)
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Too many attempts. Try again later.",
                        headers={"Retry-After": str(retry_after)},
                    )
            for key in keys:
                self._attempts.setdefault(key, deque()).append(now)
                self._attempts.move_to_end(key)
            while len(self._attempts) > self.max_keys:
                self._attempts.popitem(last=False)  # hard cap: drop the stalest key

    def forgive(self, *keys: str) -> None:
        """Gives back the most recent counted attempt (it turned out to be legitimate)."""
        with self._lock:
            for key in keys:
                attempts = self._attempts.get(key)
                if attempts:
                    attempts.pop()
                    if not attempts:
                        del self._attempts[key]

    def reset(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._attempts.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._attempts.clear()


# Per source address: tight, since one person has one address.
# Per email: loose, so one source cannot lock a member out of their own
# account (that would take several addresses), yet guessing stays impractical.
login_ip_limiter = FailureLimiter("login-ip", limit=10, window_seconds=15 * 60)
login_email_limiter = FailureLimiter("login-email", limit=50, window_seconds=15 * 60)
signup_limiter = FailureLimiter("signup-ip", limit=10, window_seconds=15 * 60)

_warned_no_forwarded_for = False


def _normalize(raw: str) -> str:
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return raw[:64]
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        # One IPv6 subscriber controls a whole /64; rotating inside it must not
        # earn a fresh budget.
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


def client_ip(request: Request) -> str | None:
    """
    The caller's address as the reverse proxy saw it: the *last* X-Forwarded-For
    entry, because earlier ones can be forged by the client. Without that header
    there is no trustworthy address (the TCP peer is the Docker gateway, the same
    for everyone), so return None and let callers skip the per-IP limit rather
    than lump every visitor into one bucket.
    """
    global _warned_no_forwarded_for
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        last = forwarded.split(",")[-1].strip()
        if last:
            return _normalize(last)
    if not _warned_no_forwarded_for:
        _warned_no_forwarded_for = True
        logger.warning("no X-Forwarded-For on a rate-limited request; per-IP limits are skipped")
    return None

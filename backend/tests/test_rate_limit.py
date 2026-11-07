from __future__ import annotations

import threading

import pytest

from app import ratelimit
from app.ratelimit import FailureLimiter, login_email_limiter, login_ip_limiter, signup_limiter

LOGIN = "/api/auth/login"
SIGNUP = "/api/auth/signup"


@pytest.fixture
def small_limits(monkeypatch):
    """Same behaviour, fewer slow bcrypt calls per test."""
    monkeypatch.setattr(login_ip_limiter, "limit", 3)
    monkeypatch.setattr(login_email_limiter, "limit", 5)
    monkeypatch.setattr(signup_limiter, "limit", 3)


def _bad_login(client, email="alice@example.com", ip="203.0.113.7", password="wrong-password"):
    headers = {"X-Forwarded-For": ip} if ip else {}
    return client.post(LOGIN, json={"email": email, "password": password}, headers=headers)


def test_the_deployed_limits():
    assert (login_ip_limiter.limit, login_ip_limiter.window) == (10, 15 * 60)
    assert login_email_limiter.limit == 50  # loose: one source must not be able to lock a member out
    assert signup_limiter.limit == 10


@pytest.mark.usefixtures("small_limits")
class TestLoginLimit:
    def test_one_ip_is_locked_out_after_the_limit(self, client, signup):
        signup(email="alice@example.com", password="password123")
        for _ in range(3):
            assert _bad_login(client).status_code == 401
        blocked = _bad_login(client)
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) >= 1

    def test_the_right_password_is_refused_while_the_ip_is_locked_out(self, client, signup):
        signup(email="alice@example.com", password="password123")
        for _ in range(3):
            _bad_login(client)
        ok = _bad_login(client, password="password123")
        assert ok.status_code == 429

    def test_unknown_emails_are_limited_too(self, client):
        for n in range(3):
            assert _bad_login(client, email=f"nobody{n}@example.com").status_code == 401
        assert _bad_login(client, email="nobody@example.com").status_code == 429

    def test_other_ips_are_not_affected(self, client, signup):
        signup(email="alice@example.com", password="password123")
        for _ in range(3):
            _bad_login(client)
        assert _bad_login(client, ip="198.51.100.9").status_code == 401

    def test_one_ip_cannot_lock_a_member_out_of_their_own_account(self, client, signup):
        signup(email="alice@example.com", password="password123")
        for _ in range(3):
            _bad_login(client, ip="203.0.113.7")  # attacker's address hits its own limit
        assert _bad_login(client, ip="203.0.113.7").status_code == 429
        member = _bad_login(client, ip="198.51.100.9", password="password123")
        assert member.status_code == 200  # the member, from their own address, still gets in

    def test_many_ips_hammering_one_account_hit_the_email_limit(self, client, signup):
        signup(email="alice@example.com", password="password123")
        for n in range(5):
            assert _bad_login(client, ip=f"198.51.100.{n}").status_code == 401
        assert _bad_login(client, ip="198.51.100.200").status_code == 429

    def test_a_successful_login_clears_that_accounts_failures(self, client, signup):
        signup(email="alice@example.com", password="password123")
        for n in range(4):
            _bad_login(client, ip=f"198.51.100.{n}")
        assert _bad_login(client, ip="198.51.100.50", password="password123").status_code == 200
        for n in range(4):
            assert _bad_login(client, ip=f"198.51.100.{60 + n}").status_code == 401

    def test_a_successful_login_does_not_use_up_the_ips_budget(self, client, signup):
        signup(email="alice@example.com", password="password123")
        for _ in range(10):
            assert _bad_login(client, password="password123").status_code == 200

    def test_email_case_and_spacing_do_not_dodge_the_limit(self, client, signup):
        signup(email="alice@example.com", password="password123")
        for n, variant in enumerate(["alice@example.com", "ALICE@example.com", " Alice@Example.com", "alice@EXAMPLE.com", "aLiCe@example.com"]):
            _bad_login(client, email=variant, ip=f"198.51.100.{n}")
        assert _bad_login(client, ip="198.51.100.99").status_code == 429

    def test_attempts_are_allowed_again_after_the_window(self, client, signup, monkeypatch):
        signup(email="alice@example.com", password="password123")
        clock = [1000.0]
        monkeypatch.setattr(ratelimit, "_now", lambda: clock[0])
        for _ in range(3):
            _bad_login(client)
        assert _bad_login(client).status_code == 429
        clock[0] += 15 * 60 + 1
        assert _bad_login(client).status_code == 401

    def test_a_429_is_returned_at_exactly_the_window_edge_with_a_positive_retry_after(self, client, signup, monkeypatch):
        signup(email="alice@example.com", password="password123")
        clock = [1000.0]
        monkeypatch.setattr(ratelimit, "_now", lambda: clock[0])
        for _ in range(3):
            _bad_login(client)
        clock[0] += 15 * 60  # the oldest attempt is exactly `window` old
        blocked = _bad_login(client)
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) >= 1


@pytest.mark.usefixtures("small_limits")
class TestWithoutAForwardedAddress:
    def test_the_per_ip_limit_is_skipped_not_shared_by_everyone(self, client, signup):
        signup(email="alice@example.com", password="password123")
        # Many failed logins for *different* accounts, with no X-Forwarded-For:
        # they must not be lumped into one shared bucket and lock everyone out.
        for n in range(6):
            assert _bad_login(client, email=f"user{n}@example.com", ip=None).status_code == 401
        assert _bad_login(client, password="password123", ip=None).status_code == 200

    def test_the_email_limit_still_applies(self, client):
        for _ in range(5):
            _bad_login(client, ip=None)
        assert _bad_login(client, ip=None).status_code == 429


@pytest.mark.usefixtures("small_limits")
class TestSignupLimit:
    BODY = {"email": "new@example.com", "displayName": "New", "password": "password123"}

    def _post(self, client, code, ip="203.0.113.7", **extra):
        return client.post(SIGNUP, json={**self.BODY, "inviteCode": code, **extra}, headers={"X-Forwarded-For": ip})

    def test_guessing_the_invite_code_is_limited(self, client, monkeypatch):
        monkeypatch.setenv("SIGNUP_CODE", "s3cret-code-that-is-long-enough")
        for n in range(3):
            assert self._post(client, f"guess{n}").status_code == 403
        assert self._post(client, "s3cret-code-that-is-long-enough").status_code == 429

    def test_other_addresses_are_unaffected(self, client, monkeypatch):
        monkeypatch.setenv("SIGNUP_CODE", "s3cret-code-that-is-long-enough")
        for n in range(3):
            self._post(client, f"guess{n}")
        assert self._post(client, "s3cret-code-that-is-long-enough", ip="198.51.100.9").status_code == 201

    def test_valid_signups_do_not_count_against_the_limit(self, client, monkeypatch):
        monkeypatch.setenv("SIGNUP_CODE", "s3cret-code-that-is-long-enough")
        for n in range(8):
            assert self._post(client, "s3cret-code-that-is-long-enough", email=f"u{n}@example.com").status_code == 201


class TestClientIp:
    def test_uses_the_last_forwarded_entry_not_one_the_client_could_forge(self, client, monkeypatch):
        monkeypatch.setattr(login_ip_limiter, "limit", 3)
        for n in range(3):
            _bad_login(client, email=f"user{n}@example.com", ip=f"1.1.1.{n}, 203.0.113.7")
        assert _bad_login(client, email="x@example.com", ip="9.9.9.9, 203.0.113.7").status_code == 429

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("203.0.113.7", "203.0.113.7"),
            ("2001:db8:1:2:aaaa:bbbb:cccc:dddd", "2001:db8:1:2::/64"),
            ("2001:db8:1:2:1111:2222:3333:4444", "2001:db8:1:2::/64"),  # same /64 -> same key
            ("::ffff:203.0.113.7", "203.0.113.7"),
            ("not-an-ip", "not-an-ip"),
        ],
    )
    def test_addresses_are_normalised_so_rotation_inside_a_subnet_gains_nothing(self, raw, expected):
        assert ratelimit._normalize(raw) == expected


class TestFailureLimiter:
    def test_memory_is_hard_capped_even_when_every_key_is_fresh(self):
        limiter = FailureLimiter("t", limit=3, window_seconds=3600, max_keys=50)
        for n in range(500):
            limiter.attempt(f"k{n}")
        assert len(limiter._attempts) == 50
        assert "k499" in limiter._attempts and "k0" not in limiter._attempts

    def test_concurrent_attempts_cannot_overshoot_the_limit(self):
        limiter = FailureLimiter("t", limit=5, window_seconds=60)
        allowed = []
        barrier = threading.Barrier(40)

        def worker():
            barrier.wait()
            try:
                limiter.attempt("same")
                allowed.append(1)
            except Exception:
                pass

        threads = [threading.Thread(target=worker) for _ in range(40)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert len(allowed) == 5

    def test_forgive_gives_back_one_attempt(self):
        limiter = FailureLimiter("t", limit=2, window_seconds=60)
        limiter.attempt("k")
        limiter.attempt("k")
        limiter.forgive("k")
        limiter.attempt("k")  # room again

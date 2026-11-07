from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import session_token
from app.store import store

CREDS = {"email": "alice@example.com", "displayName": "Alice", "password": "password123"}


@pytest.fixture
def browser() -> TestClient:
    """https, because the session cookie is Secure and would not be sent over http."""
    return TestClient(app, base_url="https://testserver")


def _signup(client: TestClient):
    response = client.post("/api/auth/signup", json=CREDS)
    assert response.status_code == 201
    return response


class TestSessionCookie:
    def test_signup_sets_a_hardened_cookie(self, browser):
        header = _signup(browser).headers["set-cookie"].lower()
        assert "pie_session=" in header
        assert "httponly" in header
        assert "secure" in header
        assert "samesite=lax" in header
        assert "max-age=7776000" in header  # 90 days
        assert "path=/" in header

    def test_login_sets_the_cookie_too(self, browser):
        _signup(browser)
        browser.cookies.clear()
        response = browser.post("/api/auth/login", json={"email": CREDS["email"], "password": CREDS["password"]})
        assert "pie_session=" in response.headers["set-cookie"]

    def test_secure_flag_can_be_turned_off_for_local_http(self, browser, monkeypatch):
        monkeypatch.setenv("COOKIE_SECURE", "false")
        assert "secure" not in _signup(browser).headers["set-cookie"].lower()

    def test_cookie_authenticates_without_an_authorization_header(self, browser):
        _signup(browser)
        me = browser.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == CREDS["email"]

    def test_no_cookie_and_no_header_is_401(self, browser):
        assert browser.get("/api/auth/me").status_code == 401

    def test_bogus_cookie_is_401(self, browser):
        browser.cookies.set("pie_session", "not-a-real-token")
        assert browser.get("/api/auth/me").status_code == 401

    def test_authorization_header_still_works_with_no_cookie(self, client, signup):
        headers, _ = signup(email="bearer@example.com")
        assert client.get("/api/auth/me", headers=headers).status_code == 200

    def test_logout_revokes_the_token_and_clears_the_cookie(self, browser):
        token = session_token(_signup(browser))
        response = browser.post("/api/auth/logout")
        assert response.status_code == 204
        cleared = response.headers["set-cookie"].lower()
        assert "pie_session=" in cleared and ("max-age=0" in cleared or "expires=" in cleared)
        assert store.user_id_for_token(token) is None
        assert browser.get("/api/auth/me").status_code == 401


class TestCrossSiteWrites:
    def test_cookie_write_from_another_origin_is_blocked(self, browser):
        _signup(browser)
        response = browser.post(
            "/api/groups", json={"name": "Trip"}, headers={"Origin": "https://evil.example"}
        )
        assert response.status_code == 403

    def test_cookie_write_from_the_same_origin_is_allowed(self, browser):
        _signup(browser)
        response = browser.post(
            "/api/groups", json={"name": "Trip"}, headers={"Origin": "https://testserver"}
        )
        assert response.status_code == 201

    def test_cookie_write_from_a_configured_cors_origin_is_allowed(self, browser):
        _signup(browser)
        response = browser.post(
            "/api/groups", json={"name": "Trip"}, headers={"Origin": "http://localhost:5173"}
        )
        assert response.status_code == 201

    def test_reads_from_another_origin_are_not_blocked_by_the_check(self, browser):
        _signup(browser)
        response = browser.get("/api/auth/me", headers={"Origin": "https://evil.example"})
        assert response.status_code == 200

    def test_bearer_requests_are_not_subject_to_the_origin_check(self, client, signup):
        headers, _ = signup()
        response = client.post(
            "/api/groups", json={"name": "Trip"}, headers={**headers, "Origin": "https://evil.example"}
        )
        assert response.status_code == 201


class TestLogoutAndSessionReplacement:
    def test_logout_without_a_session_is_still_204_and_clears_the_cookie(self, browser):
        response = browser.post("/api/auth/logout")
        assert response.status_code == 204
        assert "pie_session=" in response.headers["set-cookie"]

    def test_logout_with_an_expired_session_still_clears_the_cookie(self, browser):
        browser.cookies.set("pie_session", "revoked-or-expired")
        response = browser.post("/api/auth/logout")
        assert response.status_code == 204
        assert "pie_session=" in response.headers["set-cookie"]

    def test_login_revokes_the_session_it_replaces(self, browser):
        old = session_token(_signup(browser))
        browser.post("/api/auth/login", json={"email": CREDS["email"], "password": CREDS["password"]})
        assert store.user_id_for_token(old) is None
        assert browser.get("/api/auth/me").status_code == 200  # the new session works

    @pytest.mark.parametrize("path", ["/api/auth/login", "/api/auth/signup", "/api/auth/logout"])
    def test_auth_endpoints_reject_other_origins(self, browser, path):
        response = browser.post(path, json=CREDS, headers={"Origin": "https://evil.example"})
        assert response.status_code == 403

    def test_the_token_is_not_in_the_response_body(self, browser):
        assert "token" not in _signup(browser).json()

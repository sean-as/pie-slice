from __future__ import annotations


class TestSignup:
    def test_creates_account_and_sets_the_session_cookie(self, client):
        response = client.post(
            "/api/auth/signup",
            json={"email": "alice@example.com", "displayName": "Alice", "password": "password123"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["user"]["email"] == "alice@example.com"
        assert body["user"]["displayName"] == "Alice"
        assert "id" in body["user"]
        assert "password" not in body["user"]
        assert "passwordHash" not in body["user"]
        assert "token" not in body  # the token is only ever in the HttpOnly cookie
        assert "pie_session=" in response.headers["set-cookie"]

    def test_rejects_duplicate_email(self, client, signup):
        signup(email="alice@example.com")
        response = client.post(
            "/api/auth/signup",
            json={"email": "alice@example.com", "displayName": "Alice 2", "password": "password123"},
        )
        assert response.status_code == 409

    def test_rejects_short_password(self, client):
        response = client.post(
            "/api/auth/signup",
            json={"email": "alice@example.com", "displayName": "Alice", "password": "short"},
        )
        assert response.status_code == 422


class TestLogin:
    def test_logs_in_with_correct_credentials(self, client, signup):
        signup(email="alice@example.com", password="password123")
        response = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "password123"})
        assert response.status_code == 200
        assert "token" not in response.json()
        assert "pie_session=" in response.headers["set-cookie"]

    def test_rejects_wrong_password(self, client, signup):
        signup(email="alice@example.com", password="password123")
        response = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "wrong"})
        assert response.status_code == 401

    def test_rejects_unknown_email_with_same_generic_message_as_wrong_password(self, client, signup):
        signup(email="alice@example.com", password="password123")

        wrong_password = client.post(
            "/api/auth/login", json={"email": "alice@example.com", "password": "wrong"}
        )
        unknown_email = client.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": "password123"}
        )

        assert wrong_password.status_code == unknown_email.status_code == 401
        assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


class TestLogoutAndMe:
    def test_me_requires_a_token(self, client):
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_me_returns_current_user(self, client, signup):
        headers, user = signup(email="alice@example.com")
        response = client.get("/api/auth/me", headers=headers)
        assert response.status_code == 200
        assert response.json()["id"] == user["id"]

    def test_logout_invalidates_the_token(self, client, signup):
        headers, _ = signup(email="alice@example.com")

        logout_response = client.post("/api/auth/logout", headers=headers)
        assert logout_response.status_code == 204

        me_response = client.get("/api/auth/me", headers=headers)
        assert me_response.status_code == 401

    def test_bogus_token_is_rejected(self, client):
        response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
        assert response.status_code == 401


class TestInviteCode:
    BODY = {"email": "alice@example.com", "displayName": "Alice", "password": "password123"}

    def test_signup_is_open_when_no_code_is_configured(self, client):
        assert client.post("/api/auth/signup", json=self.BODY).status_code == 201

    def test_missing_code_is_rejected_when_one_is_configured(self, client, monkeypatch):
        monkeypatch.setenv("SIGNUP_CODE", "s3cret-code")
        response = client.post("/api/auth/signup", json=self.BODY)
        assert response.status_code == 403
        assert response.json()["detail"] == "Invalid invite code."

    def test_wrong_code_is_rejected(self, client, monkeypatch):
        monkeypatch.setenv("SIGNUP_CODE", "s3cret-code")
        response = client.post("/api/auth/signup", json={**self.BODY, "inviteCode": "nope"})
        assert response.status_code == 403

    def test_correct_code_creates_the_account(self, client, monkeypatch):
        monkeypatch.setenv("SIGNUP_CODE", "s3cret-code")
        response = client.post("/api/auth/signup", json={**self.BODY, "inviteCode": "s3cret-code"})
        assert response.status_code == 201

    def test_surrounding_whitespace_in_the_pasted_code_is_tolerated(self, client, monkeypatch):
        monkeypatch.setenv("SIGNUP_CODE", "s3cret-code")
        response = client.post("/api/auth/signup", json={**self.BODY, "inviteCode": "  s3cret-code\n"})
        assert response.status_code == 201

    def test_code_is_checked_before_revealing_whether_an_email_exists(self, client, signup, monkeypatch):
        signup(email="alice@example.com")  # created while signup was still open
        monkeypatch.setenv("SIGNUP_CODE", "s3cret-code")
        response = client.post("/api/auth/signup", json=self.BODY)  # no code
        assert response.status_code == 403  # not 409

    def test_login_does_not_need_the_code(self, client, signup, monkeypatch):
        signup(email="alice@example.com", password="password123")
        monkeypatch.setenv("SIGNUP_CODE", "s3cret-code")
        response = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "password123"})
        assert response.status_code == 200

    def test_blank_code_on_the_form_is_rejected_when_one_is_configured(self, client, monkeypatch):
        monkeypatch.setenv("SIGNUP_CODE", "s3cret-code")
        for blank in ("", "   "):
            assert client.post("/api/auth/signup", json={**self.BODY, "inviteCode": blank}).status_code == 403

    def test_code_is_case_sensitive(self, client, monkeypatch):
        monkeypatch.setenv("SIGNUP_CODE", "s3cret-code")
        assert client.post("/api/auth/signup", json={**self.BODY, "inviteCode": "S3CRET-CODE"}).status_code == 403

    def test_a_blank_server_setting_means_open_signup(self, client, monkeypatch):
        # Documented fail-open: compose.yaml refuses to start without a value,
        # so production cannot get here by accident.
        for blank in ("", "   "):
            monkeypatch.setenv("SIGNUP_CODE", blank)
            email = f"u{len(blank)}@example.com"
            assert client.post("/api/auth/signup", json={**self.BODY, "email": email}).status_code == 201

    def test_overlong_code_is_rejected_by_validation(self, client, monkeypatch):
        monkeypatch.setenv("SIGNUP_CODE", "s3cret-code")
        assert client.post("/api/auth/signup", json={**self.BODY, "inviteCode": "x" * 1000}).status_code == 422

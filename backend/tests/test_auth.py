from __future__ import annotations


class TestSignup:
    def test_creates_account_and_returns_token(self, client):
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
        assert isinstance(body["token"], str) and len(body["token"]) > 10

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
        assert "token" in response.json()

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

from __future__ import annotations

import os
from typing import Callable

# Must be set before `app.db` (and therefore anything that imports it) is
# ever imported — an isolated in-memory SQLite DB, separate from whatever
# DATABASE_URL is configured for real runs.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.store import store


@pytest.fixture(autouse=True)
def reset_store():
    """
    app.main.seed() runs once at import time; each test gets a clean slate
    and builds whatever data it needs via the API itself (signup, create
    group, ...) so tests never depend on — or leak into — each other.
    """
    store.reset()
    yield
    store.reset()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def signup(client: TestClient) -> Callable[..., tuple[dict[str, str], dict]]:
    """signup() -> (auth_headers, user_json); call with kwargs to customize email/displayName/password."""

    def _signup(email: str = "alice@example.com", display_name: str = "Alice", password: str = "password123"):
        response = client.post(
            "/api/auth/signup",
            json={"email": email, "displayName": display_name, "password": password},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        headers = {"Authorization": f"Bearer {body['token']}"}
        return headers, body["user"]

    return _signup


@pytest.fixture
def group_with_members(client: TestClient, signup):
    """
    Alice creates a group, adds Bob (linked) and Carol (placeholder).
    Returns a dict with headers/users/group/member-id lookups so expense,
    settlement, and balance tests don't each rebuild this from scratch.
    """
    alice_headers, alice = signup(email="alice@example.com", display_name="Alice")
    bob_headers, bob = signup(email="bob@example.com", display_name="Bob")

    group = client.post("/api/groups", json={"name": "Cabin Trip"}, headers=alice_headers).json()
    client.post(f"/api/groups/{group['id']}/members/linked", json={"email": "bob@example.com"}, headers=alice_headers)
    group = client.post(
        f"/api/groups/{group['id']}/members/placeholder", json={"displayName": "Carol"}, headers=alice_headers
    ).json()

    members_by_name = {m["displayName"]: m for m in group["members"]}

    return {
        "group": group,
        "alice_headers": alice_headers,
        "bob_headers": bob_headers,
        "alice_user": alice,
        "bob_user": bob,
        "alice_member": members_by_name["Alice"],
        "bob_member": members_by_name["Bob"],
        "carol_member": members_by_name["Carol"],
    }

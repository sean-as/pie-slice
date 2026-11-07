"""
Sweeps every route in the app, so a new endpoint that forgets its auth or
membership dependency fails here instead of shipping.
"""

from __future__ import annotations

import re

import pytest

from app.main import app

PUBLIC = {("post", "/api/auth/signup"), ("post", "/api/auth/login"), ("post", "/api/auth/logout")}
METHODS = ("get", "post", "put", "patch", "delete")


def _operations():
    for path, item in app.openapi()["paths"].items():
        full = path if path.startswith("/api") else f"/api{path}"
        for method in METHODS:
            if method in item and (method, full) not in PUBLIC and full != "/api/health":
                yield method, full


OPERATIONS = sorted(_operations())
GROUP_OPERATIONS = [(m, p) for m, p in OPERATIONS if "{group_id}" in p]


def _fill(path: str, group_id: str) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: group_id if m.group(1) == "group_id" else "does-not-exist", path)


def test_the_sweep_found_the_routes():
    # Guards the guard: if openapi output changes shape this must not pass vacuously.
    assert len(OPERATIONS) >= 20
    assert len(GROUP_OPERATIONS) >= 15


@pytest.mark.parametrize("method,path", OPERATIONS)
def test_every_route_requires_a_login(client, method, path):
    response = client.request(method, _fill(path, "any"), json={})
    assert response.status_code == 401, f"{method.upper()} {path} is reachable without logging in"


@pytest.mark.parametrize("method,path", GROUP_OPERATIONS)
def test_group_routes_are_invisible_to_non_members(client, signup, method, path):
    owner_headers, _ = signup(email="owner@example.com", display_name="Owner")
    group_id = client.post("/api/groups", json={"name": "Private"}, headers=owner_headers).json()["id"]
    outsider_headers, _ = signup(email="outsider@example.com", display_name="Outsider")

    response = client.request(method, _fill(path, group_id), json={}, headers=outsider_headers)

    assert response.status_code == 404, (
        f"{method.upper()} {path} answered {response.status_code} to a user who is not in the group"
    )


def test_listing_groups_only_shows_your_own(client, signup):
    owner_headers, _ = signup(email="owner@example.com", display_name="Owner")
    client.post("/api/groups", json={"name": "Private"}, headers=owner_headers)
    outsider_headers, _ = signup(email="outsider@example.com", display_name="Outsider")

    assert len(client.get("/api/groups", headers=owner_headers).json()) == 1
    assert client.get("/api/groups", headers=outsider_headers).json() == []

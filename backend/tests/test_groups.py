from __future__ import annotations


class TestCreateAndListGroups:
    def test_creator_becomes_first_linked_member(self, client, signup):
        headers, alice = signup(email="alice@example.com")
        response = client.post("/api/groups", json={"name": "Road Trip"}, headers=headers)
        assert response.status_code == 201
        group = response.json()
        assert group["name"] == "Road Trip"
        assert len(group["members"]) == 1
        assert group["members"][0]["userId"] == alice["id"]
        assert group["members"][0]["displayName"] == "Alice"

    def test_list_groups_only_shows_your_own(self, client, signup):
        alice_headers, _ = signup(email="alice@example.com")
        bob_headers, _ = signup(email="bob@example.com")

        client.post("/api/groups", json={"name": "Alice's Group"}, headers=alice_headers)
        client.post("/api/groups", json={"name": "Bob's Group"}, headers=bob_headers)

        alice_groups = client.get("/api/groups", headers=alice_headers).json()
        bob_groups = client.get("/api/groups", headers=bob_headers).json()

        assert [g["name"] for g in alice_groups] == ["Alice's Group"]
        assert [g["name"] for g in bob_groups] == ["Bob's Group"]

    def test_create_group_requires_auth(self, client):
        response = client.post("/api/groups", json={"name": "No Auth"})
        assert response.status_code == 401


class TestGetGroup:
    def test_member_can_fetch_it(self, client, signup):
        headers, _ = signup()
        group = client.post("/api/groups", json={"name": "Trip"}, headers=headers).json()

        response = client.get(f"/api/groups/{group['id']}", headers=headers)
        assert response.status_code == 200
        assert response.json()["id"] == group["id"]

    def test_nonexistent_group_is_404(self, client, signup):
        headers, _ = signup()
        response = client.get("/api/groups/00000000-0000-0000-0000-000000000000", headers=headers)
        assert response.status_code == 404

    def test_non_member_gets_same_404_as_nonexistent(self, client, signup):
        alice_headers, _ = signup(email="alice@example.com")
        bob_headers, _ = signup(email="bob@example.com")
        group = client.post("/api/groups", json={"name": "Alice Only"}, headers=alice_headers).json()

        not_found = client.get("/api/groups/00000000-0000-0000-0000-000000000000", headers=bob_headers)
        not_a_member = client.get(f"/api/groups/{group['id']}", headers=bob_headers)

        assert not_found.status_code == not_a_member.status_code == 404
        assert not_found.json()["detail"] == not_a_member.json()["detail"]


class TestAddMembers:
    def test_add_linked_member_by_email(self, client, signup):
        alice_headers, _ = signup(email="alice@example.com")
        _, bob = signup(email="bob@example.com", display_name="Bob")
        group = client.post("/api/groups", json={"name": "Trip"}, headers=alice_headers).json()

        response = client.post(
            f"/api/groups/{group['id']}/members/linked",
            json={"email": "bob@example.com"},
            headers=alice_headers,
        )
        assert response.status_code == 200
        members = response.json()["members"]
        assert any(m["userId"] == bob["id"] and m["displayName"] == "Bob" for m in members)

    def test_linked_member_must_have_an_account(self, client, signup):
        headers, _ = signup(email="alice@example.com")
        group = client.post("/api/groups", json={"name": "Trip"}, headers=headers).json()

        response = client.post(
            f"/api/groups/{group['id']}/members/linked",
            json={"email": "nobody@example.com"},
            headers=headers,
        )
        assert response.status_code == 404

    def test_cannot_double_add_same_linked_member(self, client, signup):
        alice_headers, _ = signup(email="alice@example.com")
        signup(email="bob@example.com")
        group = client.post("/api/groups", json={"name": "Trip"}, headers=alice_headers).json()

        client.post(
            f"/api/groups/{group['id']}/members/linked", json={"email": "bob@example.com"}, headers=alice_headers
        )
        second = client.post(
            f"/api/groups/{group['id']}/members/linked", json={"email": "bob@example.com"}, headers=alice_headers
        )
        assert second.status_code == 409

    def test_add_placeholder_member(self, client, signup):
        headers, _ = signup(email="alice@example.com")
        group = client.post("/api/groups", json={"name": "Trip"}, headers=headers).json()

        response = client.post(
            f"/api/groups/{group['id']}/members/placeholder",
            json={"displayName": "Carol"},
            headers=headers,
        )
        assert response.status_code == 200
        members = response.json()["members"]
        carol = next(m for m in members if m["displayName"] == "Carol")
        assert carol["userId"] is None

    def test_non_member_cannot_add_members(self, client, signup):
        alice_headers, _ = signup(email="alice@example.com")
        bob_headers, _ = signup(email="bob@example.com")
        group = client.post("/api/groups", json={"name": "Alice Only"}, headers=alice_headers).json()

        response = client.post(
            f"/api/groups/{group['id']}/members/placeholder",
            json={"displayName": "Carol"},
            headers=bob_headers,
        )
        assert response.status_code == 404

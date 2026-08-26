from __future__ import annotations


def _add_settlement(client, group_id, headers, **overrides):
    body = {
        "fromMemberId": overrides.pop("from_member_id", None),
        "toMemberId": overrides.pop("to_member_id", None),
        "amountCents": 2000,
        "date": "2026-08-26",
    }
    body.update(overrides)
    return client.post(f"/api/groups/{group_id}/settlements", json=body, headers=headers)


class TestAddSettlement:
    def test_records_a_settlement(self, client, group_with_members):
        g = group_with_members
        response = _add_settlement(
            client,
            g["group"]["id"],
            g["bob_headers"],
            from_member_id=g["bob_member"]["id"],
            to_member_id=g["alice_member"]["id"],
            method="Venmo",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["createdByUserId"] == g["bob_user"]["id"]
        assert body["method"] == "Venmo"

    def test_method_is_optional(self, client, group_with_members):
        g = group_with_members
        response = _add_settlement(
            client,
            g["group"]["id"],
            g["alice_headers"],
            from_member_id=g["alice_member"]["id"],
            to_member_id=g["bob_member"]["id"],
        )
        assert response.status_code == 201
        assert response.json()["method"] is None

    def test_amount_must_be_positive(self, client, group_with_members):
        g = group_with_members
        response = _add_settlement(
            client,
            g["group"]["id"],
            g["alice_headers"],
            from_member_id=g["alice_member"]["id"],
            to_member_id=g["bob_member"]["id"],
            amountCents=0,
        )
        assert response.status_code == 422

    def test_non_member_cannot_record_settlement(self, client, group_with_members, signup):
        g = group_with_members
        stranger_headers, _ = signup(email="stranger@example.com")
        response = _add_settlement(
            client,
            g["group"]["id"],
            stranger_headers,
            from_member_id=g["alice_member"]["id"],
            to_member_id=g["bob_member"]["id"],
        )
        assert response.status_code == 404


class TestEditAndDeleteSettlement:
    def _create(self, client, g, headers=None):
        response = _add_settlement(
            client,
            g["group"]["id"],
            headers or g["alice_headers"],
            from_member_id=g["bob_member"]["id"],
            to_member_id=g["alice_member"]["id"],
        )
        assert response.status_code == 201
        return response.json()

    def test_creator_can_edit(self, client, group_with_members):
        g = group_with_members
        settlement = self._create(client, g)

        response = client.put(
            f"/api/groups/{g['group']['id']}/settlements/{settlement['id']}",
            json={
                "fromMemberId": g["bob_member"]["id"],
                "toMemberId": g["alice_member"]["id"],
                "amountCents": 5000,
                "date": "2026-08-28",
                "method": "cash",
            },
            headers=g["alice_headers"],
        )
        assert response.status_code == 200
        assert response.json()["amountCents"] == 5000
        assert response.json()["method"] == "cash"

    def test_non_creator_cannot_edit(self, client, group_with_members):
        g = group_with_members
        settlement = self._create(client, g)

        response = client.put(
            f"/api/groups/{g['group']['id']}/settlements/{settlement['id']}",
            json={
                "fromMemberId": g["bob_member"]["id"],
                "toMemberId": g["alice_member"]["id"],
                "amountCents": 1,
                "date": "2026-08-28",
            },
            headers=g["bob_headers"],
        )
        assert response.status_code == 403

    def test_non_creator_cannot_delete(self, client, group_with_members):
        g = group_with_members
        settlement = self._create(client, g)

        response = client.delete(
            f"/api/groups/{g['group']['id']}/settlements/{settlement['id']}", headers=g["bob_headers"]
        )
        assert response.status_code == 403

    def test_creator_can_delete(self, client, group_with_members):
        g = group_with_members
        settlement = self._create(client, g)

        response = client.delete(
            f"/api/groups/{g['group']['id']}/settlements/{settlement['id']}", headers=g["alice_headers"]
        )
        assert response.status_code == 204

        remaining = client.get(
            f"/api/groups/{g['group']['id']}/settlements", headers=g["alice_headers"]
        ).json()
        assert all(s["id"] != settlement["id"] for s in remaining)

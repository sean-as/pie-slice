from __future__ import annotations


def _add_expense(client, group_id, headers, **overrides):
    body = {
        "description": "Groceries",
        "amountCents": 3000,
        "payerId": overrides.pop("payer_id", None),
        "date": "2026-08-26",
        "splitMethod": "equal",
        "splitInput": overrides.pop("split_input", None),
    }
    body.update(overrides)
    return client.post(f"/api/groups/{group_id}/expenses", json=body, headers=headers)


class TestAddExpense:
    def test_equal_split(self, client, group_with_members):
        g = group_with_members
        response = _add_expense(
            client,
            g["group"]["id"],
            g["alice_headers"],
            payer_id=g["alice_member"]["id"],
            split_input={
                "method": "equal",
                "memberIds": [g["alice_member"]["id"], g["bob_member"]["id"], g["carol_member"]["id"]],
            },
        )
        assert response.status_code == 201
        expense = response.json()
        assert expense["createdByUserId"] == g["alice_user"]["id"]
        assert sum(s["amountCents"] for s in expense["splits"]) == 3000
        assert len(expense["splits"]) == 3

    def test_exact_split_must_sum_to_total(self, client, group_with_members):
        g = group_with_members
        response = _add_expense(
            client,
            g["group"]["id"],
            g["alice_headers"],
            payer_id=g["alice_member"]["id"],
            splitMethod="exact",
            split_input={
                "method": "exact",
                "amounts": [
                    {"memberId": g["alice_member"]["id"], "amountCents": 1000},
                    {"memberId": g["bob_member"]["id"], "amountCents": 1000},
                ],
            },
        )
        assert response.status_code == 400

    def test_percent_split_must_sum_to_100(self, client, group_with_members):
        g = group_with_members
        response = _add_expense(
            client,
            g["group"]["id"],
            g["alice_headers"],
            payer_id=g["alice_member"]["id"],
            splitMethod="percent",
            split_input={
                "method": "percent",
                "percentages": [
                    {"memberId": g["alice_member"]["id"], "percent": 50},
                    {"memberId": g["bob_member"]["id"], "percent": 40},
                ],
            },
        )
        assert response.status_code == 400

    def test_shares_split(self, client, group_with_members):
        g = group_with_members
        response = _add_expense(
            client,
            g["group"]["id"],
            g["alice_headers"],
            amountCents=300,
            payer_id=g["alice_member"]["id"],
            splitMethod="shares",
            split_input={
                "method": "shares",
                "shares": [
                    {"memberId": g["alice_member"]["id"], "shares": 2},
                    {"memberId": g["bob_member"]["id"], "shares": 1},
                ],
            },
        )
        assert response.status_code == 201
        splits_by_member = {s["memberId"]: s["amountCents"] for s in response.json()["splits"]}
        assert splits_by_member[g["alice_member"]["id"]] == 200
        assert splits_by_member[g["bob_member"]["id"]] == 100

    def test_non_member_cannot_add_expense(self, client, group_with_members, signup):
        g = group_with_members
        stranger_headers, _ = signup(email="stranger@example.com")
        response = _add_expense(
            client,
            g["group"]["id"],
            stranger_headers,
            payer_id=g["alice_member"]["id"],
            split_input={"method": "equal", "memberIds": [g["alice_member"]["id"]]},
        )
        assert response.status_code == 404

    def test_amount_must_be_positive(self, client, group_with_members):
        g = group_with_members
        response = _add_expense(
            client,
            g["group"]["id"],
            g["alice_headers"],
            amountCents=0,
            payer_id=g["alice_member"]["id"],
            split_input={"method": "equal", "memberIds": [g["alice_member"]["id"]]},
        )
        assert response.status_code == 422


class TestEditAndDeleteExpense:
    def _create(self, client, g):
        response = _add_expense(
            client,
            g["group"]["id"],
            g["alice_headers"],
            payer_id=g["alice_member"]["id"],
            split_input={
                "method": "equal",
                "memberIds": [g["alice_member"]["id"], g["bob_member"]["id"]],
            },
        )
        assert response.status_code == 201
        return response.json()

    def test_creator_can_edit(self, client, group_with_members):
        g = group_with_members
        expense = self._create(client, g)

        response = client.put(
            f"/api/groups/{g['group']['id']}/expenses/{expense['id']}",
            json={
                "description": "Groceries (updated)",
                "amountCents": 4000,
                "payerId": g["alice_member"]["id"],
                "date": "2026-08-27",
                "splitMethod": "equal",
                "splitInput": {"method": "equal", "memberIds": [g["alice_member"]["id"], g["bob_member"]["id"]]},
            },
            headers=g["alice_headers"],
        )
        assert response.status_code == 200
        assert response.json()["description"] == "Groceries (updated)"
        assert response.json()["amountCents"] == 4000

    def test_non_creator_cannot_edit(self, client, group_with_members):
        g = group_with_members
        expense = self._create(client, g)

        response = client.put(
            f"/api/groups/{g['group']['id']}/expenses/{expense['id']}",
            json={
                "description": "Hijacked",
                "amountCents": 1,
                "payerId": g["bob_member"]["id"],
                "date": "2026-08-27",
                "splitMethod": "equal",
                "splitInput": {"method": "equal", "memberIds": [g["bob_member"]["id"]]},
            },
            headers=g["bob_headers"],
        )
        assert response.status_code == 403

    def test_non_creator_cannot_delete(self, client, group_with_members):
        g = group_with_members
        expense = self._create(client, g)

        response = client.delete(
            f"/api/groups/{g['group']['id']}/expenses/{expense['id']}", headers=g["bob_headers"]
        )
        assert response.status_code == 403

        still_there = client.get(f"/api/groups/{g['group']['id']}/expenses", headers=g["alice_headers"]).json()
        assert any(e["id"] == expense["id"] for e in still_there)

    def test_creator_can_delete(self, client, group_with_members):
        g = group_with_members
        expense = self._create(client, g)

        response = client.delete(
            f"/api/groups/{g['group']['id']}/expenses/{expense['id']}", headers=g["alice_headers"]
        )
        assert response.status_code == 204

        remaining = client.get(f"/api/groups/{g['group']['id']}/expenses", headers=g["alice_headers"]).json()
        assert all(e["id"] != expense["id"] for e in remaining)


class TestMemberValidation:
    """
    A member id from another group (or pure garbage) must be rejected, not
    silently stored: compute_balances only tallies ids in *this* group's
    member list, so a foreign payer would make the money vanish from the
    group's totals.
    """

    def _foreign_member_id(self, client, group_with_members):
        g = group_with_members
        other = client.post("/api/groups", json={"name": "Other"}, headers=g["bob_headers"]).json()
        return other["members"][0]["id"]

    def test_rejects_foreign_payer(self, client, group_with_members):
        g = group_with_members
        foreign = self._foreign_member_id(client, g)
        response = _add_expense(
            client,
            g["group"]["id"],
            g["alice_headers"],
            payer_id=foreign,
            split_input={"method": "equal", "memberIds": [g["alice_member"]["id"]]},
        )
        assert response.status_code == 400

    def test_rejects_unknown_payer(self, client, group_with_members):
        g = group_with_members
        response = _add_expense(
            client,
            g["group"]["id"],
            g["alice_headers"],
            payer_id="not-a-real-member",
            split_input={"method": "equal", "memberIds": [g["alice_member"]["id"]]},
        )
        assert response.status_code == 400

    def test_rejects_foreign_split_participant(self, client, group_with_members):
        g = group_with_members
        foreign = self._foreign_member_id(client, g)
        response = _add_expense(
            client,
            g["group"]["id"],
            g["alice_headers"],
            payer_id=g["alice_member"]["id"],
            split_input={"method": "equal", "memberIds": [g["alice_member"]["id"], foreign]},
        )
        assert response.status_code == 400

    def test_rejects_foreign_member_on_update(self, client, group_with_members):
        g = group_with_members
        created = _add_expense(
            client,
            g["group"]["id"],
            g["alice_headers"],
            payer_id=g["alice_member"]["id"],
            split_input={"method": "equal", "memberIds": [g["alice_member"]["id"]]},
        ).json()

        response = client.put(
            f"/api/groups/{g['group']['id']}/expenses/{created['id']}",
            json={
                "description": "Groceries",
                "amountCents": 3000,
                "payerId": "not-a-real-member",
                "date": "2026-08-26",
                "splitMethod": "equal",
                "splitInput": {"method": "equal", "memberIds": [g["alice_member"]["id"]]},
            },
            headers=g["alice_headers"],
        )
        assert response.status_code == 400

    def test_no_expense_is_stored_when_rejected(self, client, group_with_members):
        g = group_with_members
        _add_expense(
            client,
            g["group"]["id"],
            g["alice_headers"],
            payer_id="not-a-real-member",
            split_input={"method": "equal", "memberIds": [g["alice_member"]["id"]]},
        )
        listed = client.get(f"/api/groups/{g['group']['id']}/expenses", headers=g["alice_headers"]).json()
        assert listed == []

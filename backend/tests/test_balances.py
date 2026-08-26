from __future__ import annotations


class TestBalances:
    def test_full_scenario_matches_domain_layer(self, client, group_with_members):
        """
        Same scenario exercised against the frontend's mock service via
        Playwright during development: Groceries $60 equal-split among all
        three, Cabin rental $100 shares-split 2/1/1 (Alice/Bob/Carol), then
        Bob settles $10 to Alice.
        """
        client_ = client
        alice_id = group_with_members["alice_member"]["id"]
        bob_id = group_with_members["bob_member"]["id"]
        carol_id = group_with_members["carol_member"]["id"]
        group_id = group_with_members["group"]["id"]
        alice_headers = group_with_members["alice_headers"]

        client_.post(
            f"/api/groups/{group_id}/expenses",
            json={
                "description": "Groceries",
                "amountCents": 6000,
                "payerId": alice_id,
                "date": "2026-08-26",
                "splitMethod": "equal",
                "splitInput": {"method": "equal", "memberIds": [alice_id, bob_id, carol_id]},
            },
            headers=alice_headers,
        )

        client_.post(
            f"/api/groups/{group_id}/expenses",
            json={
                "description": "Cabin rental",
                "amountCents": 10000,
                "payerId": alice_id,
                "date": "2026-08-26",
                "splitMethod": "shares",
                "splitInput": {
                    "method": "shares",
                    "shares": [
                        {"memberId": alice_id, "shares": 2},
                        {"memberId": bob_id, "shares": 1},
                        {"memberId": carol_id, "shares": 1},
                    ],
                },
            },
            headers=alice_headers,
        )

        balances = client_.get(f"/api/groups/{group_id}/balances", headers=alice_headers).json()
        by_id = {b["memberId"]: b["netCents"] for b in balances["balances"]}
        # Alice paid 6000+10000=16000, owes 2000(groceries share)+5000(cabin share)=7000 -> net +9000
        # Bob owes 2000+2500=4500 -> net -4500
        # Carol owes 2000+2500=4500 -> net -4500
        assert by_id[alice_id] == 9000
        assert by_id[bob_id] == -4500
        assert by_id[carol_id] == -4500
        assert sum(by_id.values()) == 0

        client_.post(
            f"/api/groups/{group_id}/settlements",
            json={"fromMemberId": bob_id, "toMemberId": alice_id, "amountCents": 1000, "date": "2026-08-27"},
            headers=alice_headers,
        )

        balances_after = client_.get(f"/api/groups/{group_id}/balances", headers=alice_headers).json()
        by_id_after = {b["memberId"]: b["netCents"] for b in balances_after["balances"]}
        assert by_id_after[alice_id] == 8000
        assert by_id_after[bob_id] == -3500
        assert by_id_after[carol_id] == -4500

    def test_zero_balance_excluded_from_settle_up(self, client, group_with_members):
        g = group_with_members
        response = client.get(f"/api/groups/{g['group']['id']}/balances", headers=g["alice_headers"])
        assert response.status_code == 200
        body = response.json()
        assert body["balances"] == [
            {"memberId": g["alice_member"]["id"], "netCents": 0},
            {"memberId": g["bob_member"]["id"], "netCents": 0},
            {"memberId": g["carol_member"]["id"], "netCents": 0},
        ]
        assert body["settleUp"] == []

    def test_balances_require_membership(self, client, group_with_members, signup):
        g = group_with_members
        stranger_headers, _ = signup(email="stranger@example.com")
        response = client.get(f"/api/groups/{g['group']['id']}/balances", headers=stranger_headers)
        assert response.status_code == 404

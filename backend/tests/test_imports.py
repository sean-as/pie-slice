from __future__ import annotations


def _upload(client, group_id, headers, *lines):
    content = "\n".join(("date,description,amount",) + lines).encode("utf-8")
    return client.post(
        f"/api/groups/{group_id}/imports",
        files={"file": ("statement.csv", content, "text/csv")},
        headers=headers,
    )


def _confirm(client, group_id, headers, import_id, row_ids):
    return client.post(
        f"/api/groups/{group_id}/imports/{import_id}/confirm",
        json={"rowIds": row_ids},
        headers=headers,
    )


def _expenses(client, group_id, headers):
    return client.get(f"/api/groups/{group_id}/expenses", headers=headers).json()


class TestUpload:
    def test_upload_creates_nothing_on_its_own(self, client, group_with_members):
        """The core invariant: nothing exists until the user reviews and submits."""
        g = group_with_members
        response = _upload(
            client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,79.99", "2026-08-27,Shell,40.00"
        )
        assert response.status_code == 200
        preview = response.json()
        assert len(preview["rows"]) == 2
        assert _expenses(client, g["group"]["id"], g["alice_headers"]) == []

    def test_new_merchants_start_unselected(self, client, group_with_members):
        g = group_with_members
        preview = _upload(client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,79.99").json()
        assert preview["rows"][0]["preselected"] is False

    def test_reports_unparseable_rows_without_failing(self, client, group_with_members):
        g = group_with_members
        preview = _upload(
            client, g["group"]["id"], g["alice_headers"], "nonsense,Comcast,79.99", "2026-08-27,Shell,40.00"
        ).json()
        assert [r["description"] for r in preview["rows"]] == ["Shell"]
        assert len(preview["skipped"]) == 1

    def test_negative_rows_never_reach_review(self, client, group_with_members):
        g = group_with_members
        preview = _upload(
            client, g["group"]["id"], g["alice_headers"], "2026-08-26,Payment,-100.00", "2026-08-27,Shell,40.00"
        ).json()
        assert [r["description"] for r in preview["rows"]] == ["Shell"]
        assert preview["skipped"] == []

    def test_missing_columns_are_rejected(self, client, group_with_members):
        g = group_with_members
        response = client.post(
            f"/api/groups/{g['group']['id']}/imports",
            files={"file": ("statement.csv", b"foo,bar\n1,2", "text/csv")},
            headers=g["alice_headers"],
        )
        assert response.status_code == 400

    def test_oversized_upload_is_rejected(self, client, group_with_members):
        g = group_with_members
        content = b"date,description,amount\n" + b"x" * 1_000_001
        response = client.post(
            f"/api/groups/{g['group']['id']}/imports",
            files={"file": ("statement.csv", content, "text/csv")},
            headers=g["alice_headers"],
        )
        assert response.status_code == 413

    def test_non_member_cannot_upload(self, client, group_with_members, signup):
        g = group_with_members
        mallory_headers, _ = signup(email="mallory@example.com", display_name="Mallory")
        response = _upload(client, g["group"]["id"], mallory_headers, "2026-08-26,Comcast,79.99")
        assert response.status_code == 404

    def test_requires_authentication(self, client, group_with_members):
        g = group_with_members
        response = _upload(client, g["group"]["id"], {}, "2026-08-26,Comcast,79.99")
        assert response.status_code == 401


class TestConfirm:
    def test_imports_only_the_selected_rows(self, client, group_with_members):
        g = group_with_members
        preview = _upload(
            client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,79.99", "2026-08-27,Shell,40.00"
        ).json()
        chosen = next(r for r in preview["rows"] if r["description"] == "Comcast")

        response = _confirm(client, g["group"]["id"], g["alice_headers"], preview["importId"], [chosen["id"]])
        assert response.status_code == 200
        assert [e["description"] for e in response.json()["imported"]] == ["Comcast"]
        assert [e["description"] for e in _expenses(client, g["group"]["id"], g["alice_headers"])] == ["Comcast"]

    def test_selecting_nothing_imports_nothing(self, client, group_with_members):
        g = group_with_members
        preview = _upload(client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,79.99").json()

        response = _confirm(client, g["group"]["id"], g["alice_headers"], preview["importId"], [])
        assert response.status_code == 200
        assert response.json()["imported"] == []
        assert _expenses(client, g["group"]["id"], g["alice_headers"]) == []

    def test_imported_expense_looks_like_any_other(self, client, group_with_members):
        g = group_with_members
        preview = _upload(client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,79.99").json()
        expense = _confirm(
            client, g["group"]["id"], g["alice_headers"], preview["importId"], [preview["rows"][0]["id"]]
        ).json()["imported"][0]

        assert expense["amountCents"] == 7999
        assert expense["payerId"] == g["alice_member"]["id"]
        assert expense["date"] == "2026-08-26"
        assert expense["splitMethod"] == "equal"
        assert expense["createdByUserId"] == g["alice_user"]["id"]
        # Equal split across all three current members, summing exactly.
        assert len(expense["splits"]) == 3
        assert sum(s["amountCents"] for s in expense["splits"]) == 7999

    def test_imported_expense_is_creator_only_editable(self, client, group_with_members):
        g = group_with_members
        preview = _upload(client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,79.99").json()
        expense = _confirm(
            client, g["group"]["id"], g["alice_headers"], preview["importId"], [preview["rows"][0]["id"]]
        ).json()["imported"][0]

        response = client.delete(
            f"/api/groups/{g['group']['id']}/expenses/{expense['id']}", headers=g["bob_headers"]
        )
        assert response.status_code == 403

    def test_imported_expense_counts_in_balances(self, client, group_with_members):
        g = group_with_members
        preview = _upload(client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,30.00").json()
        _confirm(client, g["group"]["id"], g["alice_headers"], preview["importId"], [preview["rows"][0]["id"]])

        balances = client.get(f"/api/groups/{g['group']['id']}/balances", headers=g["alice_headers"]).json()
        by_member = {b["memberId"]: b["netCents"] for b in balances["balances"]}
        assert by_member[g["alice_member"]["id"]] == 2000  # paid 3000, owes 1000
        assert by_member[g["bob_member"]["id"]] == -1000

    def test_rejects_a_row_id_from_another_users_import(self, client, group_with_members):
        g = group_with_members
        alice_preview = _upload(
            client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,79.99"
        ).json()
        bob_preview = _upload(client, g["group"]["id"], g["bob_headers"], "2026-08-26,Shell,40.00").json()

        # Bob can't confirm Alice's import at all...
        assert (
            _confirm(
                client, g["group"]["id"], g["bob_headers"], alice_preview["importId"], [alice_preview["rows"][0]["id"]]
            ).status_code
            == 404
        )
        # ...nor smuggle her row id into his own.
        assert (
            _confirm(
                client, g["group"]["id"], g["bob_headers"], bob_preview["importId"], [alice_preview["rows"][0]["id"]]
            ).status_code
            == 400
        )

    def test_confirming_twice_does_not_double_import(self, client, group_with_members):
        g = group_with_members
        preview = _upload(client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,79.99").json()
        row_id = preview["rows"][0]["id"]

        assert _confirm(client, g["group"]["id"], g["alice_headers"], preview["importId"], [row_id]).status_code == 200
        assert _confirm(client, g["group"]["id"], g["alice_headers"], preview["importId"], [row_id]).status_code == 404
        assert len(_expenses(client, g["group"]["id"], g["alice_headers"])) == 1

    def test_repeated_row_id_creates_one_expense(self, client, group_with_members):
        g = group_with_members
        preview = _upload(client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,79.99").json()
        row_id = preview["rows"][0]["id"]

        result = _confirm(client, g["group"]["id"], g["alice_headers"], preview["importId"], [row_id, row_id]).json()
        assert len(result["imported"]) == 1


class TestRememberedMerchants:
    def test_importing_preselects_that_merchant_next_time(self, client, group_with_members):
        g = group_with_members
        first = _upload(client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,79.99").json()
        _confirm(client, g["group"]["id"], g["alice_headers"], first["importId"], [first["rows"][0]["id"]])

        second = _upload(
            client, g["group"]["id"], g["alice_headers"], "2026-09-26,Comcast,79.99", "2026-09-27,Shell,40.00"
        ).json()
        by_description = {r["description"]: r for r in second["rows"]}
        assert by_description["Comcast"]["preselected"] is True
        assert by_description["Shell"]["preselected"] is False

    def test_matching_ignores_case_and_spacing(self, client, group_with_members):
        g = group_with_members
        first = _upload(client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast Cable,79.99").json()
        _confirm(client, g["group"]["id"], g["alice_headers"], first["importId"], [first["rows"][0]["id"]])

        second = _upload(client, g["group"]["id"], g["alice_headers"], "2026-09-26,COMCAST  CABLE,79.99").json()
        assert second["rows"][0]["preselected"] is True

    def test_deselecting_does_not_forget_a_merchant(self, client, group_with_members):
        g = group_with_members
        first = _upload(client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,79.99").json()
        _confirm(client, g["group"]["id"], g["alice_headers"], first["importId"], [first["rows"][0]["id"]])

        # Second month: shown pre-selected, but Alice unticks it.
        second = _upload(client, g["group"]["id"], g["alice_headers"], "2026-09-26,Comcast,79.99").json()
        _confirm(client, g["group"]["id"], g["alice_headers"], second["importId"], [])

        # Third month: still remembered — skipping is per-upload, not a forget.
        third = _upload(client, g["group"]["id"], g["alice_headers"], "2026-10-26,Comcast,79.99").json()
        assert third["rows"][0]["preselected"] is True

    def test_memory_is_per_user(self, client, group_with_members):
        g = group_with_members
        first = _upload(client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,79.99").json()
        _confirm(client, g["group"]["id"], g["alice_headers"], first["importId"], [first["rows"][0]["id"]])

        # Bob uploads the same merchant to the same group — Alice's history
        # must not tick anything for him (user story 18).
        bob = _upload(client, g["group"]["id"], g["bob_headers"], "2026-08-26,Comcast,79.99").json()
        assert bob["rows"][0]["preselected"] is False

    def test_memory_is_per_group(self, client, group_with_members):
        g = group_with_members
        first = _upload(client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,79.99").json()
        _confirm(client, g["group"]["id"], g["alice_headers"], first["importId"], [first["rows"][0]["id"]])

        other = client.post("/api/groups", json={"name": "Apartment"}, headers=g["alice_headers"]).json()
        elsewhere = _upload(client, other["id"], g["alice_headers"], "2026-08-26,Comcast,79.99").json()
        assert elsewhere["rows"][0]["preselected"] is False


class TestDeduplication:
    def test_reupload_hides_already_imported_rows(self, client, group_with_members):
        g = group_with_members
        first = _upload(
            client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,79.99", "2026-08-27,Shell,40.00"
        ).json()
        comcast = next(r for r in first["rows"] if r["description"] == "Comcast")
        _confirm(client, g["group"]["id"], g["alice_headers"], first["importId"], [comcast["id"]])

        # Overlapping re-upload: Comcast is gone, Shell (never imported) stays.
        second = _upload(
            client,
            g["group"]["id"],
            g["alice_headers"],
            "2026-08-26,Comcast,79.99",
            "2026-08-27,Shell,40.00",
            "2026-09-01,Trader Joes,25.00",
        ).json()
        assert [r["description"] for r in second["rows"]] == ["Shell", "Trader Joes"]
        assert second["duplicateCount"] == 1

    def test_identical_rows_within_one_file_collapse(self, client, group_with_members):
        g = group_with_members
        preview = _upload(
            client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,79.99", "2026-08-26,Comcast,79.99"
        ).json()
        assert len(preview["rows"]) == 1
        assert preview["duplicateCount"] == 1

    def test_dedupe_is_per_uploader(self, client, group_with_members):
        g = group_with_members
        first = _upload(client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,79.99").json()
        _confirm(client, g["group"]["id"], g["alice_headers"], first["importId"], [first["rows"][0]["id"]])

        # Bob genuinely paid his own Comcast bill — not Alice's duplicate.
        bob = _upload(client, g["group"]["id"], g["bob_headers"], "2026-08-26,Comcast,79.99").json()
        assert len(bob["rows"]) == 1
        assert bob["duplicateCount"] == 0

    def test_same_merchant_different_amount_is_not_a_duplicate(self, client, group_with_members):
        g = group_with_members
        first = _upload(client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,79.99").json()
        _confirm(client, g["group"]["id"], g["alice_headers"], first["importId"], [first["rows"][0]["id"]])

        second = _upload(client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,89.99").json()
        assert len(second["rows"]) == 1


CHASE_STYLE = (
    "Transaction Date,Post Date,Merchant,Debit,Category\n"
    "09/25/2026,09/26/2026,Comcast,-79.99,Utilities\n"
    "09/26/2026,09/27/2026,Payment Received,500.00,Payment\n"
).encode("utf-8")


def _inspect(client, group_id, headers, content=CHASE_STYLE):
    return client.post(
        f"/api/groups/{group_id}/imports/inspect",
        files={"file": ("statement.csv", content, "text/csv")},
        headers=headers,
    )


def _upload_mapped(client, group_id, headers, content=CHASE_STYLE, **mapping):
    return client.post(
        f"/api/groups/{group_id}/imports",
        files={"file": ("statement.csv", content, "text/csv")},
        data=mapping,
        headers=headers,
    )


CHASE_MAPPING = {
    "dateColumn": "Transaction Date",
    "descriptionColumn": "Merchant",
    "amountColumn": "Debit",
    "dateFormat": "mdy",
    "amountSign": "negative_is_charge",
}


class TestInspect:
    def test_returns_columns_and_samples(self, client, group_with_members):
        g = group_with_members
        shape = _inspect(client, g["group"]["id"], g["alice_headers"]).json()
        assert shape["columns"] == ["Transaction Date", "Post Date", "Merchant", "Debit", "Category"]
        assert shape["sampleRows"][0]["Merchant"] == "Comcast"

    def test_reports_columns_it_cannot_guess(self, client, group_with_members):
        g = group_with_members
        shape = _inspect(client, g["group"]["id"], g["alice_headers"]).json()
        assert sorted(shape["unresolved"]) == ["amount", "date", "description"]

    def test_recognizes_a_conventional_file(self, client, group_with_members):
        g = group_with_members
        shape = _inspect(
            client,
            g["group"]["id"],
            g["alice_headers"],
            b"date,description,amount\n2026-08-26,Comcast,79.99\n",
        ).json()
        assert shape["unresolved"] == []
        assert shape["suggested"]["dateColumn"] == "date"
        assert shape["dateFormatAmbiguous"] is False

    def test_creates_nothing(self, client, group_with_members):
        g = group_with_members
        _inspect(client, g["group"]["id"], g["alice_headers"])
        assert _expenses(client, g["group"]["id"], g["alice_headers"]) == []

    def test_non_member_cannot_inspect(self, client, group_with_members, signup):
        g = group_with_members
        mallory_headers, _ = signup(email="mallory@example.com", display_name="Mallory")
        assert _inspect(client, g["group"]["id"], mallory_headers).status_code == 404


class TestMappedUpload:
    def test_reads_a_bank_that_agrees_on_nothing(self, client, group_with_members):
        """Foreign column names, negative charges, and US dates at once."""
        g = group_with_members
        preview = _upload_mapped(client, g["group"]["id"], g["alice_headers"], **CHASE_MAPPING).json()

        assert [r["description"] for r in preview["rows"]] == ["Comcast"]
        assert preview["rows"][0]["amountCents"] == 7999
        assert preview["rows"][0]["date"] == "2026-09-25"

    def test_wrong_sign_convention_finds_the_other_side_of_the_ledger(self, client, group_with_members):
        g = group_with_members
        preview = _upload_mapped(
            client,
            g["group"]["id"],
            g["alice_headers"],
            **{**CHASE_MAPPING, "amountSign": "positive_is_charge"},
        ).json()
        assert [r["description"] for r in preview["rows"]] == ["Payment Received"]

    def test_naming_a_missing_column_is_rejected(self, client, group_with_members):
        g = group_with_members
        response = _upload_mapped(
            client, g["group"]["id"], g["alice_headers"], **{**CHASE_MAPPING, "amountColumn": "Nope"}
        )
        assert response.status_code == 400

    def test_partial_mapping_is_rejected(self, client, group_with_members):
        g = group_with_members
        response = _upload_mapped(
            client, g["group"]["id"], g["alice_headers"], dateColumn="Transaction Date"
        )
        assert response.status_code == 400

    def test_no_mapping_still_works_for_conventional_files(self, client, group_with_members):
        g = group_with_members
        preview = _upload(client, g["group"]["id"], g["alice_headers"], "2026-08-26,Comcast,79.99").json()
        assert len(preview["rows"]) == 1

    def test_unknown_date_format_is_rejected(self, client, group_with_members):
        g = group_with_members
        response = _upload_mapped(
            client, g["group"]["id"], g["alice_headers"], **{**CHASE_MAPPING, "dateFormat": "martian"}
        )
        assert response.status_code == 422

    def test_mapped_import_produces_an_ordinary_expense(self, client, group_with_members):
        g = group_with_members
        preview = _upload_mapped(client, g["group"]["id"], g["alice_headers"], **CHASE_MAPPING).json()
        expense = _confirm(
            client, g["group"]["id"], g["alice_headers"], preview["importId"], [preview["rows"][0]["id"]]
        ).json()["imported"][0]

        assert expense["amountCents"] == 7999
        assert expense["date"] == "2026-09-25"
        assert expense["payerId"] == g["alice_member"]["id"]
        assert expense["splitMethod"] == "equal"


class TestRememberedMapping:
    def test_next_inspect_is_prefilled_from_the_last_upload(self, client, group_with_members):
        g = group_with_members
        _upload_mapped(client, g["group"]["id"], g["alice_headers"], **CHASE_MAPPING)

        shape = _inspect(client, g["group"]["id"], g["alice_headers"]).json()
        assert shape["unresolved"] == []
        assert shape["suggested"]["descriptionColumn"] == "Merchant"
        assert shape["suggested"]["amountSign"] == "negative_is_charge"
        assert shape["suggested"]["dateFormat"] == "mdy"

    def test_a_rejected_mapping_is_not_remembered(self, client, group_with_members):
        g = group_with_members
        _upload_mapped(
            client, g["group"]["id"], g["alice_headers"], **{**CHASE_MAPPING, "amountColumn": "Nope"}
        )
        shape = _inspect(client, g["group"]["id"], g["alice_headers"]).json()
        assert sorted(shape["unresolved"]) == ["amount", "date", "description"]

    def test_mapping_is_per_user(self, client, group_with_members):
        g = group_with_members
        _upload_mapped(client, g["group"]["id"], g["alice_headers"], **CHASE_MAPPING)

        # Bob's bank is his own business — Alice's mapping must not leak.
        shape = _inspect(client, g["group"]["id"], g["bob_headers"]).json()
        assert sorted(shape["unresolved"]) == ["amount", "date", "description"]

    def test_mapping_is_per_group(self, client, group_with_members):
        g = group_with_members
        _upload_mapped(client, g["group"]["id"], g["alice_headers"], **CHASE_MAPPING)

        other = client.post("/api/groups", json={"name": "Apartment"}, headers=g["alice_headers"]).json()
        shape = _inspect(client, other["id"], g["alice_headers"]).json()
        assert sorted(shape["unresolved"]) == ["amount", "date", "description"]

    def test_a_later_mapping_replaces_the_earlier_one(self, client, group_with_members):
        g = group_with_members
        _upload_mapped(client, g["group"]["id"], g["alice_headers"], **CHASE_MAPPING)
        _upload_mapped(
            client,
            g["group"]["id"],
            g["alice_headers"],
            **{**CHASE_MAPPING, "descriptionColumn": "Category"},
        )
        shape = _inspect(client, g["group"]["id"], g["alice_headers"]).json()
        assert shape["suggested"]["descriptionColumn"] == "Category"


class TestCategory:
    """Optional throughout: mapped when the file has one, absent when it doesn't."""

    WITH_CATEGORY = b"date,description,amount,category\n2026-08-26,Comcast,79.99,Utilities\n"

    def test_a_category_column_is_suggested_when_present(self, client, group_with_members):
        g = group_with_members
        shape = _inspect(client, g["group"]["id"], g["alice_headers"], self.WITH_CATEGORY).json()
        assert shape["suggested"]["categoryColumn"] == "category"
        # Present but optional — never blocks the user.
        assert shape["unresolved"] == []

    def test_no_category_column_is_fine(self, client, group_with_members):
        g = group_with_members
        shape = _inspect(
            client, g["group"]["id"], g["alice_headers"], b"date,description,amount\n2026-08-26,X,1.00\n"
        ).json()
        assert shape["suggested"]["categoryColumn"] is None
        assert shape["unresolved"] == []

    def test_category_reaches_the_review_row_and_the_expense(self, client, group_with_members):
        g = group_with_members
        preview = _upload_mapped(
            client,
            g["group"]["id"],
            g["alice_headers"],
            self.WITH_CATEGORY,
            dateColumn="date",
            descriptionColumn="description",
            amountColumn="amount",
            categoryColumn="category",
        ).json()
        assert preview["rows"][0]["category"] == "Utilities"

        expense = _confirm(
            client, g["group"]["id"], g["alice_headers"], preview["importId"], [preview["rows"][0]["id"]]
        ).json()["imported"][0]
        assert expense["category"] == "Utilities"

    def test_importing_without_mapping_a_category_leaves_it_empty(self, client, group_with_members):
        g = group_with_members
        preview = _upload_mapped(
            client,
            g["group"]["id"],
            g["alice_headers"],
            self.WITH_CATEGORY,
            dateColumn="date",
            descriptionColumn="description",
            amountColumn="amount",
        ).json()
        assert preview["rows"][0]["category"] is None

    def test_a_blank_category_cell_is_no_category(self, client, group_with_members):
        g = group_with_members
        preview = _upload_mapped(
            client,
            g["group"]["id"],
            g["alice_headers"],
            b"date,description,amount,category\n2026-08-26,Comcast,79.99,\n",
            dateColumn="date",
            descriptionColumn="description",
            amountColumn="amount",
            categoryColumn="category",
        ).json()
        assert preview["rows"][0]["category"] is None

    def test_naming_a_missing_category_column_is_rejected(self, client, group_with_members):
        g = group_with_members
        response = _upload_mapped(
            client,
            g["group"]["id"],
            g["alice_headers"],
            self.WITH_CATEGORY,
            dateColumn="date",
            descriptionColumn="description",
            amountColumn="amount",
            categoryColumn="Nope",
        )
        assert response.status_code == 400

    def test_category_mapping_is_remembered(self, client, group_with_members):
        g = group_with_members
        _upload_mapped(
            client,
            g["group"]["id"],
            g["alice_headers"],
            b"date,description,amount,Bucket\n2026-08-26,Comcast,79.99,Utilities\n",
            dateColumn="date",
            descriptionColumn="description",
            amountColumn="amount",
            categoryColumn="Bucket",
        )
        shape = _inspect(
            client,
            g["group"]["id"],
            g["alice_headers"],
            b"date,description,amount,Bucket\n2026-09-26,Comcast,79.99,Utilities\n",
        ).json()
        assert shape["suggested"]["categoryColumn"] == "Bucket"

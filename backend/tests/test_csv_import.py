from __future__ import annotations

from datetime import date

import pytest

from app.csv_import import (
    MAX_ROWS,
    ColumnMapping,
    CsvFormatError,
    defuse_formula,
    detect_mapping,
    fingerprint,
    normalize_merchant,
    parse_csv,
)


def _csv(*lines: str) -> bytes:
    return "\n".join(lines).encode("utf-8")


class TestParseCsv:
    def test_parses_a_basic_file(self):
        result = parse_csv(_csv("date,description,amount", "2026-08-26,Comcast,79.99"))
        assert result.skipped == []
        assert len(result.rows) == 1
        row = result.rows[0]
        assert row.date == date(2026, 8, 26)
        assert row.description == "Comcast"
        assert row.amount_cents == 7999

    def test_header_matching_is_case_insensitive_and_order_free(self):
        result = parse_csv(_csv("Amount, DESCRIPTION ,Date", "42.50,Shell,2026-08-01"))
        assert [(r.description, r.amount_cents, r.date) for r in result.rows] == [
            ("Shell", 4250, date(2026, 8, 1))
        ]

    def test_extra_columns_are_ignored(self):
        result = parse_csv(_csv("date,description,amount,category", "2026-08-26,Comcast,79.99,Utilities"))
        assert len(result.rows) == 1

    def test_missing_required_column_is_fatal(self):
        with pytest.raises(CsvFormatError):
            parse_csv(_csv("date,description", "2026-08-26,Comcast"))

    def test_empty_file_is_fatal(self):
        with pytest.raises(CsvFormatError):
            parse_csv(b"")

    def test_zero_and_negative_rows_are_dropped_silently(self):
        result = parse_csv(
            _csv(
                "date,description,amount",
                "2026-08-26,Comcast,79.99",
                "2026-08-27,Payment thank you,-250.00",
                "2026-08-28,Adjustment,0.00",
            )
        )
        assert [r.description for r in result.rows] == ["Comcast"]
        # Dropped, *not* reported as skipped — the user never sees them.
        assert result.skipped == []

    def test_unparseable_rows_are_reported_not_fatal(self):
        result = parse_csv(
            _csv(
                "date,description,amount",
                "not-a-date,Comcast,79.99",
                "2026-08-27,Shell,abc",
                "2026-08-28,Trader Joes,25.00",
            )
        )
        assert [r.description for r in result.rows] == ["Trader Joes"]
        assert [s.line for s in result.skipped] == [2, 3]

    def test_short_row_is_skipped(self):
        result = parse_csv(_csv("date,description,amount", "2026-08-26,Comcast"))
        assert result.rows == []
        assert len(result.skipped) == 1

    def test_blank_lines_are_ignored(self):
        result = parse_csv(_csv("date,description,amount", "", "2026-08-26,Comcast,79.99", ""))
        assert len(result.rows) == 1
        assert result.skipped == []

    def test_amount_is_exact_cents_not_float(self):
        result = parse_csv(
            _csv("date,description,amount", "2026-08-26,A,0.10", "2026-08-26,B,0.20", "2026-08-26,C,1234.56")
        )
        assert [r.amount_cents for r in result.rows] == [10, 20, 123456]

    def test_currency_symbols_and_thousands_separators(self):
        result = parse_csv(_csv("date,description,amount", "2026-08-26,Rent,\"$1,200.00\""))
        assert result.rows[0].amount_cents == 120000

    def test_sub_cent_precision_is_skipped(self):
        result = parse_csv(_csv("date,description,amount", "2026-08-26,Odd,1.005"))
        assert result.rows == []
        assert len(result.skipped) == 1

    def test_too_many_rows_is_fatal(self):
        lines = ["date,description,amount"] + [f"2026-08-26,Store,1.00"] * (MAX_ROWS + 1)
        with pytest.raises(CsvFormatError):
            parse_csv(_csv(*lines))

    def test_oversized_file_is_fatal(self):
        with pytest.raises(CsvFormatError):
            parse_csv(b"date,description,amount\n" + b"x" * 1_000_001)

    def test_utf8_bom_is_tolerated(self):
        result = parse_csv("﻿date,description,amount\n2026-08-26,Comcast,79.99".encode("utf-8"))
        assert len(result.rows) == 1


class TestFormulaDefusal:
    @pytest.mark.parametrize("raw", ["=1+1", "+SUM(A1)", "-2+3", "@import"])
    def test_dangerous_prefixes_are_defused(self, raw):
        assert defuse_formula(raw).startswith("'")

    def test_ordinary_text_is_untouched(self):
        assert defuse_formula("  Comcast  ") == "Comcast"

    def test_parse_defuses_descriptions(self):
        result = parse_csv(_csv("date,description,amount", "2026-08-26,=cmd|'/c calc',10.00"))
        assert result.rows[0].description.startswith("'=")


class TestNormalizeMerchant:
    def test_case_and_whitespace_are_ignored(self):
        assert normalize_merchant("  COMCAST   Cable ") == normalize_merchant("comcast cable")

    def test_different_merchants_stay_different(self):
        # The spec rules out fuzzy matching — these must not collapse.
        assert normalize_merchant("AMAZON MKTPLACE") != normalize_merchant("AMAZON.COM*A1B2C")


class TestFingerprint:
    def test_is_stable_across_casing_and_spacing(self):
        a = fingerprint("g", "u", date(2026, 8, 26), "COMCAST  CABLE", 7999)
        b = fingerprint("g", "u", date(2026, 8, 26), "comcast cable", 7999)
        assert a == b

    def test_differs_by_group_user_date_and_amount(self):
        base = fingerprint("g", "u", date(2026, 8, 26), "Comcast", 7999)
        assert base != fingerprint("g2", "u", date(2026, 8, 26), "Comcast", 7999)
        assert base != fingerprint("g", "u2", date(2026, 8, 26), "Comcast", 7999)
        assert base != fingerprint("g", "u", date(2026, 8, 27), "Comcast", 7999)
        assert base != fingerprint("g", "u", date(2026, 8, 26), "Comcast", 8000)


class TestColumnMapping:
    """Banks disagree on column names, so which column is which is a parameter."""

    CHASE = _csv(
        "Transaction Date,Post Date,Merchant,Debit,Category",
        "2026-08-26,2026-08-27,Comcast,79.99,Utilities",
    )

    def test_maps_arbitrary_column_names(self):
        result = parse_csv(
            self.CHASE,
            ColumnMapping(
                date_column="Transaction Date", description_column="Merchant", amount_column="Debit"
            ),
        )
        assert [(r.description, r.amount_cents) for r in result.rows] == [("Comcast", 7999)]

    def test_picks_the_mapped_date_column_not_another_date_looking_one(self):
        result = parse_csv(
            self.CHASE,
            ColumnMapping(
                date_column="Post Date", description_column="Merchant", amount_column="Debit"
            ),
        )
        assert result.rows[0].date == date(2026, 8, 27)

    def test_column_names_match_case_insensitively(self):
        result = parse_csv(
            self.CHASE,
            ColumnMapping(
                date_column="transaction date", description_column="MERCHANT", amount_column="debit"
            ),
        )
        assert len(result.rows) == 1

    def test_naming_a_column_that_does_not_exist_is_fatal(self):
        with pytest.raises(CsvFormatError, match="Nope"):
            parse_csv(
                self.CHASE,
                ColumnMapping(date_column="Nope", description_column="Merchant", amount_column="Debit"),
            )

    def test_no_mapping_falls_back_to_conventional_names(self):
        result = parse_csv(_csv("date,description,amount", "2026-08-26,Comcast,79.99"))
        assert len(result.rows) == 1


class TestAmountSign:
    """Some banks write purchases as negative; without this the whole file
    would be silently dropped as 'not a charge'."""

    NEGATIVE_BANK = _csv("date,description,amount", "2026-08-26,Comcast,-79.99", "2026-08-27,Payment,500.00")

    def _mapping(self, **kwargs):
        return ColumnMapping(
            date_column="date", description_column="description", amount_column="amount", **kwargs
        )

    def test_negative_is_charge_flips_which_rows_count(self):
        result = parse_csv(self.NEGATIVE_BANK, self._mapping(amount_sign="negative_is_charge"))
        assert [(r.description, r.amount_cents) for r in result.rows] == [("Comcast", 7999)]

    def test_wrong_sign_convention_yields_the_other_side_of_the_ledger(self):
        result = parse_csv(self.NEGATIVE_BANK, self._mapping(amount_sign="positive_is_charge"))
        assert [r.description for r in result.rows] == ["Payment"]

    def test_stored_amount_is_always_positive(self):
        result = parse_csv(self.NEGATIVE_BANK, self._mapping(amount_sign="negative_is_charge"))
        assert all(r.amount_cents > 0 for r in result.rows)


class TestDateFormats:
    def _mapping(self, date_format):
        return ColumnMapping(
            date_column="date",
            description_column="description",
            amount_column="amount",
            date_format=date_format,
        )

    def test_us_format(self):
        result = parse_csv(_csv("date,description,amount", "09/01/2026,Comcast,79.99"), self._mapping("mdy"))
        assert result.rows[0].date == date(2026, 9, 1)

    def test_eu_format_reads_the_same_string_differently(self):
        result = parse_csv(_csv("date,description,amount", "09/01/2026,Comcast,79.99"), self._mapping("dmy"))
        assert result.rows[0].date == date(2026, 1, 9)

    def test_wrong_format_skips_the_row_rather_than_guessing(self):
        result = parse_csv(_csv("date,description,amount", "09/01/2026,Comcast,79.99"), self._mapping("iso"))
        assert result.rows == []
        assert "expected YYYY-MM-DD" in result.skipped[0].reason

    def test_impossible_date_under_the_chosen_format_is_skipped(self):
        # 25 can't be a month, so MM/DD/YYYY genuinely fails here.
        result = parse_csv(_csv("date,description,amount", "25/01/2026,Comcast,79.99"), self._mapping("mdy"))
        assert result.rows == []
        assert len(result.skipped) == 1


class TestDetectMapping:
    def test_recognizes_conventional_headers(self):
        shape = detect_mapping(_csv("date,description,amount", "2026-08-26,Comcast,79.99"))
        assert shape.unresolved == []
        assert shape.suggested.date_column == "date"
        assert shape.suggested.date_format == "iso"
        assert shape.date_format_ambiguous is False

    def test_reports_columns_it_cannot_guess(self):
        shape = detect_mapping(_csv("Posted,Merchant,Debit", "2026-08-26,Comcast,79.99"))
        assert sorted(shape.unresolved) == ["amount", "date", "description"]
        assert shape.columns == ["Posted", "Merchant", "Debit"]

    def test_returns_sample_rows_keyed_by_column(self):
        shape = detect_mapping(
            _csv("date,description,amount", "2026-08-26,Comcast,79.99", "2026-08-27,Shell,40.00")
        )
        assert shape.sample_rows[0] == {
            "date": "2026-08-26",
            "description": "Comcast",
            "amount": "79.99",
        }

    def test_infers_us_dates_when_a_day_exceeds_twelve(self):
        shape = detect_mapping(_csv("date,description,amount", "09/25/2026,Comcast,79.99"))
        assert shape.suggested.date_format == "mdy"
        assert shape.date_format_ambiguous is False

    def test_infers_eu_dates_when_the_first_part_exceeds_twelve(self):
        shape = detect_mapping(_csv("date,description,amount", "25/09/2026,Comcast,79.99"))
        assert shape.suggested.date_format == "dmy"
        assert shape.date_format_ambiguous is False

    def test_flags_genuinely_ambiguous_slash_dates(self):
        # Every part <= 12: MM/DD and DD/MM are indistinguishable, so the
        # user must decide rather than have us pick silently.
        shape = detect_mapping(_csv("date,description,amount", "09/01/2026,Comcast,79.99"))
        assert shape.date_format_ambiguous is True

    def test_previous_mapping_wins_when_its_columns_still_exist(self):
        previous = ColumnMapping(
            date_column="Posted",
            description_column="Merchant",
            amount_column="Debit",
            amount_sign="negative_is_charge",
        )
        shape = detect_mapping(_csv("Posted,Merchant,Debit", "2026-08-26,Comcast,-79.99"), previous)
        assert shape.unresolved == []
        assert shape.suggested.description_column == "Merchant"
        assert shape.suggested.amount_sign == "negative_is_charge"

    def test_previous_mapping_is_ignored_when_the_columns_are_gone(self):
        previous = ColumnMapping(
            date_column="Posted", description_column="Merchant", amount_column="Debit"
        )
        shape = detect_mapping(_csv("date,description,amount", "2026-08-26,Comcast,79.99"), previous)
        assert shape.unresolved == []
        assert shape.suggested.date_column == "date"

    def test_header_only_file_is_shapeable(self):
        shape = detect_mapping(_csv("date,description,amount"))
        assert shape.sample_rows == []
        assert shape.unresolved == []

    def test_file_with_no_header_is_fatal(self):
        with pytest.raises(CsvFormatError):
            detect_mapping(b",,\n1,2,3")


class TestLineNumbers:
    def test_skip_reports_point_at_the_real_line(self):
        # A blank line in the middle must not shift the reported number.
        result = parse_csv(
            _csv("date,description,amount", "2026-08-26,Comcast,79.99", "", "bad,Shell,40.00")
        )
        assert [s.line for s in result.skipped] == [4]

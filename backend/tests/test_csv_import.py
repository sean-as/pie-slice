from __future__ import annotations

from datetime import date

import pytest

from app.csv_import import (
    MAX_ROWS,
    CsvFormatError,
    defuse_formula,
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

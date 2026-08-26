"""
Direct unit tests of app/domain.py — no HTTP, mirrors
frontend/src/domain/{splitting,balances}.test.ts so both implementations
are held to the same behavior.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domain import (
    SplitValidationError,
    compute_balances,
    split_equal,
    split_exact,
    split_percent,
    split_shares,
)
from app.models import Expense, Settlement


class TestSplitEqual:
    def test_splits_evenly_when_it_divides_cleanly(self):
        result = split_equal(300, ["a", "b", "c"])
        assert [(s.member_id, s.amount_cents) for s in result] == [("a", 100), ("b", 100), ("c", 100)]

    def test_distributes_remainder_deterministically_and_sums_exactly(self):
        result = split_equal(100, ["a", "b", "c"])
        assert sum(s.amount_cents for s in result) == 100
        assert sorted((s.amount_cents for s in result), reverse=True) == [34, 33, 33]

    def test_rejects_empty_member_list(self):
        with pytest.raises(SplitValidationError):
            split_equal(100, [])


class TestSplitExact:
    def test_accepts_amounts_summing_to_total(self):
        result = split_exact(500, [("a", 300), ("b", 200)])
        assert [(s.member_id, s.amount_cents) for s in result] == [("a", 300), ("b", 200)]

    def test_rejects_amounts_not_summing_to_total(self):
        with pytest.raises(SplitValidationError):
            split_exact(500, [("a", 300), ("b", 100)])


class TestSplitPercent:
    def test_splits_proportionally(self):
        result = split_percent(1000, [("a", 50), ("b", 50)])
        assert [(s.member_id, s.amount_cents) for s in result] == [("a", 500), ("b", 500)]

    def test_rejects_percentages_not_summing_to_100(self):
        with pytest.raises(SplitValidationError):
            split_percent(1000, [("a", 50), ("b", 40)])

    def test_sums_to_exact_total_even_with_uneven_percentages(self):
        result = split_percent(999, [("a", 33.33), ("b", 33.33), ("c", 33.34)])
        assert sum(s.amount_cents for s in result) == 999


class TestSplitShares:
    def test_splits_proportionally_to_shares(self):
        result = split_shares(300, [("a", 2), ("b", 1)])
        assert [(s.member_id, s.amount_cents) for s in result] == [("a", 200), ("b", 100)]

    def test_sums_exactly_even_when_shares_dont_divide_cleanly(self):
        result = split_shares(100, [("a", 1), ("b", 1), ("c", 1)])
        assert sum(s.amount_cents for s in result) == 100

    def test_rejects_non_positive_shares(self):
        with pytest.raises(SplitValidationError):
            split_shares(100, [("a", 0)])


def _expense(**overrides) -> Expense:
    defaults = dict(
        id="e1",
        group_id="g1",
        description="test",
        amount_cents=0,
        payer_id="alice",
        date=date(2026, 8, 26),
        split_method="equal",
        splits=[],
        created_by_user_id="u1",
    )
    defaults.update(overrides)
    return Expense(**defaults)


MEMBERS = ["alice", "bob", "carol"]


class TestComputeBalances:
    def test_nets_to_zero_with_no_settlements(self):
        expenses = [
            _expense(
                amount_cents=300,
                payer_id="alice",
                splits=[
                    {"memberId": "alice", "amountCents": 100},
                    {"memberId": "bob", "amountCents": 100},
                    {"memberId": "carol", "amountCents": 100},
                ],
            )
        ]
        result = compute_balances(MEMBERS, expenses, [])
        assert sum(b.net_cents for b in result.balances) == 0
        by_id = {b.member_id: b.net_cents for b in result.balances}
        assert by_id == {"alice": 200, "bob": -100, "carol": -100}

    def test_zero_balance_member_not_in_settle_up(self):
        expenses = [
            _expense(
                amount_cents=200,
                payer_id="alice",
                splits=[
                    {"memberId": "alice", "amountCents": 100},
                    {"memberId": "bob", "amountCents": 100},
                ],
            )
        ]
        result = compute_balances(MEMBERS, expenses, [])
        carol = next(b for b in result.balances if b.member_id == "carol")
        assert carol.net_cents == 0
        assert not any(t.from_member_id == "carol" or t.to_member_id == "carol" for t in result.settle_up)

    def test_settlements_move_balances_toward_zero(self):
        expenses = [
            _expense(
                amount_cents=200,
                payer_id="alice",
                splits=[
                    {"memberId": "alice", "amountCents": 100},
                    {"memberId": "bob", "amountCents": 100},
                ],
            )
        ]
        settlements = [
            Settlement(
                id="s1",
                group_id="g1",
                from_member_id="bob",
                to_member_id="alice",
                amount_cents=100,
                date=date(2026, 8, 26),
                created_by_user_id="u1",
            )
        ]
        result = compute_balances(MEMBERS, expenses, settlements)
        by_id = {b.member_id: b.net_cents for b in result.balances}
        assert by_id["alice"] == 0
        assert by_id["bob"] == 0

    def test_settle_up_transfers_sum_to_each_debtors_full_debt(self):
        expenses = [
            _expense(
                amount_cents=300,
                payer_id="alice",
                splits=[
                    {"memberId": "alice", "amountCents": 100},
                    {"memberId": "bob", "amountCents": 100},
                    {"memberId": "carol", "amountCents": 100},
                ],
            )
        ]
        result = compute_balances(MEMBERS, expenses, [])
        total_from_bob = sum(t.amount_cents for t in result.settle_up if t.from_member_id == "bob")
        total_from_carol = sum(t.amount_cents for t in result.settle_up if t.from_member_id == "carol")
        assert total_from_bob == 100
        assert total_from_carol == 100

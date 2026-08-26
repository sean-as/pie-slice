"""
Pure money-math logic — ported 1:1 from frontend/src/domain/splitting.ts and
frontend/src/domain/balances.ts so the two implementations agree exactly.
No FastAPI, no store access: everything here is a plain function of its
arguments, which is what product-spec.md's "always derived, never a stored
running total" constraint requires and what makes this trivially testable.
"""

from __future__ import annotations

from app.models import (
    BalancesResult,
    Expense,
    ExactSplitInput,
    EqualSplitInput,
    MemberBalance,
    PercentSplitInput,
    Settlement,
    SettleUpTransfer,
    SharesSplitInput,
    Split,
    SplitInput,
)


class SplitValidationError(ValueError):
    pass


def _distribute_proportionally(amount_cents: int, weights: list[tuple[str, float]]) -> list[Split]:
    """
    Largest-remainder method: floor each proportional share, then hand out
    the leftover cents one at a time to whoever's fractional share was
    largest (ties broken by list order). Deterministic; always sums to
    exactly amount_cents.
    """
    total_weight = sum(w for _, w in weights)
    if total_weight <= 0:
        raise SplitValidationError("Total weight must be positive.")

    raw = [(member_id, amount_cents * weight / total_weight) for member_id, weight in weights]
    floors = [int(value) for _, value in raw]
    distributed = sum(floors)
    remainder = amount_cents - distributed

    by_fraction = sorted(
        range(len(raw)),
        key=lambda i: (-(raw[i][1] - floors[i]), i),
    )

    result = floors[:]
    for k in range(remainder):
        result[by_fraction[k]] += 1

    return [Split(member_id=weights[i][0], amount_cents=result[i]) for i in range(len(weights))]


def split_equal(amount_cents: int, member_ids: list[str]) -> list[Split]:
    if len(member_ids) == 0:
        raise SplitValidationError("Select at least one member to split with.")
    return _distribute_proportionally(amount_cents, [(member_id, 1.0) for member_id in member_ids])


def split_exact(amount_cents: int, amounts: list[tuple[str, int]]) -> list[Split]:
    if len(amounts) == 0:
        raise SplitValidationError("Select at least one member to split with.")
    total = sum(cents for _, cents in amounts)
    if total != amount_cents:
        raise SplitValidationError(
            f"Exact amounts sum to {total} cents but the expense total is {amount_cents} cents."
        )
    return [Split(member_id=member_id, amount_cents=cents) for member_id, cents in amounts]


def split_percent(amount_cents: int, percentages: list[tuple[str, float]]) -> list[Split]:
    if len(percentages) == 0:
        raise SplitValidationError("Select at least one member to split with.")
    total = sum(percent for _, percent in percentages)
    if abs(total - 100) > 0.01:
        raise SplitValidationError(f"Percentages sum to {total}%, but must sum to 100%.")
    return _distribute_proportionally(amount_cents, percentages)


def split_shares(amount_cents: int, shares: list[tuple[str, int]]) -> list[Split]:
    if len(shares) == 0:
        raise SplitValidationError("Select at least one member to split with.")
    for _, count in shares:
        if count <= 0:
            raise SplitValidationError("Shares must be positive whole numbers.")
    return _distribute_proportionally(amount_cents, [(member_id, float(count)) for member_id, count in shares])


def resolve_splits(amount_cents: int, split_input: SplitInput) -> list[Split]:
    if isinstance(split_input, EqualSplitInput):
        return split_equal(amount_cents, split_input.member_ids)
    if isinstance(split_input, ExactSplitInput):
        return split_exact(amount_cents, [(a.member_id, a.amount_cents) for a in split_input.amounts])
    if isinstance(split_input, PercentSplitInput):
        return split_percent(amount_cents, [(p.member_id, p.percent) for p in split_input.percentages])
    if isinstance(split_input, SharesSplitInput):
        return split_shares(amount_cents, [(s.member_id, s.shares) for s in split_input.shares])
    raise SplitValidationError(f"Unknown split method: {split_input!r}")


def compute_balances(
    member_ids: list[str], expenses: list[Expense], settlements: list[Settlement]
) -> BalancesResult:
    """
    Pure function: balances are always derived from (expenses, settlements),
    never stored as a mutable running total (product-spec.md).

    net_cents: positive = owed money by the group, negative = owes the group.
    """
    net: dict[str, int] = {member_id: 0 for member_id in member_ids}

    for expense in expenses:
        net[expense.payer_id] = net.get(expense.payer_id, 0) + expense.amount_cents
        for split in expense.splits:
            net[split.member_id] = net.get(split.member_id, 0) - split.amount_cents

    for settlement in settlements:
        net[settlement.from_member_id] = net.get(settlement.from_member_id, 0) + settlement.amount_cents
        net[settlement.to_member_id] = net.get(settlement.to_member_id, 0) - settlement.amount_cents

    balances = [MemberBalance(member_id=member_id, net_cents=net.get(member_id, 0)) for member_id in member_ids]

    return BalancesResult(balances=balances, settle_up=_simplify_debts(balances))


def _simplify_debts(balances: list[MemberBalance]) -> list[SettleUpTransfer]:
    """
    Greedy debt simplification: repeatedly match the largest creditor with
    the largest debtor. Standard practical approach (what Splitwise-style
    apps use) — not guaranteed to be the globally minimal transaction count
    (that's NP-hard in general), but produces a small, sensible set.
    """
    creditors = sorted(
        [{"member_id": b.member_id, "net_cents": b.net_cents} for b in balances if b.net_cents > 0],
        key=lambda b: -b["net_cents"],
    )
    debtors = sorted(
        [{"member_id": b.member_id, "net_cents": b.net_cents} for b in balances if b.net_cents < 0],
        key=lambda b: b["net_cents"],
    )

    transfers: list[SettleUpTransfer] = []
    ci = 0
    di = 0

    while ci < len(creditors) and di < len(debtors):
        creditor = creditors[ci]
        debtor = debtors[di]
        amount = min(creditor["net_cents"], -debtor["net_cents"])

        if amount > 0:
            transfers.append(
                SettleUpTransfer(from_member_id=debtor["member_id"], to_member_id=creditor["member_id"], amount_cents=amount)
            )
            creditor["net_cents"] -= amount
            debtor["net_cents"] += amount

        if creditor["net_cents"] == 0:
            ci += 1
        if debtor["net_cents"] == 0:
            di += 1

    return transfers

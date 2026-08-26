import type { Expense, Settlement, MemberBalance, SettleUpTransfer, BalancesResult } from "./types";

/**
 * Pure function: balances are always derived from (expenses, settlements),
 * never stored as a mutable running total, so an edit/delete can never leave
 * stale balances (see product-spec.md's technical constraints).
 *
 * netCents: positive = owed money by the group, negative = owes the group.
 */
export function computeBalances(
  memberIds: string[],
  expenses: Expense[],
  settlements: Settlement[]
): BalancesResult {
  const net = new Map<string, number>(memberIds.map((id) => [id, 0]));

  for (const expense of expenses) {
    net.set(expense.payerId, (net.get(expense.payerId) ?? 0) + expense.amountCents);
    for (const split of expense.splits) {
      net.set(split.memberId, (net.get(split.memberId) ?? 0) - split.amountCents);
    }
  }

  for (const settlement of settlements) {
    net.set(settlement.fromMemberId, (net.get(settlement.fromMemberId) ?? 0) + settlement.amountCents);
    net.set(settlement.toMemberId, (net.get(settlement.toMemberId) ?? 0) - settlement.amountCents);
  }

  const balances: MemberBalance[] = memberIds.map((memberId) => ({
    memberId,
    netCents: net.get(memberId) ?? 0,
  }));

  return { balances, settleUp: simplifyDebts(balances) };
}

/**
 * Greedy debt simplification: repeatedly match the largest creditor with the
 * largest debtor. This is the standard practical approach (what Splitwise-
 * style apps use) — it produces a small, sensible set of transfers, though
 * finding the provably minimal number of transactions is NP-hard in general
 * and not attempted here.
 */
function simplifyDebts(balances: MemberBalance[]): SettleUpTransfer[] {
  const creditors = balances
    .filter((b) => b.netCents > 0)
    .map((b) => ({ ...b }))
    .sort((a, b) => b.netCents - a.netCents);
  const debtors = balances
    .filter((b) => b.netCents < 0)
    .map((b) => ({ ...b }))
    .sort((a, b) => a.netCents - b.netCents);

  const transfers: SettleUpTransfer[] = [];
  let ci = 0;
  let di = 0;

  while (ci < creditors.length && di < debtors.length) {
    const creditor = creditors[ci];
    const debtor = debtors[di];
    const amount = Math.min(creditor.netCents, -debtor.netCents);

    if (amount > 0) {
      transfers.push({ fromMemberId: debtor.memberId, toMemberId: creditor.memberId, amountCents: amount });
      creditor.netCents -= amount;
      debtor.netCents += amount;
    }

    if (creditor.netCents === 0) ci++;
    if (debtor.netCents === 0) di++;
  }

  return transfers;
}

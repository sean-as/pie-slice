import type { Expense, Settlement } from "./types";

export type LedgerEntry =
  | { kind: "expense"; date: string; expense: Expense }
  | { kind: "settlement"; date: string; settlement: Settlement };

/**
 * One date-ordered list of expenses and settlements, newest first. The two
 * stay separate records (settlements have no split or category and must not
 * count toward category totals); this is only the display merge.
 *
 * Same-day ties keep a stable order: the inputs arrive oldest-first from the
 * server, so within a day the later-created entry comes first, and an
 * expense sorts above a settlement on the same day.
 */
export function mergeLedger(expenses: Expense[], settlements: Settlement[]): LedgerEntry[] {
  const entries: { entry: LedgerEntry; order: number }[] = [
    ...expenses.map((expense, i) => ({
      entry: { kind: "expense" as const, date: expense.date, expense },
      order: i,
    })),
    ...settlements.map((settlement, i) => ({
      entry: { kind: "settlement" as const, date: settlement.date, settlement },
      order: i,
    })),
  ];

  return entries
    .sort((a, b) => {
      if (a.entry.date !== b.entry.date) return a.entry.date < b.entry.date ? 1 : -1;
      if (a.entry.kind !== b.entry.kind) return a.entry.kind === "expense" ? -1 : 1;
      return b.order - a.order;
    })
    .map((e) => e.entry);
}

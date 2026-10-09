import { describe, expect, it } from "vitest";
import { mergeLedger } from "./ledger";
import type { Expense, Settlement } from "./types";

const exp = (id: string, date: string): Expense => ({
  id,
  groupId: "g",
  description: id,
  amountCents: 100,
  payerId: "a",
  date,
  splitMethod: "equal",
  splits: [],
  createdByUserId: "u",
});
const set = (id: string, date: string): Settlement => ({
  id,
  groupId: "g",
  fromMemberId: "a",
  toMemberId: "b",
  amountCents: 100,
  date,
  createdByUserId: "u",
});

const ids = (entries: ReturnType<typeof mergeLedger>) =>
  entries.map((e) => (e.kind === "expense" ? e.expense.id : e.settlement.id));

describe("mergeLedger", () => {
  it("orders mixed entries newest first", () => {
    const out = mergeLedger([exp("e1", "2026-08-01"), exp("e2", "2026-08-10")], [set("s1", "2026-08-05")]);
    expect(ids(out)).toEqual(["e2", "s1", "e1"]);
  });

  it("breaks same-day ties: expense above settlement, later-created first", () => {
    const out = mergeLedger(
      [exp("e1", "2026-08-05"), exp("e2", "2026-08-05")],
      [set("s1", "2026-08-05"), set("s2", "2026-08-05")]
    );
    expect(ids(out)).toEqual(["e2", "e1", "s2", "s1"]);
  });

  it("handles empty input", () => {
    expect(mergeLedger([], [])).toEqual([]);
  });
});

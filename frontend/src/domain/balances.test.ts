import { describe, it, expect } from "vitest";
import { computeBalances } from "./balances";
import type { Expense, Settlement } from "./types";

const members = ["alice", "bob", "carol"];

function expense(partial: Partial<Expense>): Expense {
  return {
    id: "e1",
    groupId: "g1",
    description: "test",
    amountCents: 0,
    payerId: "alice",
    date: "2026-08-26",
    splitMethod: "equal",
    splits: [],
    createdByUserId: "u1",
    ...partial,
  };
}

describe("computeBalances", () => {
  it("nets to zero across all members with no settlements", () => {
    const expenses = [
      expense({
        amountCents: 300,
        payerId: "alice",
        splits: [
          { memberId: "alice", amountCents: 100 },
          { memberId: "bob", amountCents: 100 },
          { memberId: "carol", amountCents: 100 },
        ],
      }),
    ];
    const { balances } = computeBalances(members, expenses, []);
    const sum = balances.reduce((t, b) => t + b.netCents, 0);
    expect(sum).toBe(0);

    const byId = Object.fromEntries(balances.map((b) => [b.memberId, b.netCents]));
    expect(byId.alice).toBe(200); // paid 300, owes 100 -> net +200
    expect(byId.bob).toBe(-100);
    expect(byId.carol).toBe(-100);
  });

  it("a member with net zero does not appear in settle-up", () => {
    const expenses = [
      expense({
        amountCents: 200,
        payerId: "alice",
        splits: [
          { memberId: "alice", amountCents: 100 },
          { memberId: "bob", amountCents: 100 },
        ],
      }),
    ];
    const { balances, settleUp } = computeBalances(members, expenses, []);
    const carol = balances.find((b) => b.memberId === "carol")!;
    expect(carol.netCents).toBe(0);
    expect(settleUp.some((t) => t.fromMemberId === "carol" || t.toMemberId === "carol")).toBe(false);
  });

  it("settlements move balances back toward zero", () => {
    const expenses = [
      expense({
        amountCents: 200,
        payerId: "alice",
        splits: [
          { memberId: "alice", amountCents: 100 },
          { memberId: "bob", amountCents: 100 },
        ],
      }),
    ];
    const settlements: Settlement[] = [
      {
        id: "s1",
        groupId: "g1",
        fromMemberId: "bob",
        toMemberId: "alice",
        amountCents: 100,
        date: "2026-08-26",
        createdByUserId: "u1",
      },
    ];
    const { balances } = computeBalances(members, expenses, settlements);
    const byId = Object.fromEntries(balances.map((b) => [b.memberId, b.netCents]));
    expect(byId.alice).toBe(0);
    expect(byId.bob).toBe(0);
  });

  it("settle-up transfers sum to each debtor's full debt", () => {
    const expenses = [
      expense({
        amountCents: 300,
        payerId: "alice",
        splits: [
          { memberId: "alice", amountCents: 100 },
          { memberId: "bob", amountCents: 100 },
          { memberId: "carol", amountCents: 100 },
        ],
      }),
    ];
    const { settleUp } = computeBalances(members, expenses, []);
    const totalFromBob = settleUp
      .filter((t) => t.fromMemberId === "bob")
      .reduce((sum, t) => sum + t.amountCents, 0);
    const totalFromCarol = settleUp
      .filter((t) => t.fromMemberId === "carol")
      .reduce((sum, t) => sum + t.amountCents, 0);
    expect(totalFromBob).toBe(100);
    expect(totalFromCarol).toBe(100);
  });
});

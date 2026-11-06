import { describe, expect, it } from "vitest";
import { categoryByMonth, categoryByYear, previousMonth, totalThrough, UNCATEGORISED } from "./categoryMonths";
import type { Expense } from "./types";

function exp(date: string, amountCents: number, category: string | null, payerId = "a", splits = [
  { memberId: "a", amountCents: Math.ceil(amountCents / 2) },
  { memberId: "b", amountCents: Math.floor(amountCents / 2) },
]): Expense {
  return {
    id: `${date}-${amountCents}-${category}`,
    groupId: "g",
    description: "x",
    amountCents,
    payerId,
    date,
    splitMethod: "equal",
    splits,
    createdByUserId: "u",
    category,
  };
}

describe("categoryByMonth", () => {
  it("splits on month boundaries", () => {
    const out = categoryByMonth([exp("2026-07-31", 100, "Food"), exp("2026-08-01", 200, "Food")]);
    expect(out.map((m) => [m.month, m.totalCents])).toEqual([
      ["2026-08", 200],
      ["2026-07", 100],
    ]);
  });

  it("puts blank/missing categories in Uncategorised and totals reconcile", () => {
    const [aug] = categoryByMonth([
      exp("2026-08-01", 500, "Food"),
      exp("2026-08-02", 300, ""),
      exp("2026-08-03", 200, null),
    ]);
    expect(aug.categories.map((c) => [c.category, c.totalCents])).toEqual([
      ["Food", 500],
      [UNCATEGORISED, 500],
    ]);
    expect(aug.categories.reduce((s, c) => s + c.totalCents, 0)).toBe(aug.totalCents);
  });

  it("normalises case and whitespace, keeping the first spelling", () => {
    const [aug] = categoryByMonth([exp("2026-08-01", 100, "Food"), exp("2026-08-02", 100, " food ")]);
    expect(aug.categories).toHaveLength(1);
    expect(aug.categories[0]).toMatchObject({ category: "Food", totalCents: 200 });
  });

  it("sums uneven splits exactly into per-member owed and paid", () => {
    const [aug] = categoryByMonth([exp("2026-08-01", 101, "Food"), exp("2026-08-02", 101, "Food")]);
    const food = aug.categories[0];
    const owed = food.members.reduce((s, m) => s + m.owedCents, 0);
    const paid = food.members.reduce((s, m) => s + m.paidCents, 0);
    expect(owed).toBe(202);
    expect(paid).toBe(202);
    expect(food.members.find((m) => m.memberId === "a")).toMatchObject({ paidCents: 202, owedCents: 102 });
  });

  it("returns nothing for no expenses", () => {
    expect(categoryByMonth([])).toEqual([]);
  });
});

describe("previousMonth", () => {
  it("steps back one calendar month, across year boundaries", () => {
    expect(previousMonth("2026-08")).toBe("2026-07");
    expect(previousMonth("2026-01")).toBe("2025-12");
  });
});

describe("categoryByYear", () => {
  it("rolls months into years, newest first, categories summing to the year", () => {
    const out = categoryByYear([
      exp("2025-12-31", 100, "Food"),
      exp("2026-01-01", 200, "Food"),
      exp("2026-06-15", 300, "food "),
      exp("2026-06-16", 50, null),
    ]);
    expect(out.map((y) => [y.month, y.totalCents])).toEqual([
      ["2026", 550],
      ["2025", 100],
    ]);
    expect(out[0].categories.map((c) => [c.category, c.totalCents])).toEqual([
      ["Food", 500],
      [UNCATEGORISED, 50],
    ]);
  });
});

describe("totalThrough", () => {
  it("counts only same-year expenses up to the month-day, inclusive", () => {
    const e = [exp("2025-03-01", 100, null), exp("2025-03-02", 200, null), exp("2026-01-01", 400, null)];
    expect(totalThrough(e, "2025", "03-01")).toBe(100);
    expect(totalThrough(e, "2025", "12-31")).toBe(300);
  });
});

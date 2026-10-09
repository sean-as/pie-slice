import type { Expense } from "./types";

export const UNCATEGORISED = "Uncategorised";

export type MemberCategoryAmounts = {
  memberId: string;
  paidCents: number;
  owedCents: number;
};

export type CategoryTotal = {
  category: string;
  totalCents: number;
  members: MemberCategoryAmounts[];
};

export type MonthBreakdown = {
  /** "YYYY-MM" */
  month: string;
  totalCents: number;
  categories: CategoryTotal[];
};

function categoryKey(category: string | null | undefined): string {
  return (category ?? "").trim().toLowerCase();
}

/**
 * Spending per category per month, derived from expenses only — settlements
 * carry no category and never count. Category matching ignores case and
 * surrounding whitespace ("Food" and "food " are one bucket, shown under
 * the spelling seen first); blank goes to "Uncategorised" so every month's
 * categories always sum to its total.
 *
 * Months are newest first; categories within a month by size, largest first.
 */
export function categoryByMonth(expenses: Expense[]): MonthBreakdown[] {
  type Bucket = { label: string; totalCents: number; members: Map<string, MemberCategoryAmounts> };
  const months = new Map<string, Map<string, Bucket>>();

  for (const expense of expenses) {
    const month = expense.date.slice(0, 7);
    const key = categoryKey(expense.category);
    const label = key === "" ? UNCATEGORISED : (expense.category ?? "").trim();

    const buckets = months.get(month) ?? new Map<string, Bucket>();
    months.set(month, buckets);
    const bucket = buckets.get(key) ?? { label, totalCents: 0, members: new Map() };
    buckets.set(key, bucket);

    bucket.totalCents += expense.amountCents;
    const forMember = (memberId: string) => {
      const existing = bucket.members.get(memberId) ?? { memberId, paidCents: 0, owedCents: 0 };
      bucket.members.set(memberId, existing);
      return existing;
    };
    forMember(expense.payerId).paidCents += expense.amountCents;
    for (const split of expense.splits) forMember(split.memberId).owedCents += split.amountCents;
  }

  return [...months.entries()]
    .sort(([a], [b]) => (a < b ? 1 : a > b ? -1 : 0))
    .map(([month, buckets]) => {
      const categories: CategoryTotal[] = [...buckets.values()]
        .map((b) => ({ category: b.label, totalCents: b.totalCents, members: [...b.members.values()] }))
        .sort((a, b) => b.totalCents - a.totalCents || a.category.localeCompare(b.category));
      return { month, totalCents: categories.reduce((sum, c) => sum + c.totalCents, 0), categories };
    });
}

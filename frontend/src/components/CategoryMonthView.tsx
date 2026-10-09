import { useState } from "react";
import type { Expense, Member } from "../domain/types";
import { formatCents } from "../domain/money";
import { categoryByMonth } from "../domain/categoryMonths";

function monthLabel(month: string): string {
  const [y, m] = month.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

/**
 * Spending by category for one month at a time, with each member's paid and
 * owed share. Settlements are not part of this — only expenses have
 * categories.
 */
export function CategoryMonthView({ expenses, members }: { expenses: Expense[]; members: Member[] }) {
  const months = categoryByMonth(expenses);
  const [index, setIndex] = useState(0);
  const nameById = new Map(members.map((m) => [m.id, m.displayName]));

  if (months.length === 0) return null;
  const current = months[Math.min(index, months.length - 1)];
  const at = Math.min(index, months.length - 1);

  return (
    <section>
      <h2>Spending by category</h2>
      <div className="actions">
        <button type="button" className="secondary" disabled={at >= months.length - 1} onClick={() => setIndex(at + 1)}>
          ← Earlier
        </button>
        <strong>{monthLabel(current.month)}</strong>
        <button type="button" className="secondary" disabled={at === 0} onClick={() => setIndex(at - 1)}>
          Later →
        </button>
      </div>
      <p className="meta">Total {formatCents(current.totalCents)}</p>
      <ul className="list">
        {current.categories.map((c) => (
          <li key={c.category} className="card">
            <span>
              {c.category}
              <br />
              <span className="meta">
                {c.members
                  .map(
                    (m) =>
                      `${nameById.get(m.memberId) ?? "Unknown"}: paid ${formatCents(m.paidCents)}, owes ${formatCents(m.owedCents)}`
                  )
                  .join(" · ")}
              </span>
            </span>
            <span>{formatCents(c.totalCents)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

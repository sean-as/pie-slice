import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import type { Expense, Group } from "../domain/types";
import { formatCents } from "../domain/money";
import { categoryByMonth, previousMonth } from "../domain/categoryMonths";
import { expenseService } from "../services";
import { useCurrentUser } from "../hooks/useCurrentUser";

function monthLabel(month: string): string {
  const [y, m] = month.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

function percent(part: number, whole: number): number {
  return whole === 0 ? 0 : Math.round((part / whole) * 100);
}

export function SpendingPage() {
  const { user, loading: userLoading } = useCurrentUser();
  const { groupId } = useParams<{ groupId: string }>();
  const [group, setGroup] = useState<Group | null | undefined>(undefined);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [index, setIndex] = useState(0);
  const [openCategory, setOpenCategory] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!groupId || !user) return;
    const [g, exps] = await Promise.all([
      expenseService.getGroup(groupId),
      expenseService.listExpenses(groupId).catch(() => []),
    ]);
    setGroup(g);
    setExpenses(exps);
  }, [groupId, user]);

  useEffect(() => {
    load();
  }, [load]);

  if (userLoading || group === undefined) return <p>Loading…</p>;
  if (!user) return <Navigate to="/login" replace />;
  if (group === null) {
    return (
      <div>
        <h1>Group not found</h1>
        <p>This group doesn't exist, or you're not a member of it.</p>
      </div>
    );
  }

  const months = categoryByMonth(expenses);
  const at = Math.min(index, Math.max(months.length - 1, 0));
  const current = months[at];
  const prior = current ? months.find((m) => m.month === previousMonth(current.month)) : undefined;
  const nameById = new Map(group.members.map((m) => [m.id, m.displayName]));
  const delta = current && prior ? current.totalCents - prior.totalCents : null;

  function go(next: number) {
    setIndex(next);
    setOpenCategory(null);
  }

  return (
    <div>
      <p className="meta">
        <Link to={`/group/${group.id}`}>← Back to group</Link>
      </p>
      <h1>Spending</h1>

      {!current ? (
        <p className="meta">No expenses yet — nothing to break down.</p>
      ) : (
        <>
          <div className="month-nav">
            <button
              type="button"
              className="secondary"
              aria-label="Earlier month"
              disabled={at >= months.length - 1}
              onClick={() => go(at + 1)}
            >
              ←
            </button>
            <strong>{monthLabel(current.month)}</strong>
            <button
              type="button"
              className="secondary"
              aria-label="Later month"
              disabled={at === 0}
              onClick={() => go(at - 1)}
            >
              →
            </button>
          </div>

          <div className="spend-total">
            <span className="spend-total-amount">{formatCents(current.totalCents)}</span>
            {delta !== null && (
              <span className="meta">
                {delta === 0
                  ? `same as ${monthLabel(prior!.month)}`
                  : `${formatCents(Math.abs(delta))} ${delta > 0 ? "more" : "less"} than ${monthLabel(prior!.month)}`}
              </span>
            )}
          </div>

          <ul className="list">
            {current.categories.map((c) => {
              const open = openCategory === c.category;
              const share = percent(c.totalCents, current.totalCents);
              return (
                <li key={c.category} className="spend-row">
                  <button
                    type="button"
                    className="spend-summary"
                    aria-expanded={open}
                    onClick={() => setOpenCategory(open ? null : c.category)}
                  >
                    <span className="spend-head">
                      <span>{c.category}</span>
                      <span>
                        {formatCents(c.totalCents)} <span className="meta">· {share}%</span>
                      </span>
                    </span>
                    <span className="spend-bar" aria-hidden="true">
                      <span className="spend-bar-fill" style={{ width: `${share}%` }} />
                    </span>
                  </button>
                  {open && (
                    <table className="spend-members">
                      <thead>
                        <tr>
                          <th />
                          <th>Paid</th>
                          <th>Owes</th>
                        </tr>
                      </thead>
                      <tbody>
                        {c.members.map((m) => (
                          <tr key={m.memberId}>
                            <td>{nameById.get(m.memberId) ?? "Unknown"}</td>
                            <td>{formatCents(m.paidCents)}</td>
                            <td>{formatCents(m.owedCents)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}

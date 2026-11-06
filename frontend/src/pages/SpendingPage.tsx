import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import type { Expense, Group } from "../domain/types";
import { formatCents } from "../domain/money";
import { categoryByMonth, categoryByYear, previousMonth, totalThrough } from "../domain/categoryMonths";
import { StackedMonthChart } from "../components/StackedMonthChart";
import { categoryColors } from "../domain/categoryColors";
import { expenseService } from "../services";
import { useCurrentUser } from "../hooks/useCurrentUser";

function monthLabel(month: string): string {
  const [y, m] = month.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

function todayParts(): { year: string; monthDay: string } {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return { year: String(now.getFullYear()), monthDay: `${pad(now.getMonth() + 1)}-${pad(now.getDate())}` };
}

function percent(part: number, whole: number): number {
  return whole === 0 ? 0 : Math.round((part / whole) * 100);
}

export function SpendingPage() {
  const { user, loading: userLoading } = useCurrentUser();
  const { groupId } = useParams<{ groupId: string }>();
  const [group, setGroup] = useState<Group | null | undefined>(undefined);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [view, setView] = useState<"year" | "month">("year");
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

  const byYear = view === "year";
  const months = byYear ? categoryByYear(expenses) : categoryByMonth(expenses);
  const at = Math.min(index, Math.max(months.length - 1, 0));
  const current = months[at];
  const today = todayParts();
  const ytd = byYear && current?.month === today.year;
  const nameById = new Map(group.members.map((m) => [m.id, m.displayName]));

  // What to compare against: last year (same dates, if this one is still in
  // progress) or last calendar month.
  let delta: number | null = null;
  let against = "";
  if (current && byYear) {
    const prevYear = String(Number(current.month) - 1);
    if (months.some((y) => y.month === prevYear)) {
      const prevTotal = totalThrough(expenses, prevYear, ytd ? today.monthDay : "12-31");
      delta = current.totalCents - prevTotal;
      against = ytd ? `same point in ${prevYear}` : prevYear;
    }
  } else if (current) {
    const prior = months.find((m) => m.month === previousMonth(current.month));
    if (prior) {
      delta = current.totalCents - prior.totalCents;
      against = monthLabel(prior.month);
    }
  }
  const chartYear = current ? (byYear ? current.month : current.month.slice(0, 4)) : "";
  const allMonths = categoryByMonth(expenses);
  const yearCategories = current
    ? (categoryByYear(expenses).find((y) => y.month === chartYear)?.categories ?? [])
    : [];
  const colors = categoryColors(yearCategories);
  const periodLabel = current ? (byYear ? (ytd ? `${current.month} · year to date` : current.month) : monthLabel(current.month)) : "";

  function switchView(next: "year" | "month") {
    setView(next);
    setIndex(0);
    setOpenCategory(null);
  }

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

      <div className="view-toggle" role="group" aria-label="Group spending by">
        <button type="button" className={byYear ? "" : "secondary"} aria-pressed={byYear} onClick={() => switchView("year")}>
          Year
        </button>
        <button type="button" className={byYear ? "secondary" : ""} aria-pressed={!byYear} onClick={() => switchView("month")}>
          Month
        </button>
      </div>

      {!current ? (
        <p className="meta">No expenses yet — nothing to break down.</p>
      ) : (
        <>
          <div className="month-nav">
            <button
              type="button"
              className="secondary"
              aria-label={byYear ? "Earlier year" : "Earlier month"}
              disabled={at >= months.length - 1}
              onClick={() => go(at + 1)}
            >
              ←
            </button>
            <strong>{periodLabel}</strong>
            <button
              type="button"
              className="secondary"
              aria-label={byYear ? "Later year" : "Later month"}
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
                  ? `same as ${against}`
                  : `${formatCents(Math.abs(delta))} ${delta > 0 ? "more" : "less"} than ${against}`}
              </span>
            )}
          </div>

          <StackedMonthChart
            year={chartYear}
            months={allMonths.filter((m) => m.month.startsWith(chartYear))}
            yearCategories={yearCategories}
            selectedMonth={byYear ? undefined : current.month}
            onSelectMonth={(month) => {
              setView("month");
              setIndex(allMonths.findIndex((m) => m.month === month));
              setOpenCategory(null);
            }}
          />

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
                      <span className="spend-bar-fill" style={{ width: `${share}%`, background: colors.get(c.category.trim().toLowerCase()) }} />
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

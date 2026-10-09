import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import type { BalancesResult, Expense, Group, Settlement } from "../domain/types";
import { formatCents } from "../domain/money";
import { expenseService } from "../services";
import { ExpenseForm } from "../components/ExpenseForm";
import { mergeLedger } from "../domain/ledger";
import { BalancesView } from "../components/BalancesView";
import { ActionsMenu } from "../components/ActionsMenu";
import { useCurrentUser } from "../hooks/useCurrentUser";

export function GroupPage() {
  const { user, loading: userLoading } = useCurrentUser();
  const { groupId } = useParams<{ groupId: string }>();
  const [group, setGroup] = useState<Group | null | undefined>(undefined);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [settlements, setSettlements] = useState<Settlement[]>([]);
  const [balances, setBalances] = useState<BalancesResult | null>(null);

  const [editingExpenseId, setEditingExpenseId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!groupId || !user) return;
    const [g, exps, settles, bals] = await Promise.all([
      expenseService.getGroup(groupId),
      expenseService.listExpenses(groupId).catch(() => []),
      expenseService.listSettlements(groupId).catch(() => []),
      expenseService.getBalances(groupId).catch(() => null),
    ]);
    setGroup(g);
    setExpenses(exps);
    setSettlements(settles);
    setBalances(bals);
  }, [groupId, user]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (userLoading) {
    return <p>Loading…</p>;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  if (group === undefined) {
    return <p>Loading…</p>;
  }
  if (group === null) {
    return (
      <div>
        <h1>Group not found</h1>
        <p>This group doesn't exist, or you're not a member of it.</p>
      </div>
    );
  }

  const nameById = new Map(group.members.map((m) => [m.id, m.displayName]));

  async function handleDeleteExpense(expenseId: string) {
    if (!groupId) return;
    await expenseService.deleteExpense(groupId, expenseId);
    await refresh();
  }

  async function handleDeleteSettlement(settlementId: string) {
    if (!groupId) return;
    await expenseService.deleteSettlement(groupId, settlementId);
    await refresh();
  }

  const ledger = mergeLedger(expenses, settlements);
  const memberCount = group.members.length;

  return (
    <div>
      <h1>{group.name}</h1>
      {group.description && <p>{group.description}</p>}
      <p className="meta">
        <Link to={`/group/${group.id}/members`}>
          {memberCount} member{memberCount === 1 ? "" : "s"}
        </Link>
      </p>

      {balances && (
        <BalancesView
          balances={balances}
          members={group.members}
          settlements={settlements}
          currentUserId={user.id}
          onRecord={async (input) => {
            await expenseService.addSettlement(groupId!, input);
            await refresh();
          }}
          onUpdate={async (settlementId, input) => {
            await expenseService.updateSettlement(groupId!, settlementId, input);
            await refresh();
          }}
          onDelete={handleDeleteSettlement}
        />
      )}

      <div className="section-header">
        <h2>Expenses</h2>
        <Link to={`/group/${group.id}/add`} className="button-link">
          + Add expense
        </Link>
      </div>
      <ul className="list">
        {ledger.length === 0 && <p className="meta">No expenses yet.</p>}
        {ledger.map((entry) => {
          if (entry.kind === "settlement") {
            const s = entry.settlement;
            return (
              <li key={`s-${s.id}`} className="card">
                <span>
                  <span className="meta">Settlement · </span>
                  {nameById.get(s.fromMemberId) ?? "Unknown"} paid {nameById.get(s.toMemberId) ?? "Unknown"}{" "}
                  {formatCents(s.amountCents)}
                  <br />
                  <span className="meta">
                    {s.date}
                    {s.method ? ` · ${s.method}` : ""} · logged by{" "}
                    {s.createdByUserId === user.id ? "you" : "someone else"}
                  </span>
                </span>
                {s.createdByUserId === user.id && (
                  <button type="button" className="secondary" onClick={() => handleDeleteSettlement(s.id)}>
                    Remove
                  </button>
                )}
              </li>
            );
          }

          const exp = entry.expense;
          return editingExpenseId === exp.id ? (
            <li key={`e-${exp.id}`}>
              <ExpenseForm
                members={group.members}
                initial={exp}
                onCancel={() => setEditingExpenseId(null)}
                onSubmit={async (input) => {
                  await expenseService.updateExpense(groupId!, exp.id, input);
                  setEditingExpenseId(null);
                  await refresh();
                }}
              />
            </li>
          ) : (
            <li key={`e-${exp.id}`} className="card">
              <span>
                {exp.description} — {formatCents(exp.amountCents)}
                <br />
                <span className="meta">
                  paid by {nameById.get(exp.payerId) ?? "Unknown"} on {exp.date}
                  {exp.category && ` · ${exp.category}`} · logged by{" "}
                  {exp.createdByUserId === user.id ? "you" : "someone else"}
                </span>
              </span>
              {exp.createdByUserId === user.id && (
                <ActionsMenu
                  onEdit={() => setEditingExpenseId(exp.id)}
                  onDelete={() => handleDeleteExpense(exp.id)}
                />
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

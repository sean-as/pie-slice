import { useCallback, useEffect, useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import type { BalancesResult, Expense, Group, Settlement } from "../domain/types";
import { formatCents } from "../domain/money";
import { expenseService } from "../services";
import { ExpenseForm } from "../components/ExpenseForm";
import { SettlementForm } from "../components/SettlementForm";
import { BalancesView } from "../components/BalancesView";
import { CsvImportPanel } from "../components/CsvImportPanel";
import { useCurrentUser } from "../hooks/useCurrentUser";

export function GroupPage() {
  const { user, loading: userLoading } = useCurrentUser();
  const { groupId } = useParams<{ groupId: string }>();
  const [group, setGroup] = useState<Group | null | undefined>(undefined);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [settlements, setSettlements] = useState<Settlement[]>([]);
  const [balances, setBalances] = useState<BalancesResult | null>(null);

  const [linkedEmail, setLinkedEmail] = useState("");
  const [placeholderName, setPlaceholderName] = useState("");
  const [memberError, setMemberError] = useState<string | null>(null);
  /** The name we've warned about; submitting it again confirms it. */
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null);
  const [showExpenseForm, setShowExpenseForm] = useState(false);
  const [editingExpenseId, setEditingExpenseId] = useState<string | null>(null);
  const [showSettlementForm, setShowSettlementForm] = useState(false);
  const [editingSettlementId, setEditingSettlementId] = useState<string | null>(null);

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

  async function handleAddLinkedMember(e: React.FormEvent) {
    e.preventDefault();
    setMemberError(null);
    const email = linkedEmail.trim();
    if (!email || !groupId) return;
    try {
      await expenseService.addLinkedMember(groupId, email);
      setLinkedEmail("");
      await refresh();
    } catch (err) {
      setMemberError(err instanceof Error ? err.message : "Could not add that member.");
    }
  }

  async function handleAddPlaceholderMember(e: React.FormEvent) {
    e.preventDefault();
    setMemberError(null);
    const name = placeholderName.trim();
    if (!name || !groupId) return;

    // Duplicate names are allowed but make "who owes whom" ambiguous, so
    // warn once and let a second submit through (product-spec.md).
    const clashes = group!.members.some(
      (m) => m.displayName.trim().toLowerCase() === name.toLowerCase()
    );
    if (clashes && duplicateWarning !== name) {
      setDuplicateWarning(name);
      return;
    }
    setDuplicateWarning(null);

    try {
      await expenseService.addPlaceholderMember(groupId, name);
      setPlaceholderName("");
      setDuplicateWarning(null);
      await refresh();
    } catch (err) {
      setMemberError(err instanceof Error ? err.message : "Could not add that member.");
    }
  }

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

  return (
    <div>
      <h1>{group.name}</h1>

      <h2>Members</h2>
      <ul className="list">
        {group.members.map((m) => (
          <li key={m.id} className="card">
            <span>{m.displayName}</span>
            {!m.userId && <span className="meta">no account</span>}
          </li>
        ))}
      </ul>
      <form onSubmit={handleAddLinkedMember} className="inline-form">
        <input
          type="email"
          value={linkedEmail}
          onChange={(e) => setLinkedEmail(e.target.value)}
          placeholder="Add by email (existing account)"
        />
        <button type="submit">Add</button>
      </form>
      <form onSubmit={handleAddPlaceholderMember} className="inline-form">
        <input
          type="text"
          value={placeholderName}
          onChange={(e) => setPlaceholderName(e.target.value)}
          placeholder="Add a name (no account)"
        />
        <button type="submit" className="secondary">
          Add placeholder
        </button>
      </form>
      {duplicateWarning && (
        <p className="warning">
          Someone in this group is already called “{duplicateWarning}” — that makes “who owes whom”
          ambiguous. Add it again to confirm.
        </p>
      )}
      {memberError && <p className="error">{memberError}</p>}

      {balances && <BalancesView balances={balances} members={group.members} />}

      <h2>Expenses</h2>
      <ul className="list">
        {expenses.length === 0 && <p className="meta">No expenses yet.</p>}
        {expenses.map((exp) =>
          editingExpenseId === exp.id ? (
            <li key={exp.id}>
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
            <li key={exp.id} className="card">
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
                <span className="actions">
                  <button className="secondary" onClick={() => setEditingExpenseId(exp.id)}>
                    Edit
                  </button>
                  <button className="danger" onClick={() => handleDeleteExpense(exp.id)}>
                    Delete
                  </button>
                </span>
              )}
            </li>
          )
        )}
      </ul>
      {showExpenseForm ? (
        <ExpenseForm
          members={group.members}
          onCancel={() => setShowExpenseForm(false)}
          onSubmit={async (input) => {
            await expenseService.addExpense(groupId!, input);
            setShowExpenseForm(false);
            await refresh();
          }}
        />
      ) : (
        <button onClick={() => setShowExpenseForm(true)}>+ Add expense</button>
      )}

      <CsvImportPanel groupId={group.id} onImported={refresh} />

      <h2>Settlements</h2>
      <ul className="list">
        {settlements.length === 0 && <p className="meta">No settlements recorded yet.</p>}
        {settlements.map((s) =>
          editingSettlementId === s.id ? (
            <li key={s.id}>
              <SettlementForm
                members={group.members}
                initial={s}
                onCancel={() => setEditingSettlementId(null)}
                onSubmit={async (input) => {
                  await expenseService.updateSettlement(groupId!, s.id, input);
                  setEditingSettlementId(null);
                  await refresh();
                }}
              />
            </li>
          ) : (
            <li key={s.id} className="card">
              <span>
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
                <span className="actions">
                  <button className="secondary" onClick={() => setEditingSettlementId(s.id)}>
                    Edit
                  </button>
                  <button className="danger" onClick={() => handleDeleteSettlement(s.id)}>
                    Delete
                  </button>
                </span>
              )}
            </li>
          )
        )}
      </ul>
      {showSettlementForm ? (
        <SettlementForm
          members={group.members}
          onCancel={() => setShowSettlementForm(false)}
          onSubmit={async (input) => {
            await expenseService.addSettlement(groupId!, input);
            setShowSettlementForm(false);
            await refresh();
          }}
        />
      ) : (
        <button onClick={() => setShowSettlementForm(true)}>+ Record settlement</button>
      )}
    </div>
  );
}

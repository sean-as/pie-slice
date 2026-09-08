import { useState } from "react";
import type { Expense, Member, SplitMethod } from "../domain/types";
import { parseDollarsToCents, formatCents } from "../domain/money";
import type { AddExpenseInput } from "../services";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function ExpenseForm({
  members,
  initial,
  onSubmit,
  onCancel,
}: {
  members: Member[];
  initial?: Expense;
  onSubmit: (input: AddExpenseInput) => Promise<void>;
  onCancel?: () => void;
}) {
  const [description, setDescription] = useState(initial?.description ?? "");
  const [category, setCategory] = useState(initial?.category ?? "");
  const [amount, setAmount] = useState(initial ? (initial.amountCents / 100).toFixed(2) : "");
  const [payerId, setPayerId] = useState(initial?.payerId ?? members[0]?.id ?? "");
  const [date, setDate] = useState(initial?.date ?? todayIso());
  const [splitMethod, setSplitMethod] = useState<SplitMethod>(initial?.splitMethod ?? "equal");
  const [selected, setSelected] = useState<Set<string>>(
    new Set(initial ? initial.splits.map((s) => s.memberId) : members.map((m) => m.id))
  );
  const [perMemberValue, setPerMemberValue] = useState<Record<string, string>>(() => {
    if (!initial) return {};
    if (initial.splitMethod === "exact") {
      return Object.fromEntries(initial.splits.map((s) => [s.memberId, (s.amountCents / 100).toFixed(2)]));
    }
    return {};
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function toggleMember(memberId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(memberId)) next.delete(memberId);
      else next.add(memberId);
      return next;
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const amountCents = parseDollarsToCents(amount);
    if (amountCents === null || amountCents <= 0) {
      setError("Enter a valid amount greater than $0.");
      return;
    }
    if (!payerId) {
      setError("Choose who paid.");
      return;
    }
    const selectedIds = Array.from(selected);
    if (selectedIds.length === 0) {
      setError("Select at least one person to split with.");
      return;
    }

    let splitInput: AddExpenseInput["splitInput"];
    if (splitMethod === "equal") {
      splitInput = { method: "equal", memberIds: selectedIds };
    } else if (splitMethod === "exact") {
      const amounts = selectedIds.map((memberId) => {
        const cents = parseDollarsToCents(perMemberValue[memberId] ?? "");
        return { memberId, amountCents: cents ?? -1 };
      });
      if (amounts.some((a) => a.amountCents < 0)) {
        setError("Enter a valid dollar amount for every selected person.");
        return;
      }
      splitInput = { method: "exact", amounts };
    } else if (splitMethod === "percent") {
      const percentages = selectedIds.map((memberId) => ({
        memberId,
        percent: Number(perMemberValue[memberId] ?? NaN),
      }));
      if (percentages.some((p) => Number.isNaN(p.percent) || p.percent < 0)) {
        setError("Enter a valid percentage for every selected person.");
        return;
      }
      splitInput = { method: "percent", percentages };
    } else {
      const shares = selectedIds.map((memberId) => ({
        memberId,
        shares: Number(perMemberValue[memberId] ?? NaN),
      }));
      if (shares.some((s) => !Number.isInteger(s.shares) || s.shares <= 0)) {
        setError("Enter a positive whole number of shares for every selected person.");
        return;
      }
      splitInput = { method: "shares", shares };
    }

    setSubmitting(true);
    try {
      await onSubmit({
        description: description.trim() || "Expense",
        amountCents,
        payerId,
        date,
        splitMethod,
        splitInput,
        category: category.trim() || null,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the expense.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="field">
        <label htmlFor="expense-description">Description</label>
        <input
          id="expense-description"
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Groceries"
        />
      </div>

      <div className="field">
        <label htmlFor="expense-category">Category (optional)</label>
        <input
          id="expense-category"
          type="text"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder="Utilities"
          maxLength={100}
        />
      </div>

      <div className="field">
        <label htmlFor="expense-amount">Amount ($)</label>
        <input
          id="expense-amount"
          type="text"
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="42.50"
        />
      </div>

      <div className="field">
        <label htmlFor="expense-payer">Paid by</label>
        <select id="expense-payer" value={payerId} onChange={(e) => setPayerId(e.target.value)}>
          {members.map((m) => (
            <option key={m.id} value={m.id}>
              {m.displayName}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="expense-date">Date</label>
        <input id="expense-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </div>

      <div className="field">
        <label htmlFor="expense-split-method">Split method</label>
        <select
          id="expense-split-method"
          value={splitMethod}
          onChange={(e) => setSplitMethod(e.target.value as SplitMethod)}
        >
          <option value="equal">Equal</option>
          <option value="exact">Exact amounts</option>
          <option value="percent">Percentages</option>
          <option value="shares">Shares</option>
        </select>
      </div>

      <div className="field">
        <label>Split with</label>
        {members.map((m) => (
          <div key={m.id} className="split-row">
            <input
              type="checkbox"
              id={`member-${m.id}`}
              checked={selected.has(m.id)}
              onChange={() => toggleMember(m.id)}
            />
            <label htmlFor={`member-${m.id}`}>{m.displayName}</label>
            {splitMethod !== "equal" && selected.has(m.id) && (
              <input
                type="text"
                className="split-value"
                inputMode="decimal"
                value={perMemberValue[m.id] ?? ""}
                onChange={(e) => setPerMemberValue((prev) => ({ ...prev, [m.id]: e.target.value }))}
                placeholder={
                  splitMethod === "exact" ? "$" : splitMethod === "percent" ? "%" : "shares"
                }
              />
            )}
          </div>
        ))}
        {amount && parseDollarsToCents(amount) !== null && (
          <p className="meta">Total to split: {formatCents(parseDollarsToCents(amount)!)}</p>
        )}
      </div>

      {error && <p className="error">{error}</p>}

      <div className="actions">
        <button type="submit" disabled={submitting}>
          {submitting ? "Saving…" : initial ? "Save changes" : "Add expense"}
        </button>
        {onCancel && (
          <button type="button" className="secondary" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

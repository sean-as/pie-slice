import { useState } from "react";
import type { Member, Settlement } from "../domain/types";
import { parseDollarsToCents } from "../domain/money";
import type { AddSettlementInput } from "../services";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function SettlementForm({
  members,
  initial,
  onSubmit,
  onCancel,
}: {
  members: Member[];
  initial?: Settlement;
  onSubmit: (input: AddSettlementInput) => Promise<void>;
  onCancel?: () => void;
}) {
  const [fromMemberId, setFromMemberId] = useState(initial?.fromMemberId ?? members[0]?.id ?? "");
  const [toMemberId, setToMemberId] = useState(initial?.toMemberId ?? members[1]?.id ?? members[0]?.id ?? "");
  const [amount, setAmount] = useState(initial ? (initial.amountCents / 100).toFixed(2) : "");
  const [date, setDate] = useState(initial?.date ?? todayIso());
  const [method, setMethod] = useState(initial?.method ?? "");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const amountCents = parseDollarsToCents(amount);
    if (amountCents === null || amountCents <= 0) {
      setError("Enter a valid amount greater than $0.");
      return;
    }
    if (!fromMemberId || !toMemberId) {
      setError("Choose who paid and who received it.");
      return;
    }
    if (fromMemberId === toMemberId) {
      setError("Payer and recipient must be different people.");
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit({
        fromMemberId,
        toMemberId,
        amountCents,
        date,
        method: method.trim() || undefined,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the settlement.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="field">
        <label htmlFor="settlement-from">Paid by</label>
        <select id="settlement-from" value={fromMemberId} onChange={(e) => setFromMemberId(e.target.value)}>
          {members.map((m) => (
            <option key={m.id} value={m.id}>
              {m.displayName}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="settlement-to">Paid to</label>
        <select id="settlement-to" value={toMemberId} onChange={(e) => setToMemberId(e.target.value)}>
          {members.map((m) => (
            <option key={m.id} value={m.id}>
              {m.displayName}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="settlement-amount">Amount ($)</label>
        <input
          id="settlement-amount"
          type="text"
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="20.00"
        />
      </div>

      <div className="field">
        <label htmlFor="settlement-date">Date</label>
        <input id="settlement-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </div>

      <div className="field">
        <label htmlFor="settlement-method">Method (optional)</label>
        <input
          id="settlement-method"
          type="text"
          value={method}
          onChange={(e) => setMethod(e.target.value)}
          placeholder="Venmo, cash…"
        />
      </div>

      {error && <p className="error">{error}</p>}

      <div className="actions">
        <button type="submit" disabled={submitting}>
          {submitting ? "Saving…" : initial ? "Save changes" : "Record settlement"}
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

import { useState } from "react";
import type { BalancesResult, Member, Settlement } from "../domain/types";
import { formatCents } from "../domain/money";
import type { AddSettlementInput } from "../services";
import { ActionsMenu } from "./ActionsMenu";
import { SettlementForm } from "./SettlementForm";

/**
 * Who owes what, and where it gets settled: a suggested transfer can be
 * recorded (opening the form pre-filled with it), and every
 * recorded settlement is listed here so a mistaken one can be removed from
 * the place it was made. (Settlements also show in the group's ledger.)
 */
export function BalancesView({
  balances,
  members,
  settlements,
  currentUserId,
  onRecord,
  onUpdate,
  onDelete,
}: {
  balances: BalancesResult;
  members: Member[];
  settlements: Settlement[];
  currentUserId: string;
  onRecord: (input: AddSettlementInput) => Promise<void>;
  onUpdate: (settlementId: string, input: AddSettlementInput) => Promise<void>;
  onDelete: (settlementId: string) => Promise<void>;
}) {
  const nameById = new Map(members.map((m) => [m.id, m.displayName]));
  const name = (id: string) => nameById.get(id) ?? "Unknown";
  const [settlingIndex, setSettlingIndex] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function guarded(action: () => Promise<void>, fallback: string) {
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : fallback);
    }
  }

  return (
    <div>
      <h2>Balances</h2>
      <ul className="list">
        {balances.balances.map((b) => (
          <li key={b.memberId} className="card">
            <span>{name(b.memberId)}</span>
            <span
              className={
                b.netCents > 0 ? "balance-positive" : b.netCents < 0 ? "balance-negative" : "balance-zero"
              }
            >
              {b.netCents === 0
                ? "settled up"
                : b.netCents > 0
                  ? `is owed ${formatCents(b.netCents)}`
                  : `owes ${formatCents(-b.netCents)}`}
            </span>
          </li>
        ))}
      </ul>

      <h3>Settle up</h3>
      {balances.settleUp.length === 0 ? (
        <p className="meta">Everyone is settled up.</p>
      ) : (
        <ul className="list">
          {balances.settleUp.map((t, i) =>
            settlingIndex === i ? (
              <li key={i}>
                <SettlementForm
                  members={members}
                  prefill={t}
                  onCancel={() => setSettlingIndex(null)}
                  onSubmit={async (input) => {
                    await onRecord(input);
                    setSettlingIndex(null);
                  }}
                />
              </li>
            ) : (
            <li key={i} className="card">
              <span>
                {name(t.fromMemberId)} → {name(t.toMemberId)} · {formatCents(t.amountCents)}
              </span>
              <button type="button" className="secondary" onClick={() => setSettlingIndex(i)}>
                + Record settlement
              </button>
            </li>
            )
          )}
        </ul>
      )}
      {error && <p className="error">{error}</p>}

      {settlements.length > 0 && (
        <>
          <h3>Recorded settlements</h3>
          <ul className="list">
            {settlements.map((s) =>
              editingId === s.id ? (
                <li key={s.id}>
                  <SettlementForm
                    members={members}
                    initial={s}
                    onCancel={() => setEditingId(null)}
                    onSubmit={async (input) => {
                      await onUpdate(s.id, input);
                      setEditingId(null);
                    }}
                  />
                </li>
              ) : (
                <li key={s.id} className="card">
                  <span>
                    {name(s.fromMemberId)} paid {name(s.toMemberId)} {formatCents(s.amountCents)}
                    <br />
                    <span className="meta">
                      {s.date}
                      {s.method ? ` · ${s.method}` : ""}
                    </span>
                  </span>
                  {s.createdByUserId === currentUserId && (
                    <ActionsMenu
                      onEdit={() => setEditingId(s.id)}
                      onDelete={() => guarded(() => onDelete(s.id), "Could not remove that settlement.")}
                    />
                  )}
                </li>
              )
            )}
          </ul>
        </>
      )}
    </div>
  );
}

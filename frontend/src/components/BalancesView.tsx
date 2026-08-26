import type { BalancesResult, Member } from "../domain/types";
import { formatCents } from "../domain/money";

export function BalancesView({ balances, members }: { balances: BalancesResult; members: Member[] }) {
  const nameById = new Map(members.map((m) => [m.id, m.displayName]));

  return (
    <div>
      <h2>Balances</h2>
      <ul className="list">
        {balances.balances.map((b) => (
          <li key={b.memberId} className="card">
            <span>{nameById.get(b.memberId) ?? "Unknown"}</span>
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

      <h2>Settle up</h2>
      {balances.settleUp.length === 0 ? (
        <p className="meta">Everyone is settled up.</p>
      ) : (
        <ul className="list">
          {balances.settleUp.map((t, i) => (
            <li key={i} className="card">
              <span>
                {nameById.get(t.fromMemberId) ?? "Unknown"} → {nameById.get(t.toMemberId) ?? "Unknown"}
              </span>
              <span>{formatCents(t.amountCents)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

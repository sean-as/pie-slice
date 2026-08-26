import type { Split } from "./types";

export class SplitValidationError extends Error {}

type Weighted = { memberId: string; weight: number };

/**
 * Distributes amountCents proportionally to weights using the largest-remainder
 * method: floor each share, then hand out the leftover cents one at a time to
 * whoever's fractional share was largest (ties broken by list order). This is
 * deterministic and always sums to exactly amountCents.
 */
function distributeProportionally(amountCents: number, weighted: Weighted[]): Split[] {
  const totalWeight = weighted.reduce((sum, w) => sum + w.weight, 0);
  if (totalWeight <= 0) {
    throw new SplitValidationError("Total weight must be positive.");
  }

  const raw = weighted.map((w) => (amountCents * w.weight) / totalWeight);
  const floors = raw.map(Math.floor);
  const distributed = floors.reduce((a, b) => a + b, 0);
  const remainder = amountCents - distributed;

  const byFraction = raw
    .map((r, i) => ({ i, frac: r - floors[i] }))
    .sort((a, b) => b.frac - a.frac || a.i - b.i);

  const result = floors.slice();
  for (let k = 0; k < remainder; k++) {
    result[byFraction[k].i] += 1;
  }

  return weighted.map((w, i) => ({ memberId: w.memberId, amountCents: result[i] }));
}

export function splitEqual(amountCents: number, memberIds: string[]): Split[] {
  if (memberIds.length === 0) {
    throw new SplitValidationError("Select at least one member to split with.");
  }
  return distributeProportionally(
    amountCents,
    memberIds.map((memberId) => ({ memberId, weight: 1 }))
  );
}

export function splitExact(amountCents: number, amounts: Split[]): Split[] {
  if (amounts.length === 0) {
    throw new SplitValidationError("Select at least one member to split with.");
  }
  const sum = amounts.reduce((total, s) => total + s.amountCents, 0);
  if (sum !== amountCents) {
    throw new SplitValidationError(
      `Exact amounts sum to ${sum} cents but the expense total is ${amountCents} cents.`
    );
  }
  return amounts;
}

export function splitPercent(
  amountCents: number,
  percentages: { memberId: string; percent: number }[]
): Split[] {
  if (percentages.length === 0) {
    throw new SplitValidationError("Select at least one member to split with.");
  }
  const sum = percentages.reduce((total, p) => total + p.percent, 0);
  if (Math.abs(sum - 100) > 0.01) {
    throw new SplitValidationError(`Percentages sum to ${sum}%, but must sum to 100%.`);
  }
  return distributeProportionally(
    amountCents,
    percentages.map((p) => ({ memberId: p.memberId, weight: p.percent }))
  );
}

export function splitShares(
  amountCents: number,
  shares: { memberId: string; shares: number }[]
): Split[] {
  if (shares.length === 0) {
    throw new SplitValidationError("Select at least one member to split with.");
  }
  for (const s of shares) {
    if (!Number.isInteger(s.shares) || s.shares <= 0) {
      throw new SplitValidationError("Shares must be positive whole numbers.");
    }
  }
  return distributeProportionally(
    amountCents,
    shares.map((s) => ({ memberId: s.memberId, weight: s.shares }))
  );
}

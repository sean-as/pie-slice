export function formatCents(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  const dollars = Math.floor(abs / 100);
  const remainder = String(abs % 100).padStart(2, "0");
  return `${sign}$${dollars}.${remainder}`;
}

/**
 * Parses a user-typed dollar string ("12.3", "12.34", "12") into integer
 * cents without floating-point math. Returns null if the input isn't a
 * valid non-negative amount.
 */
export function parseDollarsToCents(input: string): number | null {
  const trimmed = input.trim();
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) {
    return null;
  }
  const [wholePart, fractionPart = ""] = trimmed.split(".");
  const cents = fractionPart.padEnd(2, "0");
  return Number(wholePart) * 100 + Number(cents);
}

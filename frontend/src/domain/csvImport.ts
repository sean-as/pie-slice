/**
 * CSV parsing and merchant normalization — ported 1:1 from
 * backend/app/csv_import.py so the mock service behaves identically to the
 * real backend. Pure functions only: no service, no storage.
 *
 * The real backend does this parsing for real uploads; this exists so the
 * no-backend mock mode is a faithful stand-in.
 */

export const MAX_UPLOAD_BYTES = 1_000_000;
export const MAX_ROWS = 2_000;

const REQUIRED_COLUMNS = ["date", "description", "amount"] as const;
const FORMULA_PREFIXES = ["=", "+", "-", "@"];

export class CsvFormatError extends Error {}

export type ParsedRow = {
  date: string;
  description: string;
  amountCents: number;
};

export type ParsedSkip = {
  line: number;
  reason: string;
};

export type ParseResult = {
  rows: ParsedRow[];
  skipped: ParsedSkip[];
};

/**
 * Case-folded and whitespace-collapsed. Deliberately literal: the spec
 * rules out fuzzy matching, so "AMAZON MKTPLACE" and "AMAZON.COM*A1B2C"
 * stay different merchants.
 */
export function normalizeMerchant(description: string): string {
  return description.trim().replace(/\s+/g, " ").toLowerCase();
}

/**
 * Prefixes a leading =, +, - or @ with an apostrophe so the text can never
 * be evaluated as a formula by a spreadsheet downstream.
 */
export function defuseFormula(description: string): string {
  const trimmed = description.trim();
  return FORMULA_PREFIXES.some((p) => trimmed.startsWith(p)) ? `'${trimmed}` : trimmed;
}

/** Identifies an already-imported transaction (see the backend's dedupe rule). */
export function fingerprint(
  groupId: string,
  uploaderUserId: string,
  date: string,
  description: string,
  amountCents: number
): string {
  return [groupId, uploaderUserId, date, normalizeMerchant(description), String(amountCents)].join(
    ""
  );
}

/**
 * Minimal RFC-4180 splitter: handles quoted fields and doubled quotes,
 * which is all a bank export needs (amounts like "1,200.00" are quoted).
 */
function splitCsvLine(line: string): string[] {
  const cells: string[] = [];
  let cell = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    if (inQuotes) {
      if (char === '"') {
        if (line[i + 1] === '"') {
          cell += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        cell += char;
      }
    } else if (char === '"') {
      inQuotes = true;
    } else if (char === ",") {
      cells.push(cell);
      cell = "";
    } else {
      cell += char;
    }
  }
  cells.push(cell);
  return cells;
}

/**
 * Dollars to integer cents without floating point: the decimal string is
 * split and padded, so 1234.56 can never become 123455.99999.
 */
function parseAmountCents(raw: string): number {
  const cleaned = raw.trim().replace(/[$,]/g, "");
  if (!cleaned) throw new Error("missing amount");

  const match = /^(-?)(\d*)(?:\.(\d+))?$/.exec(cleaned);
  if (!match || (!match[2] && !match[3])) throw new Error(`could not read amount '${raw.trim()}'`);

  const [, sign, whole, fraction = ""] = match;
  if (fraction.length > 2) throw new Error(`amount '${raw.trim()}' is more precise than whole cents`);

  const cents = Number(whole || "0") * 100 + Number(fraction.padEnd(2, "0") || "0");
  return sign === "-" ? -cents : cents;
}

function isIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().startsWith(value);
}

/**
 * Returns the positive-amount rows that parsed, plus a per-line report of
 * what was skipped. A bad row never fails the whole upload; only broken
 * file-level structure does.
 */
export function parseCsv(text: string): ParseResult {
  if (text.length > MAX_UPLOAD_BYTES) {
    throw new CsvFormatError("That file is too large — please upload a statement under 1 MB.");
  }

  const lines = text.replace(/^﻿/, "").split(/\r?\n/);
  if (lines.length === 0 || !lines[0].trim()) {
    throw new CsvFormatError("That file is empty.");
  }

  const header = splitCsvLine(lines[0]).map((name) => name.trim().toLowerCase());
  const missing = REQUIRED_COLUMNS.filter((column) => !header.includes(column));
  if (missing.length > 0) {
    throw new CsvFormatError(
      `The file needs date, description and amount columns — missing: ${missing.join(", ")}.`
    );
  }

  const dateAt = header.indexOf("date");
  const descriptionAt = header.indexOf("description");
  const amountAt = header.indexOf("amount");

  const rows: ParsedRow[] = [];
  const skipped: ParsedSkip[] = [];

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;
    if (rows.length + skipped.length >= MAX_ROWS) {
      throw new CsvFormatError(`That file has more than ${MAX_ROWS} rows — please split it up.`);
    }

    const lineNumber = i + 1;
    const cells = splitCsvLine(line);

    try {
      if (Math.max(dateAt, descriptionAt, amountAt) >= cells.length) {
        throw new Error("row has fewer columns than the header");
      }
      const date = cells[dateAt].trim();
      if (!isIsoDate(date)) throw new Error(`could not read date '${date}'`);

      const description = defuseFormula(cells[descriptionAt]);
      if (!description) throw new Error("missing description");

      const amountCents = parseAmountCents(cells[amountAt]);

      // Payments, credits and refunds aren't expenses — dropped silently,
      // not even shown for review.
      if (amountCents <= 0) continue;

      rows.push({ date, description, amountCents });
    } catch (err) {
      skipped.push({ line: lineNumber, reason: err instanceof Error ? err.message : "unreadable row" });
    }
  }

  return { rows, skipped };
}

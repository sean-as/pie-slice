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

/** Header names recognized without being told, when a file happens to use them. */
export const DEFAULT_COLUMN_NAMES = {
  date: "date",
  description: "description",
  amount: "amount",
} as const;

/** How many data rows to show so the user can check their mapping. */
export const SAMPLE_ROWS = 3;

const FORMULA_PREFIXES = ["=", "+", "-", "@"];
const SLASH_DATE = /^\d{1,2}\/\d{1,2}\/\d{4}$/;

export type DateFormat = "iso" | "mdy" | "dmy";
export type AmountSign = "positive_is_charge" | "negative_is_charge";

const DATE_FORMAT_LABELS: Record<DateFormat, string> = {
  iso: "YYYY-MM-DD",
  mdy: "MM/DD/YYYY",
  dmy: "DD/MM/YYYY",
};

export class CsvFormatError extends Error {}

/** How to read one bank's export. Column values are header names. */
export type ColumnMapping = {
  dateColumn: string;
  descriptionColumn: string;
  amountColumn: string;
  dateFormat: DateFormat;
  amountSign: AmountSign;
};

/**
 * What a file looks like before any transaction is read from it — enough
 * for the user to confirm or correct how it should be read.
 */
export type FileShape = {
  columns: string[];
  sampleRows: Record<string, string>[];
  suggested: ColumnMapping;
  /** Roles the guess couldn't fill in; the user must choose these. */
  unresolved: string[];
  /** True when MM/DD vs DD/MM can't be told apart from this file's data. */
  dateFormatAmbiguous: boolean;
};

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
 * Parses in the chosen format only — guessing per row would let one file
 * silently mix MM/DD and DD/MM. Returns an ISO string, since that's what
 * the rest of the app passes around.
 */
function parseDate(raw: string, dateFormat: DateFormat): string {
  const text = raw.trim();
  const fail = () => {
    throw new Error(`could not read date '${text}' — expected ${DATE_FORMAT_LABELS[dateFormat]}`);
  };

  let year: number;
  let month: number;
  let day: number;

  if (dateFormat === "iso") {
    if (!isIsoDate(text)) fail();
    return text;
  }

  const match = SLASH_DATE.exec(text);
  if (!match) fail();
  const [first, second, rest] = text.split("/");
  year = Number(rest);
  if (dateFormat === "mdy") {
    month = Number(first);
    day = Number(second);
  } else {
    day = Number(first);
    month = Number(second);
  }

  const iso = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  // Catches 02/31 and month 25 — Date would silently roll them over.
  if (!isIsoDate(iso)) fail();
  return iso;
}

/**
 * Returns the positive-amount rows that parsed, plus a per-line report of
 * what was skipped. A bad row never fails the whole upload; only broken
 * file-level structure does.
 */
type Record_ = { line: number; cells: string[] };

/**
 * Decodes the file into its header and data records, each paired with its
 * real line number — blank lines are dropped but still counted, so a skip
 * report points at the line the user sees.
 */
function read(text: string): { header: string[]; records: Record_[] } {
  if (text.length > MAX_UPLOAD_BYTES) {
    throw new CsvFormatError("That file is too large — please upload a statement under 1 MB.");
  }

  const lines = text.replace(/^﻿/, "").split(/\r?\n/);
  if (lines.length === 0 || !lines[0].trim()) {
    throw new CsvFormatError("That file is empty.");
  }

  const header = splitCsvLine(lines[0]).map((name) => name.trim());
  if (!header.some(Boolean)) {
    throw new CsvFormatError("That file has no header row naming its columns.");
  }

  const records: Record_[] = [];
  for (let i = 1; i < lines.length; i++) {
    if (!lines[i].trim()) continue;
    records.push({ line: i + 1, cells: splitCsvLine(lines[i]) });
  }
  if (records.length > MAX_ROWS) {
    throw new CsvFormatError(`That file has more than ${MAX_ROWS} rows — please split it up.`);
  }

  return { header, records };
}

/** Header names are matched case-insensitively but are otherwise literal. */
function columnIndex(header: string[], column: string, role: string): number {
  const wanted = column.trim().toLowerCase();
  const at = header.findIndex((name) => name.toLowerCase() === wanted);
  if (at === -1) {
    throw new CsvFormatError(`This file has no column named '${column}' to use as the ${role}.`);
  }
  return at;
}

/**
 * MM/DD vs DD/MM is decidable only if some row has a part > 12. Returns
 * null when every row is ambiguous — the caller must ask.
 */
function inferSlashOrder(values: string[]): DateFormat | null {
  const firstOver12 = values.some((v) => Number(v.split("/")[0]) > 12);
  const secondOver12 = values.some((v) => Number(v.split("/")[1]) > 12);
  if (firstOver12 && !secondOver12) return "dmy";
  if (secondOver12 && !firstOver12) return "mdy";
  return null;
}

/**
 * Which format a set of date strings is in, or null when it can't be known
 * for certain — either they aren't all one recognizable shape, or they're
 * slash dates whose day parts are all <= 12 (see inferSlashOrder).
 */
export function detectDateFormat(values: string[]): DateFormat | null {
  if (values.length === 0) return null;
  if (values.every(isIsoDate)) return "iso";
  if (values.every((v) => SLASH_DATE.test(v))) return inferSlashOrder(values);
  return null;
}

/**
 * Works out what it safely can about a file: column names, sample rows, and
 * a suggested mapping. `previous` (the user's last mapping for this group)
 * wins wherever its columns still exist.
 *
 * Deliberately does not guess between MM/DD/YYYY and DD/MM/YYYY: for days
 * <= 12 they're indistinguishable, and picking wrong would silently import
 * transactions on the wrong dates.
 */
export function detectMapping(text: string, previous?: ColumnMapping | null): FileShape {
  const { header, records } = read(text);

  const byLower = new Map(header.filter(Boolean).map((name) => [name.toLowerCase(), name]));
  const suggested: Record<string, string> = {};
  const unresolved: string[] = [];

  for (const role of ["date", "description", "amount"] as const) {
    const fromPrevious = previous?.[`${role}Column` as const];
    if (fromPrevious && byLower.has(fromPrevious.toLowerCase())) {
      suggested[role] = byLower.get(fromPrevious.toLowerCase())!;
    } else if (byLower.has(DEFAULT_COLUMN_NAMES[role])) {
      suggested[role] = byLower.get(DEFAULT_COLUMN_NAMES[role])!;
    } else {
      // No safe guess — the user picks. The first column is a placeholder
      // so the form has something selected; `unresolved` flags it.
      suggested[role] = header[0] ?? "";
      unresolved.push(role);
    }
  }

  const sampleRows = records.slice(0, SAMPLE_ROWS).map(({ cells }) =>
    Object.fromEntries(header.map((name, i) => [name, cells[i] ?? ""]))
  );

  let dateFormat: DateFormat = previous?.dateFormat ?? "iso";
  let dateFormatAmbiguous = false;

  if (!unresolved.includes("date")) {
    const dateAt = columnIndex(header, suggested.date, "date");
    const values = records
      .slice(0, 20)
      .map(({ cells }) => (cells[dateAt] ?? "").trim())
      .filter(Boolean);

    if (values.length > 0 && values.every(isIsoDate)) {
      dateFormat = "iso";
    } else if (values.length > 0 && values.every((v) => SLASH_DATE.test(v))) {
      const inferred = inferSlashOrder(values);
      if (inferred) {
        dateFormat = inferred;
      } else {
        dateFormat = previous && previous.dateFormat !== "iso" ? previous.dateFormat : "mdy";
        dateFormatAmbiguous = true;
      }
    }
  }

  return {
    columns: header,
    sampleRows,
    suggested: {
      dateColumn: suggested.date,
      descriptionColumn: suggested.description,
      amountColumn: suggested.amount,
      dateFormat,
      amountSign: previous?.amountSign ?? "positive_is_charge",
    },
    unresolved,
    dateFormatAmbiguous,
  };
}

/**
 * Reads the file through `mapping` and returns the rows that are charges,
 * plus a per-line report of what was skipped. Unparseable rows never fail
 * the whole upload; only broken file-level structure or an unusable
 * mapping does. With no mapping, falls back to the conventional headers.
 */
export function parseCsv(text: string, mapping?: ColumnMapping | null): ParseResult {
  const { header, records } = read(text);

  const effective: ColumnMapping = mapping ?? {
    dateColumn: DEFAULT_COLUMN_NAMES.date,
    descriptionColumn: DEFAULT_COLUMN_NAMES.description,
    amountColumn: DEFAULT_COLUMN_NAMES.amount,
    dateFormat: "iso",
    amountSign: "positive_is_charge",
  };

  const dateAt = columnIndex(header, effective.dateColumn, "date");
  const descriptionAt = columnIndex(header, effective.descriptionColumn, "description");
  const amountAt = columnIndex(header, effective.amountColumn, "amount");

  // A charge is whichever sign the user says it is; the other side of the
  // ledger (payments, credits, refunds) is what gets dropped.
  const chargeIsNegative = effective.amountSign === "negative_is_charge";

  const rows: ParsedRow[] = [];
  const skipped: ParsedSkip[] = [];

  for (const { line, cells } of records) {
    try {
      if (Math.max(dateAt, descriptionAt, amountAt) >= cells.length) {
        throw new Error("row has fewer columns than the header");
      }

      const date = parseDate(cells[dateAt], effective.dateFormat);
      const description = defuseFormula(cells[descriptionAt]);
      if (!description) throw new Error("missing description");

      let amountCents = parseAmountCents(cells[amountAt]);
      if (chargeIsNegative) amountCents = -amountCents;

      // The other side of the ledger isn't an expense — dropped silently,
      // not even shown for review.
      if (amountCents <= 0) continue;

      rows.push({ date, description, amountCents });
    } catch (err) {
      skipped.push({ line, reason: err instanceof Error ? err.message : "unreadable row" });
    }
  }

  return { rows, skipped };
}

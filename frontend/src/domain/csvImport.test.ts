import { describe, expect, it } from "vitest";
import type { ColumnMapping } from "./csvImport";
import {
  CsvFormatError,
  defuseFormula,
  detectDateFormat,
  detectMapping,
  normalizeMerchant,
  parseCsv,
} from "./csvImport";

const csv = (...lines: string[]) => ["date,description,amount", ...lines].join("\n");

describe("parseCsv", () => {
  it("parses a basic file", () => {
    const result = parseCsv(csv("2026-08-26,Comcast,79.99"));
    expect(result.skipped).toEqual([]);
    expect(result.rows).toEqual([
      { date: "2026-08-26", description: "Comcast", amountCents: 7999, category: null },
    ]);
  });

  it("matches headers case-insensitively and in any order", () => {
    const result = parseCsv(["Amount, DESCRIPTION ,Date", "42.50,Shell,2026-08-01"].join("\n"));
    expect(result.rows).toEqual([
      { date: "2026-08-01", description: "Shell", amountCents: 4250, category: null },
    ]);
  });

  it("ignores extra columns", () => {
    const result = parseCsv(
      ["date,description,amount,category", "2026-08-26,Comcast,79.99,Utilities"].join("\n")
    );
    expect(result.rows).toHaveLength(1);
  });

  it("rejects a file missing a required column", () => {
    expect(() => parseCsv("date,description\n2026-08-26,Comcast")).toThrow(CsvFormatError);
  });

  it("rejects an empty file", () => {
    expect(() => parseCsv("")).toThrow(CsvFormatError);
  });

  it("drops zero and negative rows silently", () => {
    const result = parseCsv(
      csv("2026-08-26,Comcast,79.99", "2026-08-27,Payment,-250.00", "2026-08-28,Adjustment,0.00")
    );
    expect(result.rows.map((r) => r.description)).toEqual(["Comcast"]);
    // Dropped, not "skipped" — the user never sees them.
    expect(result.skipped).toEqual([]);
  });

  it("reports unparseable rows without failing the file", () => {
    const result = parseCsv(
      csv("not-a-date,Comcast,79.99", "2026-08-27,Shell,abc", "2026-08-28,Trader Joes,25.00")
    );
    expect(result.rows.map((r) => r.description)).toEqual(["Trader Joes"]);
    expect(result.skipped.map((s) => s.line)).toEqual([2, 3]);
  });

  it("skips a row with too few columns", () => {
    const result = parseCsv(csv("2026-08-26,Comcast"));
    expect(result.rows).toEqual([]);
    expect(result.skipped).toHaveLength(1);
  });

  it("ignores blank lines", () => {
    const result = parseCsv(csv("", "2026-08-26,Comcast,79.99", ""));
    expect(result.rows).toHaveLength(1);
    expect(result.skipped).toEqual([]);
  });

  it("converts dollars to exact cents without float drift", () => {
    const result = parseCsv(csv("2026-08-26,A,0.10", "2026-08-26,B,0.20", "2026-08-26,C,1234.56"));
    expect(result.rows.map((r) => r.amountCents)).toEqual([10, 20, 123456]);
  });

  it("handles quoted amounts with currency symbols and separators", () => {
    const result = parseCsv(csv('2026-08-26,Rent,"$1,200.00"'));
    expect(result.rows[0].amountCents).toBe(120000);
  });

  it("skips sub-cent precision rather than rounding it", () => {
    const result = parseCsv(csv("2026-08-26,Odd,1.005"));
    expect(result.rows).toEqual([]);
    expect(result.skipped).toHaveLength(1);
  });

  it("rejects an out-of-range date", () => {
    const result = parseCsv(csv("2026-02-31,Comcast,79.99"));
    expect(result.rows).toEqual([]);
  });

  it("defuses formula-looking descriptions", () => {
    const result = parseCsv(csv("2026-08-26,=cmd|'/c calc',10.00"));
    expect(result.rows[0].description.startsWith("'=")).toBe(true);
  });
});

describe("defuseFormula", () => {
  it.each(["=1+1", "+SUM(A1)", "-2+3", "@import"])("defuses %s", (raw) => {
    expect(defuseFormula(raw).startsWith("'")).toBe(true);
  });

  it("leaves ordinary text alone", () => {
    expect(defuseFormula("  Comcast  ")).toBe("Comcast");
  });
});

describe("normalizeMerchant", () => {
  it("ignores case and spacing", () => {
    expect(normalizeMerchant("  COMCAST   Cable ")).toBe(normalizeMerchant("comcast cable"));
  });

  it("keeps genuinely different merchants apart", () => {
    // The spec rules out fuzzy matching — these must not collapse.
    expect(normalizeMerchant("AMAZON MKTPLACE")).not.toBe(normalizeMerchant("AMAZON.COM*A1B2C"));
  });
});

const CHASE = [
  "Transaction Date,Post Date,Merchant,Debit,Category",
  "2026-08-26,2026-08-27,Comcast,79.99,Utilities",
].join("\n");

const mapping = (overrides: Partial<ColumnMapping> = {}): ColumnMapping => ({
  dateColumn: "date",
  descriptionColumn: "description",
  amountColumn: "amount",
  dateFormat: "iso",
  amountSign: "positive_is_charge",
  ...overrides,
});

describe("column mapping", () => {
  it("reads arbitrary column names", () => {
    const result = parseCsv(
      CHASE,
      mapping({ dateColumn: "Transaction Date", descriptionColumn: "Merchant", amountColumn: "Debit" })
    );
    expect(result.rows).toEqual([
      { date: "2026-08-26", description: "Comcast", amountCents: 7999, category: null },
    ]);
  });

  it("uses the mapped date column, not another date-looking one", () => {
    const result = parseCsv(
      CHASE,
      mapping({ dateColumn: "Post Date", descriptionColumn: "Merchant", amountColumn: "Debit" })
    );
    expect(result.rows[0].date).toBe("2026-08-27");
  });

  it("matches column names case-insensitively", () => {
    const result = parseCsv(
      CHASE,
      mapping({ dateColumn: "transaction date", descriptionColumn: "MERCHANT", amountColumn: "debit" })
    );
    expect(result.rows).toHaveLength(1);
  });

  it("rejects a column the file doesn't have", () => {
    expect(() =>
      parseCsv(CHASE, mapping({ dateColumn: "Nope", descriptionColumn: "Merchant", amountColumn: "Debit" }))
    ).toThrow(CsvFormatError);
  });
});

describe("amount sign", () => {
  const negativeBank = csv("2026-08-26,Comcast,-79.99", "2026-08-27,Payment,500.00");

  it("treats negatives as charges when told to", () => {
    const result = parseCsv(negativeBank, mapping({ amountSign: "negative_is_charge" }));
    expect(result.rows.map((r) => [r.description, r.amountCents])).toEqual([["Comcast", 7999]]);
  });

  it("finds the other side of the ledger under the wrong convention", () => {
    const result = parseCsv(negativeBank, mapping({ amountSign: "positive_is_charge" }));
    expect(result.rows.map((r) => r.description)).toEqual(["Payment"]);
  });
});

describe("date formats", () => {
  it("reads US order", () => {
    const result = parseCsv(csv("09/01/2026,Comcast,79.99"), mapping({ dateFormat: "mdy" }));
    expect(result.rows[0].date).toBe("2026-09-01");
  });

  it("reads the same string differently in EU order", () => {
    const result = parseCsv(csv("09/01/2026,Comcast,79.99"), mapping({ dateFormat: "dmy" }));
    expect(result.rows[0].date).toBe("2026-01-09");
  });

  it("skips rather than guessing when the format doesn't match", () => {
    const result = parseCsv(csv("09/01/2026,Comcast,79.99"), mapping({ dateFormat: "iso" }));
    expect(result.rows).toEqual([]);
    expect(result.skipped[0].reason).toContain("YYYY-MM-DD");
  });

  it("rejects an impossible date under the chosen format", () => {
    const result = parseCsv(csv("25/01/2026,Comcast,79.99"), mapping({ dateFormat: "mdy" }));
    expect(result.rows).toEqual([]);
    expect(result.skipped).toHaveLength(1);
  });

  it("rejects a rolled-over day like Feb 31", () => {
    const result = parseCsv(csv("02/31/2026,Comcast,79.99"), mapping({ dateFormat: "mdy" }));
    expect(result.rows).toEqual([]);
  });
});

describe("detectMapping", () => {
  it("recognizes conventional headers", () => {
    const shape = detectMapping(csv("2026-08-26,Comcast,79.99"));
    expect(shape.unresolved).toEqual([]);
    expect(shape.suggested.dateColumn).toBe("date");
    expect(shape.dateFormatAmbiguous).toBe(false);
  });

  it("reports columns it can't guess", () => {
    const shape = detectMapping(CHASE);
    expect(shape.unresolved.sort()).toEqual(["amount", "date", "description"]);
    expect(shape.columns).toContain("Merchant");
  });

  it("returns sample rows keyed by column", () => {
    const shape = detectMapping(csv("2026-08-26,Comcast,79.99"));
    expect(shape.sampleRows[0]).toEqual({ date: "2026-08-26", description: "Comcast", amount: "79.99" });
  });

  it("infers US dates when a day exceeds twelve", () => {
    const shape = detectMapping(csv("09/25/2026,Comcast,79.99"));
    expect(shape.suggested.dateFormat).toBe("mdy");
    expect(shape.dateFormatAmbiguous).toBe(false);
  });

  it("infers EU dates when the first part exceeds twelve", () => {
    const shape = detectMapping(csv("25/09/2026,Comcast,79.99"));
    expect(shape.suggested.dateFormat).toBe("dmy");
  });

  it("flags genuinely ambiguous slash dates instead of picking", () => {
    const shape = detectMapping(csv("09/01/2026,Comcast,79.99"));
    expect(shape.dateFormatAmbiguous).toBe(true);
  });

  it("prefers a previous mapping whose columns still exist", () => {
    const previous = mapping({
      dateColumn: "Transaction Date",
      descriptionColumn: "Merchant",
      amountColumn: "Debit",
      amountSign: "negative_is_charge",
    });
    const shape = detectMapping(CHASE, previous);
    expect(shape.unresolved).toEqual([]);
    expect(shape.suggested.amountSign).toBe("negative_is_charge");
  });

  it("ignores a previous mapping whose columns are gone", () => {
    const previous = mapping({ dateColumn: "Gone", descriptionColumn: "Gone", amountColumn: "Gone" });
    const shape = detectMapping(csv("2026-08-26,Comcast,79.99"), previous);
    expect(shape.unresolved).toEqual([]);
    expect(shape.suggested.dateColumn).toBe("date");
  });
});

describe("line numbers", () => {
  it("points at the real line despite blank lines", () => {
    const result = parseCsv(csv("2026-08-26,Comcast,79.99", "", "bad,Shell,40.00"));
    expect(result.skipped.map((s) => s.line)).toEqual([4]);
  });
});

describe("detectDateFormat", () => {
  it("recognizes ISO", () => {
    expect(detectDateFormat(["2026-08-26", "2026-08-27"])).toBe("iso");
  });

  it("resolves slash order from a day over twelve", () => {
    expect(detectDateFormat(["09/25/2026"])).toBe("mdy");
    expect(detectDateFormat(["25/09/2026"])).toBe("dmy");
  });

  it("returns null when slash order is a coin flip", () => {
    expect(detectDateFormat(["09/01/2026", "10/02/2026"])).toBeNull();
  });

  it("returns null for unrecognizable or empty values", () => {
    expect(detectDateFormat(["Comcast"])).toBeNull();
    expect(detectDateFormat([])).toBeNull();
  });
});

describe("robustness", () => {
  // Each of these crashed the server before, which the browser reported as
  // an opaque "Failed to fetch" rather than anything actionable.
  it.each(["Infinity", "-Infinity", "NaN", "1e400", "9".repeat(400) + ".00"])(
    "skips the row for a pathological amount (%s)",
    (value) => {
      const result = parseCsv(csv(`2026-08-26,X,${value}`));
      expect(result.rows).toEqual([]);
      expect(result.skipped).toHaveLength(1);
    }
  );

  it("skips an implausibly large amount", () => {
    const result = parseCsv(csv("2026-08-26,X,999999999999.00"));
    expect(result.skipped[0].reason).toContain("implausibly large");
  });

  it("reads accounting parentheses as negative", () => {
    const charge = parseCsv(csv("2026-08-26,X,(79.99)"), mapping({ amountSign: "negative_is_charge" }));
    expect(charge.rows[0].amountCents).toBe(7999);
    // Under positive-is-charge the same row is the other side of the ledger.
    expect(parseCsv(csv("2026-08-26,X,(79.99)")).rows).toEqual([]);
  });

  it("tolerates spaces inside amounts", () => {
    expect(parseCsv(csv("2026-08-26,X,1 234.56")).rows[0].amountCents).toBe(123456);
  });
});

describe("delimiters", () => {
  it("reads semicolons", () => {
    const result = parseCsv("date;description;amount\n2026-08-26;Comcast;79.99");
    expect(result.rows[0].description).toBe("Comcast");
  });

  it("reads tabs", () => {
    const result = parseCsv("date\tdescription\tamount\n2026-08-26\tComcast\t79.99");
    expect(result.rows[0].amountCents).toBe(7999);
  });

  it("reads pipes", () => {
    const result = parseCsv("date|description|amount\n2026-08-26|Comcast|79.99");
    expect(result.rows[0].amountCents).toBe(7999);
  });

  it("keeps commas when a quoted description contains semicolons", () => {
    const result = parseCsv('date,description,amount\n2026-08-26,"A; B; C",79.99');
    expect(result.rows[0].description).toBe("A; B; C");
  });

  it("detects the delimiter in detectMapping too", () => {
    const shape = detectMapping("date;description;amount\n2026-08-26;Comcast;79.99");
    expect(shape.columns).toEqual(["date", "description", "amount"]);
    expect(shape.unresolved).toEqual([]);
  });
});

describe("category", () => {
  const withCategory = ["date,description,amount,category", "2026-08-26,Comcast,79.99,Utilities"].join("\n");

  it("is suggested when the file has one", () => {
    const shape = detectMapping(withCategory);
    expect(shape.suggested.categoryColumn).toBe("category");
    // Suggested but optional — never blocks the user.
    expect(shape.unresolved).toEqual([]);
  });

  it("is null when the file has none", () => {
    const shape = detectMapping(csv("2026-08-26,Comcast,79.99"));
    expect(shape.suggested.categoryColumn).toBeNull();
    expect(shape.unresolved).toEqual([]);
  });

  it("is read when mapped", () => {
    const result = parseCsv(withCategory, mapping({ categoryColumn: "category" }));
    expect(result.rows[0].category).toBe("Utilities");
  });

  it("is left empty when not mapped", () => {
    const result = parseCsv(withCategory, mapping());
    expect(result.rows[0].category).toBeNull();
  });

  it("treats a blank cell as no category", () => {
    const result = parseCsv(
      ["date,description,amount,category", "2026-08-26,Comcast,79.99,"].join("\n"),
      mapping({ categoryColumn: "category" })
    );
    expect(result.rows[0].category).toBeNull();
  });

  it("rejects a category column the file doesn't have", () => {
    expect(() => parseCsv(withCategory, mapping({ categoryColumn: "Nope" }))).toThrow(CsvFormatError);
  });

  it("prefers a previously mapped category column", () => {
    const file = ["date,description,amount,Bucket", "2026-08-26,Comcast,79.99,Utilities"].join("\n");
    const shape = detectMapping(file, mapping({ categoryColumn: "Bucket" }));
    expect(shape.suggested.categoryColumn).toBe("Bucket");
  });
});

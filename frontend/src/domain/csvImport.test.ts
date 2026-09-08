import { describe, expect, it } from "vitest";
import { CsvFormatError, defuseFormula, normalizeMerchant, parseCsv } from "./csvImport";

const csv = (...lines: string[]) => ["date,description,amount", ...lines].join("\n");

describe("parseCsv", () => {
  it("parses a basic file", () => {
    const result = parseCsv(csv("2026-08-26,Comcast,79.99"));
    expect(result.skipped).toEqual([]);
    expect(result.rows).toEqual([{ date: "2026-08-26", description: "Comcast", amountCents: 7999 }]);
  });

  it("matches headers case-insensitively and in any order", () => {
    const result = parseCsv(["Amount, DESCRIPTION ,Date", "42.50,Shell,2026-08-01"].join("\n"));
    expect(result.rows).toEqual([{ date: "2026-08-01", description: "Shell", amountCents: 4250 }]);
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

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ColumnMapping } from "../domain/types";
import { HttpExpenseService } from "./httpService";

/**
 * Wire-format tests for the HTTP service.
 *
 * This layer is a translation step — domain object in, request body out —
 * and a field dropped here fails silently: the server just sees a request
 * that didn't ask for anything, and returns a perfectly valid response.
 * That is exactly how a mapped CSV category went missing, so the round trip
 * is worth asserting field by field.
 */

const service = new HttpExpenseService();

let fetchMock: ReturnType<typeof vi.fn>;

/** Minimal localStorage — the tests run in node, which has none. */
function stubStorage() {
  const store = new Map<string, string>();
  return {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
  };
}

function jsonResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    text: () => Promise.resolve(JSON.stringify(body)),
  } as unknown as Response;
}

/** The FormData the service actually sent, as plain entries. */
function sentFormData(): Record<string, string> {
  const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
  const body = options.body as FormData;
  const entries: Record<string, string> = {};
  body.forEach((value, key) => {
    if (typeof value === "string") entries[key] = value;
  });
  return entries;
}

const mapping: ColumnMapping = {
  dateColumn: "Transaction Date",
  descriptionColumn: "Merchant",
  amountColumn: "Debit",
  dateFormat: "mdy",
  amountSign: "negative_is_charge",
  categoryColumn: "Category",
};

beforeEach(() => {
  vi.stubGlobal("localStorage", stubStorage());
  localStorage.setItem("pie-slice:token", "test-token");
  fetchMock = vi.fn().mockResolvedValue(jsonResponse({ importId: "i1", rows: [], skipped: [], duplicateCount: 0 }));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("uploadCsv", () => {
  const file = new File(["date,description,amount\n"], "statement.csv", { type: "text/csv" });

  it("sends every field of the mapping", () => {
    service.uploadCsv("g1", file, mapping);
    expect(sentFormData()).toEqual({
      dateColumn: "Transaction Date",
      descriptionColumn: "Merchant",
      amountColumn: "Debit",
      dateFormat: "mdy",
      amountSign: "negative_is_charge",
      categoryColumn: "Category",
    });
  });

  it("sends the category column when one is mapped", () => {
    // Regression: this was collected by the form and dropped here, so the
    // category never reached the imported expense.
    service.uploadCsv("g1", file, mapping);
    expect(sentFormData().categoryColumn).toBe("Category");
  });

  it("omits the category column when there is none", () => {
    service.uploadCsv("g1", file, { ...mapping, categoryColumn: null });
    expect(sentFormData()).not.toHaveProperty("categoryColumn");
  });

  it("sends only the file when no mapping is given", () => {
    service.uploadCsv("g1", file);
    expect(sentFormData()).toEqual({});
  });

  it("does not force a JSON content type on a multipart body", () => {
    // The browser must set Content-Type itself so it can add the multipart
    // boundary; overriding it makes the server unable to find the file.
    service.uploadCsv("g1", file, mapping);
    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((options.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });

  it("sends the bearer token", () => {
    service.uploadCsv("g1", file, mapping);
    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((options.headers as Record<string, string>).Authorization).toBe("Bearer test-token");
  });
});

describe("addExpense", () => {
  const base = {
    description: "Groceries",
    amountCents: 3000,
    payerId: "m1",
    date: "2026-08-26",
    splitMethod: "equal" as const,
    splitInput: { method: "equal" as const, memberIds: ["m1"] },
  };

  function sentJson(): Record<string, unknown> {
    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    return JSON.parse(options.body as string);
  }

  it("passes the category through", () => {
    service.addExpense("g1", { ...base, category: "Utilities" });
    expect(sentJson().category).toBe("Utilities");
  });

  it("passes every other field through untouched", () => {
    service.addExpense("g1", base);
    expect(sentJson()).toMatchObject(base);
  });
});

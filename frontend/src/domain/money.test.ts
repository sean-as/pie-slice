import { describe, it, expect } from "vitest";
import { formatCents, parseDollarsToCents } from "./money";

describe("formatCents", () => {
  it("formats whole dollars", () => {
    expect(formatCents(1200)).toBe("$12.00");
  });

  it("formats cents with leading zero", () => {
    expect(formatCents(105)).toBe("$1.05");
  });

  it("formats negative amounts", () => {
    expect(formatCents(-1200)).toBe("-$12.00");
  });

  it("formats zero", () => {
    expect(formatCents(0)).toBe("$0.00");
  });
});

describe("parseDollarsToCents", () => {
  it("parses a whole number", () => {
    expect(parseDollarsToCents("12")).toBe(1200);
  });

  it("parses two decimal places", () => {
    expect(parseDollarsToCents("12.34")).toBe(1234);
  });

  it("parses one decimal place", () => {
    expect(parseDollarsToCents("12.3")).toBe(1230);
  });

  it("rejects invalid input", () => {
    expect(parseDollarsToCents("abc")).toBeNull();
    expect(parseDollarsToCents("-5")).toBeNull();
    expect(parseDollarsToCents("12.345")).toBeNull();
    expect(parseDollarsToCents("")).toBeNull();
  });
});

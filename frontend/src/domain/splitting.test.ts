import { describe, it, expect } from "vitest";
import { splitEqual, splitExact, splitPercent, splitShares, SplitValidationError } from "./splitting";

describe("splitEqual", () => {
  it("splits evenly when it divides cleanly", () => {
    expect(splitEqual(300, ["a", "b", "c"])).toEqual([
      { memberId: "a", amountCents: 100 },
      { memberId: "b", amountCents: 100 },
      { memberId: "c", amountCents: 100 },
    ]);
  });

  it("distributes remainder cents deterministically and sums exactly", () => {
    const result = splitEqual(100, ["a", "b", "c"]);
    const sum = result.reduce((t, s) => t + s.amountCents, 0);
    expect(sum).toBe(100);
    // 100 / 3 = 33.33 each; two members get 34, one gets 33.
    const amounts = result.map((s) => s.amountCents).sort((a, b) => b - a);
    expect(amounts).toEqual([34, 33, 33]);
  });

  it("rejects an empty member list", () => {
    expect(() => splitEqual(100, [])).toThrow(SplitValidationError);
  });
});

describe("splitExact", () => {
  it("accepts amounts that sum to the total", () => {
    const result = splitExact(500, [
      { memberId: "a", amountCents: 300 },
      { memberId: "b", amountCents: 200 },
    ]);
    expect(result).toEqual([
      { memberId: "a", amountCents: 300 },
      { memberId: "b", amountCents: 200 },
    ]);
  });

  it("rejects amounts that don't sum to the total", () => {
    expect(() =>
      splitExact(500, [
        { memberId: "a", amountCents: 300 },
        { memberId: "b", amountCents: 100 },
      ])
    ).toThrow(SplitValidationError);
  });
});

describe("splitPercent", () => {
  it("splits proportionally to percentages summing to 100", () => {
    const result = splitPercent(1000, [
      { memberId: "a", percent: 50 },
      { memberId: "b", percent: 50 },
    ]);
    expect(result).toEqual([
      { memberId: "a", amountCents: 500 },
      { memberId: "b", amountCents: 500 },
    ]);
  });

  it("rejects percentages that don't sum to 100", () => {
    expect(() =>
      splitPercent(1000, [
        { memberId: "a", percent: 50 },
        { memberId: "b", percent: 40 },
      ])
    ).toThrow(SplitValidationError);
  });

  it("sums to the exact total even with uneven percentages", () => {
    const result = splitPercent(999, [
      { memberId: "a", percent: 33.33 },
      { memberId: "b", percent: 33.33 },
      { memberId: "c", percent: 33.34 },
    ]);
    expect(result.reduce((t, s) => t + s.amountCents, 0)).toBe(999);
  });
});

describe("splitShares", () => {
  it("splits proportionally to share counts", () => {
    const result = splitShares(300, [
      { memberId: "a", shares: 2 },
      { memberId: "b", shares: 1 },
    ]);
    expect(result).toEqual([
      { memberId: "a", amountCents: 200 },
      { memberId: "b", amountCents: 100 },
    ]);
  });

  it("sums exactly even when shares don't divide cleanly", () => {
    const result = splitShares(100, [
      { memberId: "a", shares: 1 },
      { memberId: "b", shares: 1 },
      { memberId: "c", shares: 1 },
    ]);
    expect(result.reduce((t, s) => t + s.amountCents, 0)).toBe(100);
  });

  it("rejects non-positive or fractional shares", () => {
    expect(() => splitShares(100, [{ memberId: "a", shares: 0 }])).toThrow(SplitValidationError);
    expect(() => splitShares(100, [{ memberId: "a", shares: 1.5 }])).toThrow(SplitValidationError);
  });
});

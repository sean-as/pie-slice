export const PALETTE = ["#4f46e5", "#0ea5a4", "#f59e0b", "#e11d48", "#16a34a", "#9333ea"];
export const OTHER = "Other";
export const OTHER_COLOR = "#9ca3af";

const norm = (s: string) => s.trim().toLowerCase();

/**
 * Colour per category for a year: the biggest few get their own colour, the
 * rest share "Other" so the legend stays readable.
 */
export function categoryColors(yearCategories: { category: string }[]): Map<string, string> {
  const colors = new Map<string, string>();
  yearCategories.forEach((c, i) => colors.set(norm(c.category), i < PALETTE.length ? PALETTE[i] : OTHER_COLOR));
  return colors;
}

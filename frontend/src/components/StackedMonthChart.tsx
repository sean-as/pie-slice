import type { MonthBreakdown } from "../domain/categoryMonths";
import { formatCents } from "../domain/money";

import { PALETTE, OTHER, OTHER_COLOR, categoryColors } from "../domain/categoryColors";

const MONTH_LETTERS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
const norm = (s: string) => s.trim().toLowerCase();

type Props = {
  year: string;
  /** Per-month breakdowns for any months with data; other months draw empty. */
  months: MonthBreakdown[];
  /** Year-level categories, largest first — fixes stack order and colours. */
  yearCategories: { category: string }[];
  selectedMonth?: string;
  onSelectMonth: (month: string) => void;
};

const W = 600;
const H = 180;
const TOP = 8;
const BOTTOM = 22;

export function StackedMonthChart({ year, months, yearCategories, selectedMonth, onSelectMonth }: Props) {
  const colors = categoryColors(yearCategories);
  const named = yearCategories.slice(0, PALETTE.length).map((c) => c.category);
  const hasOther = yearCategories.length > PALETTE.length;
  const byMonth = new Map(months.map((m) => [m.month, m]));
  const max = Math.max(1, ...months.map((m) => m.totalCents));
  const slot = W / 12;
  const barW = slot * 0.62;
  const plotH = H - TOP - BOTTOM;

  return (
    <figure className="stacked-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Spending by category per month, ${year}`}>
        {MONTH_LETTERS.map((letter, i) => {
          const key = `${year}-${String(i + 1).padStart(2, "0")}`;
          const data = byMonth.get(key);
          const x = i * slot + (slot - barW) / 2;
          let y = H - BOTTOM;
          // Stack in year-category order (largest at the base); "Other" on top.
          const order = [...named.map(norm), ...(hasOther ? [OTHER] : [])];
          const segments = order
            .map((k) => {
              const cents = (data?.categories ?? [])
                .filter((c) => (k === OTHER ? colors.get(norm(c.category)) === OTHER_COLOR : norm(c.category) === k))
                .reduce((sum, c) => sum + c.totalCents, 0);
              return { k, cents };
            })
            .filter((s) => s.cents > 0);
          return (
            <g
              key={key}
              className={data ? "chart-month" : undefined}
              onClick={data ? () => onSelectMonth(key) : undefined}
            >
              <title>{data ? `${key}: ${formatCents(data.totalCents)}` : key}</title>
              <rect x={i * slot} y={0} width={slot} height={H} fill={key === selectedMonth ? "#eef2ff" : "transparent"} />
              {segments.map((s) => {
                const h = (s.cents / max) * plotH;
                y -= h;
                return (
                  <rect key={s.k} x={x} y={y} width={barW} height={h} fill={s.k === OTHER ? OTHER_COLOR : colors.get(s.k)} />
                );
              })}
              <text x={i * slot + slot / 2} y={H - 6} textAnchor="middle" fontSize="12" fill="#666">
                {letter}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="chart-legend">
        {named.map((c) => (
          <span key={c}>
            <i style={{ background: colors.get(norm(c)) }} /> {c}
          </span>
        ))}
        {hasOther && (
          <span>
            <i style={{ background: OTHER_COLOR }} /> {OTHER}
          </span>
        )}
      </figcaption>
    </figure>
  );
}

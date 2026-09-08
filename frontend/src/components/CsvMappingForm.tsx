import { useState } from "react";
import type { AmountSign, ColumnMapping, DateFormat, FileShape } from "../domain/types";
import { formatCents } from "../domain/money";
import { detectDateFormat, parseCsv } from "../domain/csvImport";

const DATE_FORMAT_LABELS: Record<DateFormat, string> = {
  iso: "2026-08-26 (YYYY-MM-DD)",
  mdy: "08/26/2026 (MM/DD/YYYY)",
  dmy: "26/08/2026 (DD/MM/YYYY)",
};

/**
 * Reads one sample row under the current mapping so the user can see what
 * their choices actually do — the only honest way to settle MM/DD vs
 * DD/MM, which no amount of guessing can decide.
 */
function preview(shape: FileShape, mapping: ColumnMapping): string | null {
  const sample = shape.sampleRows[0];
  if (!sample) return null;

  const header = shape.columns.map((c) => `"${c.replace(/"/g, '""')}"`).join(",");
  const row = shape.columns.map((c) => `"${(sample[c] ?? "").replace(/"/g, '""')}"`).join(",");

  try {
    const { rows, skipped } = parseCsv(`${header}\n${row}`, mapping);
    if (rows.length > 0) {
      const { description, amountCents, date, category } = rows[0];
      return `${description} — ${formatCents(amountCents)} on ${date}${category ? ` (${category})` : ""}`;
    }
    if (skipped.length > 0) return `This row can't be read: ${skipped[0].reason}`;
    // Parsed fine but wasn't a charge under the chosen sign.
    return "This row would be skipped as a payment or credit, not a charge.";
  } catch (err) {
    return err instanceof Error ? err.message : "This row can't be read.";
  }
}

/**
 * Confirm-or-correct step between picking a file and reviewing its
 * transactions. Everything is pre-filled from what the server could safely
 * detect (and from the mapping this user last used here), so a familiar
 * file is one button press.
 */
export function CsvMappingForm({
  shape,
  onSubmit,
  onCancel,
  busy,
}: {
  shape: FileShape;
  onSubmit: (mapping: ColumnMapping) => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const [mapping, setMapping] = useState<ColumnMapping>(shape.suggested);

  function set<K extends keyof ColumnMapping>(key: K, value: ColumnMapping[K]) {
    setMapping((current) => ({ ...current, [key]: value }));
  }

  /**
   * Picking a different date column can change what format the dates are
   * in, so re-read the samples. Only applied when the answer is certain —
   * an ambiguous MM/DD vs DD/MM is still the user's call, and the preview
   * below is where they check it.
   */
  function setDateColumn(column: string) {
    const values = shape.sampleRows.map((row) => (row[column] ?? "").trim()).filter(Boolean);
    const detected = detectDateFormat(values);
    setMapping((current) => ({
      ...current,
      dateColumn: column,
      dateFormat: detected ?? current.dateFormat,
    }));
  }

  const columnField = (label: string, key: "dateColumn" | "descriptionColumn" | "amountColumn", role: string) => (
    <div className="field">
      <label htmlFor={`map-${key}`}>
        {label}
        {shape.unresolved.includes(role) && <span className="warning"> — please choose</span>}
      </label>
      <select
        id={`map-${key}`}
        value={mapping[key]}
        onChange={(e) => (key === "dateColumn" ? setDateColumn(e.target.value) : set(key, e.target.value))}
      >
        {shape.columns.map((column) => (
          <option key={column} value={column}>
            {column}
          </option>
        ))}
      </select>
    </div>
  );

  const sampleReading = preview(shape, mapping);

  return (
    <form
      className="mapping-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(mapping);
      }}
    >
      <h3>How should we read this file?</h3>
      {shape.unresolved.length > 0 && (
        <p className="meta">
          This file doesn't use the column names we recognize, so pick which is which.
        </p>
      )}

      {columnField("Date column", "dateColumn", "date")}
      {columnField("Description column", "descriptionColumn", "description")}
      {columnField("Amount column", "amountColumn", "amount")}

      <div className="field">
        <label htmlFor="map-date-format">Date format</label>
        <select
          id="map-date-format"
          value={mapping.dateFormat}
          onChange={(e) => set("dateFormat", e.target.value as DateFormat)}
        >
          {(Object.keys(DATE_FORMAT_LABELS) as DateFormat[]).map((format) => (
            <option key={format} value={format}>
              {DATE_FORMAT_LABELS[format]}
            </option>
          ))}
        </select>
        {shape.dateFormatAmbiguous && (
          <p className="warning">
            Day and month can't be told apart in this file — check the sample below reads the way
            you expect.
          </p>
        )}
      </div>

      <div className="field">
        <label htmlFor="map-amount-sign">Charges appear as</label>
        <select
          id="map-amount-sign"
          value={mapping.amountSign}
          onChange={(e) => set("amountSign", e.target.value as AmountSign)}
        >
          <option value="positive_is_charge">Positive numbers (79.99)</option>
          <option value="negative_is_charge">Negative numbers (-79.99)</option>
        </select>
      </div>

      <div className="field">
        <label htmlFor="map-category">Category column (optional)</label>
        <select
          id="map-category"
          value={mapping.categoryColumn ?? ""}
          onChange={(e) => set("categoryColumn", e.target.value || null)}
        >
          <option value="">None — my file has no category</option>
          {shape.columns.map((column) => (
            <option key={column} value={column}>
              {column}
            </option>
          ))}
        </select>
      </div>

      {shape.sampleRows.length > 0 && (
        <>
          <p className="meta">The first rows of your file, exactly as they appear in it:</p>
          <div className="sample-scroll">
            <table className="sample-table">
              <thead>
                <tr>
                  {shape.columns.map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shape.sampleRows.map((row, i) => (
                  <tr key={i}>
                    {shape.columns.map((column) => (
                      <td key={column}>{row[column]}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {sampleReading && (
        <p className="meta">
          With these settings, that first row reads as: <strong>{sampleReading}</strong>
        </p>
      )}

      <div className="actions">
        <button type="submit" disabled={busy}>
          Continue
        </button>
        <button type="button" className="secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  );
}

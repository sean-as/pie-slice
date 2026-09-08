import { useRef, useState } from "react";
import type { ImportPreview } from "../domain/types";
import { formatCents } from "../domain/money";
import { expenseService } from "../services";

/**
 * Two-step CSV import. Uploading only stages the file — the review list
 * below is where transactions actually get chosen, with merchants imported
 * before already ticked. A recurring monthly statement should be upload,
 * glance, submit.
 */
export function CsvImportPanel({ groupId, onImported }: { groupId: string; onImported: () => Promise<void> }) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  function reset() {
    setPreview(null);
    setSelected(new Set());
    if (fileInput.current) fileInput.current.value = "";
  }

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setError(null);
    setDone(null);
    setBusy(true);
    try {
      const result = await expenseService.uploadCsv(groupId, file);
      setPreview(result);
      // Merchants seen before start ticked; everything else starts off.
      setSelected(new Set(result.rows.filter((r) => r.preselected).map((r) => r.id)));
    } catch (err) {
      reset();
      setError(err instanceof Error ? err.message : "Could not read that file.");
    } finally {
      setBusy(false);
    }
  }

  function toggle(rowId: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
  }

  function toggleAll() {
    if (!preview) return;
    setSelected((current) =>
      current.size === preview.rows.length ? new Set() : new Set(preview.rows.map((r) => r.id))
    );
  }

  async function handleConfirm() {
    if (!preview) return;
    setError(null);
    setBusy(true);
    try {
      const imported = await expenseService.confirmImport(groupId, preview.importId, [...selected]);
      reset();
      setDone(
        imported.length === 0
          ? "Nothing imported."
          : `Imported ${imported.length} transaction${imported.length === 1 ? "" : "s"}.`
      );
      await onImported();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not import those transactions.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="import-panel">
      <h2>Import from CSV</h2>

      {!preview && (
        <>
          <p className="meta">
            A statement with <code>date</code>, <code>description</code> and <code>amount</code> columns.
            You'll review everything before anything is added.
          </p>
          <input ref={fileInput} type="file" accept=".csv,text/csv" onChange={handleFile} disabled={busy} />
        </>
      )}

      {error && <p className="error">{error}</p>}
      {done && <p className="meta">{done}</p>}

      {preview && (
        <>
          <p className="meta">
            {preview.rows.length === 0
              ? "Nothing new to import in that file."
              : `${preview.rows.length} transaction${preview.rows.length === 1 ? "" : "s"} to review — ${
                  selected.size
                } selected.`}
            {preview.duplicateCount > 0 &&
              ` ${preview.duplicateCount} already imported.`}
            {preview.skipped.length > 0 &&
              ` ${preview.skipped.length} row${preview.skipped.length === 1 ? "" : "s"} couldn't be read.`}
          </p>

          {preview.skipped.length > 0 && (
            <ul className="list meta">
              {preview.skipped.map((s) => (
                <li key={s.line}>
                  Line {s.line}: {s.reason}
                </li>
              ))}
            </ul>
          )}

          {preview.rows.length > 0 && (
            <>
              <button type="button" className="secondary" onClick={toggleAll}>
                {selected.size === preview.rows.length ? "Select none" : "Select all"}
              </button>
              <ul className="list">
                {preview.rows.map((row) => (
                  <li key={row.id} className="card">
                    <label className="import-row">
                      <input
                        type="checkbox"
                        checked={selected.has(row.id)}
                        onChange={() => toggle(row.id)}
                      />
                      <span>
                        {row.description} — {formatCents(row.amountCents)}
                        <br />
                        <span className="meta">
                          {row.date}
                          {row.preselected && " · imported before"}
                        </span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </>
          )}

          <div className="actions">
            <button type="button" onClick={handleConfirm} disabled={busy}>
              {selected.size === 0
                ? "Import nothing"
                : `Import ${selected.size} transaction${selected.size === 1 ? "" : "s"}`}
            </button>
            <button type="button" className="secondary" onClick={reset} disabled={busy}>
              Cancel
            </button>
          </div>
        </>
      )}
    </section>
  );
}

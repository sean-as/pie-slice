# pie-slice — spec gap analysis & implementation plan

Baseline: 57 backend tests pass, frontend builds. Auth, groups, members,
expenses (4 split methods), settlements, balances/settle-up are all
implemented end-to-end (backend + openapi + mock service + UI).

## Gap summary

| # | Spec requirement | Status | Size |
|---|---|---|---|
| 1 | CSV import (user stories 15–19, "CSV import" acceptance + tech constraints) | **Missing entirely** — no `csv`/`merchant` reference anywhere outside the spec | Large |
| 2 | "payer (one **existing member**)", split participants are members, settlement from/to are members | **Not enforced server-side** — `payer_id`, split `memberId`s, `fromMemberId`/`toMemberId` are accepted unvalidated | Small |
| 3 | "Two placeholder members with the same name … the UI should discourage it (e.g. a warning)" | **Missing** — no warning in `GroupPage.tsx` | Small |
| 4 | "Must work on mobile browsers (responsive)" | **Unverified** — `App.css` has a `max-width: 640px` container and zero media queries | Small |

Everything else in the spec traces to working code: bcrypt hashing
(`auth.py:20`), generic login error (`routers/auth.py`), localStorage token
surviving browser restart (`httpService.ts:14`), 404-not-403 for
non-member group access (`auth.py:42`), creator-only edit/delete enforced
server-side (`routers/expenses.py:20`), integer-cent math everywhere
(`domain.py`), derived-never-stored balances (`domain.py:105`).

---

## 1. CSV import

The one substantial feature. Decisions needed for the spec's "Open / not
yet decided" items — proposed defaults below, all cheap to change:

- **Merchant normalization**: `casefold()` + collapse internal whitespace +
  strip. No trailing-transaction-ID stripping (spec's non-goals rule out
  fuzzy matching).
- **Upload limits**: 1 MB and 2,000 data rows; over either → `413`.
- **Unparseable rows**: skipped, returned to the user in a `skipped[]`
  list with a row number and reason (the spec's stated assumption).

### 1a. Data model (`db_models.py`)

```
RememberedMerchantRow   user_id, group_id, merchant_normalized   UNIQUE(user_id, group_id, merchant_normalized)
ImportedTransactionRow  fingerprint (sha256 hex, UNIQUE), group_id, uploader_user_id, expense_id
PendingImportRow        id, group_id, uploader_user_id, created_at
PendingImportItemRow    id, import_id, date, description, amount_cents, fingerprint, preselected
```

The pending rows are held server-side between the upload response and the
submit, so the client only ever sends back a list of row ids — it never
round-trips (and therefore never gets to forge) the parsed amounts, dates,
or the fingerprint, which the tech constraint requires be computed
server-side and never trusted from the client. Pending imports are
transient: deleted on submit, and the CSV file itself is never stored
(non-goal).

### 1b. Parser (`app/csv_import.py`, pure — no FastAPI, no store)

- Header row required; header names matched case-insensitively; column
  order not assumed. Missing any of `date`/`description`/`amount` → `400`.
- `date` parsed as ISO `YYYY-MM-DD`; `amount` parsed as decimal dollars
  into integer cents via `Decimal` (never `float` — money-handling
  constraint).
- Rows with amount ≤ 0 silently skipped (not imported, not shown).
- Unparseable rows collected into `skipped[]`, never fatal.
- **Formula-injection defusal**: a `description` beginning with `=`, `+`,
  `-`, or `@` is prefixed with `'` before storage.
- `fingerprint(group_id, uploader_user_id, date, description, amount_cents)`
  → sha256 hex.

Unit-tested standalone (mirrors how `domain.py` is tested).

### 1c. Endpoints (`app/routers/imports.py`)

```
POST /groups/{groupId}/imports            multipart CSV
  → { importId, rows: ReviewRow[], skipped: SkippedRow[], duplicateCount: n }
     ReviewRow = { id, date, description, amountCents, preselected }
POST /groups/{groupId}/imports/{importId}/confirm
  body: { rowIds: string[] }        // exactly the rows the user left selected
  → { imported: Expense[] }
```

Both behind `require_group_membership`. **Nothing is created by the upload
call** — it only parses and stages. Per row:

1. fingerprint already in `ImportedTransactionRow` → dropped, counted into
   `duplicateCount`, never shown (re-upload safety);
2. merchant in the uploader's remembered list **for this group** → staged
   with `preselected: true`;
3. otherwise → staged with `preselected: false`.

`preselected` is a UI default only; the confirm call is authoritative, so
a user can deselect a pre-selected row or select a brand-new one freely.
Confirm creates an expense for each row id in the body (validating each id
belongs to this import, this user, and this group), adds each of those
merchants to the remembered list if absent, records the fingerprints, and
deletes the pending import. Unlisted rows are simply dropped. Deselecting
never removes a merchant from the remembered list.

An empty `rowIds` is valid and imports nothing. Submitting the same
`importId` twice must be safe — the second call finds no pending import
and 404s rather than double-importing.

Every created expense: `description` = transaction description,
`amountCents` = transaction amount, `payerId` = the uploader's own member
row in this group, `date` = transaction date, `splitMethod` = `equal`
across **all current group members**, `createdByUserId` = uploader —
reusing `resolve_splits` so it is byte-for-byte an ordinary expense
(creator-only edit/delete and balance inclusion come for free).

Edge case worth an explicit test: an uploader who is a linked member of
the group necessarily has a member row, so `payerId` always resolves.

### 1d. Contract + mock parity

- `openapi.yaml`: add both paths and the `ReviewRow`/`SkippedRow`/
  `ImportPreview`/`ConfirmImportInput` schemas.
- `services/types.ts`: add `uploadCsv` / `confirmImport` to
  `ExpenseServiceApi`.
- `httpService.ts` (multipart — must **not** send the JSON content-type
  header on this one call) and `mockService.ts` both implement them, so
  the no-backend mode keeps working.

### 1e. UI

New `CsvImportPanel` on `GroupPage`: file picker → upload → a review list
of checkboxes (pre-selected rows already ticked, new merchants unticked,
each showing date / description / amount), a "select all / none" control,
a summary line for what never made the list ("2 already imported, 1 row
couldn't be parsed"), and one **Import N transactions** button. Refresh
expenses + balances after. A recurring monthly statement should be a
two-click flow: upload, then submit.

### 1f. Tests

Backend: parser units (header casing, column reordering, negative/zero
skip, formula defusal, bad rows, cents precision e.g. `42.50` → `4250`);
router tests for: upload creates **zero** expenses (the core invariant of
the new model), pre-selection of a previously-imported merchant, confirm
importing only the listed rows, a deselected pre-selected row staying
remembered, selecting a brand-new merchant, re-upload dedupe hiding
already-imported rows, the per-(user, group) scoping of remembered
merchants (user story 18 — the one most likely to regress), a row id from
someone else's import being rejected, double-confirm, non-member 404, and
the size limit.
Frontend: a `csv` parse/format unit test if any parsing lands client-side
(preferably none — keep it server-side only).

---

## 2. Server-side member validation

Add a `_require_member(group, member_id)` helper (400 on miss) and apply
it in `routers/expenses.py` (payer + every split `memberId`, on both POST
and PUT) and `routers/settlements.py` (`fromMemberId`, `toMemberId`, plus
a from ≠ to check). Without it a client can post an expense whose payer is
a member of a *different* group, which lands in that group's expense list
and silently corrupts `compute_balances` (`domain.py:117` does
`net.get(...)` on an id that isn't in `member_ids`, so the money
disappears from the group's totals). Tests: 400 for foreign/garbage member
ids on each route.

## 3. Duplicate placeholder-name warning

In `GroupPage.tsx`, on placeholder submit, if the trimmed name
case-insensitively matches an existing member, show a confirm-style
warning ("Someone in this group is already called X — that makes 'who owes
whom' ambiguous") and require a second click to proceed. Spec explicitly
wants warn-not-block.

## 4. Mobile responsiveness

Verify at 375 px and fix what breaks: the `.inline-form` rows and the
`.card` action buttons are the likely offenders. Add a single
`@media (max-width: 480px)` block stacking those to full width. No
framework, no redesign.

---

## Suggested order

1. **#2 member validation** — small, closes a real data-integrity hole,
   and the import work depends on the same member-lookup helper.
2. **#1 CSV import**, in slices: model → parser (+ tests) → upload/confirm
   endpoints (+ tests) → openapi → mock + http services → review UI.
3. **#3 duplicate warning** and **#4 responsive** — small UI cleanups.

Commit after each slice per `AGENTS.md`.

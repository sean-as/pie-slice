# pie-slice — Product Spec

A free, simple expense-splitting tool for a group of friends/roommates/a
couple. Log who paid for what, split it flexibly, see who owes whom, and
record when debts get settled. Real accounts (email + password) — you sign
up, log in, and see the groups you're in.

## Core model

- A **user** has an account: email, password (hashed, never stored
  plaintext), and a display name.
- A **group** is created by a logged-in user, with a name. It has a list of
  **members**, each of which is either:
  - a **linked member** — tied to a real user account, added by
    username/email; that user can log in and see/act on the group, or
  - a **placeholder member** — just a display name, no account. Common
    case: someone who owes money but won't sign up for the app. Anyone
    else in the group can log expenses/settlements on a placeholder's
    behalf (as payer, in a split, or in a settlement).
- **Access requires login.** Only a linked member's own account can see or
  act on a group — there is no link-based or anonymous access.
- Every expense and settlement records **who (which logged-in user)
  created it**. Only that user can edit or delete it.
- Single currency: **USD only**.
- A user can **upload a CSV of their own credit card transactions** into a
  group to turn recurring bills (utilities, gas, groceries) into expenses
  without typing them in one at a time. Every upload ends in a **review
  screen**: transactions from merchants that person has imported before in
  that group come **pre-selected**, anything new starts unselected but can
  be selected too, and nothing is created until they submit. Each person
  builds up their own per-group list of previously-imported merchants
  simply by importing — there's no separate "always include" decision to
  make. No bank connection (e.g. Plaid) — CSV only, see Non-goals.

## User stories

1. As a visitor, I can sign up with an email, password, and display name.
2. As a returning user, I can log in and stay logged in across visits.
3. As a logged-in user, I can log out.
4. As a logged-in user, I see a list of the groups I'm a linked member of.
5. As a logged-in user, I can create a new group with a name; I become its
   first linked member automatically.
6. As a linked member of a group, I can add another member — either by
   looking up an existing user by username/email (linked member), or by
   typing a plain name (placeholder member, no account).
7. As a linked member of a group, I can log an expense: description,
   amount, who paid (any member, linked or placeholder), the date, and how
   it's split among members.
8. As anyone logging an expense, I can choose the split method per
   expense: **equal** across selected members (default: all group
   members), **exact dollar amounts** per person, **percentages** per
   person, or **shares** (e.g. 2 shares vs 1 share) per person.
9. As a linked member of a group, I can see a list of all logged expenses
   for the group (description, amount, payer, date, split, who logged it).
10. As the user who logged a given expense, I can edit or delete it. Other
    members cannot.
11. As a linked member of a group, I can see computed balances: what each
    member's net position is, and a simplified "who owes whom" list
    (minimum number of payments to settle the group, not a raw N×N
    matrix).
12. As a linked member of a group, I can record a settlement: from whom,
    to whom, amount, date, and an optional payment method note (e.g.
    "Venmo", "cash").
13. As a linked member of a group, recording a settlement updates the
    computed balances accordingly.
14. As the user who recorded a given settlement, I can edit or delete it.
    Other members cannot.
15. As a linked member of a group, I can upload a CSV of my own credit card
    transactions (date, description, amount) into that group.
16. Upon upload, I'm shown every transaction in the file to review before
    anything is created; transactions from merchants I've imported before
    *in this group* come pre-selected, so a recurring statement is mostly
    already ticked when I open it.
17. On that review screen I can select or deselect any transaction —
    including ones from merchants I've never imported before — and only
    what's still selected when I submit becomes an expense.
18. Importing a transaction remembers its merchant for me in this group,
    so it comes pre-selected on my next upload. That memory is mine alone
    — it doesn't affect what another member sees when they upload their
    own CSV, even to the same group, and doesn't carry over to a different
    group I'm in.
19. Expenses created from a CSV import behave exactly like any other
    expense: equal split across current group members, included in
    balances, and editable/deletable only by me (the importer).

## Acceptance criteria

**Accounts**
- Signup requires a unique email, a password meeting a minimum strength
  (length at minimum; exact rule is an implementation detail, not a
  product one), and a display name.
- Passwords are hashed (e.g. bcrypt/argon2) — never stored or logged in
  plaintext, never returned in any API response.
- Login establishes a session (mechanism — cookie session vs. token — is a
  technical decision, not specified here); staying logged in across a
  browser restart is expected.
- A failed login (wrong email or password) gives one generic error — never
  reveals whether the email exists (avoids account enumeration).

**Groups & membership**
- Creating a group requires a name; the creator is automatically a linked
  member.
- The groups-list view shows every group the current user is a linked
  member of, and nothing else.
- Adding a linked member requires finding an existing user by exact
  username/email — you cannot invite an email that has no account yet
  (see Non-goals). Adding a placeholder member requires only a non-empty
  name.
- Two placeholder members with the same name are allowed but the UI should
  discourage it (e.g. a warning), since it makes "who owes whom" ambiguous.
  A user can only be linked into a given group once.
- A member (linked or placeholder) can be selected as payer or split
  participant on any expense/settlement, regardless of who is logged in.
- Only a linked member of a group may view it or act within it; a request
  for a group the current user isn't a member of is treated the same as a
  nonexistent group (no leaking "it exists but you can't see it").

**Expenses**
- An expense requires: description (non-empty), amount (positive, in
  whole cents — no negative or zero expenses), payer (one existing
  member, linked or placeholder), date, and a split.
- Split methods:
  - *Equal*: amount ÷ number of selected members, remainder cents
    distributed deterministically (e.g. first N people by list order get
    one extra cent) so the split always sums exactly to the total.
  - *Exact amounts*: each selected member's entered amount; the sum of
    entered amounts must equal the expense total before it can be saved.
  - *Percentages*: each selected member's entered percentage; percentages
    must sum to 100 before it can be saved.
  - *Shares*: each selected member's entered share count (positive
    integer); amount is distributed proportionally to shares, remainder
    cents distributed deterministically.
- Default split (before the user changes anything) is equal, across all
  current group members.
- An expense is stamped with the logged-in user who created it. Only that
  user can edit (any field, including split method and amounts) or delete
  it; anyone else attempting to is rejected server-side, not just hidden
  in the UI.
- Editing or deleting an expense immediately recomputes balances.

**Balances & settle-up**
- Each member's net balance = (total they paid across expenses) − (total
  their share across expenses) + (net of settlements involving them).
- The "who owes whom" view shows a simplified minimum-transaction settle-up
  (standard debt-simplification: not a raw pairwise matrix), computed from
  net balances.
- A member with a net balance of exactly $0.00 does not appear in the
  settle-up list.

**Settlements**
- A settlement requires: payer (from), recipient (to), amount (positive),
  and date. Payment method is a free-text field and optional.
- Recording a settlement is available from the group view at any time
  (not gated on the settle-up suggestion — a member can record a
  settlement between any two members for any amount).
- A settlement is stamped with the logged-in user who created it. Only
  that user can edit or delete it, enforced server-side. Doing so
  immediately recomputes balances.

**Money handling**
- All amounts are stored and computed in integer cents internally — no
  floating-point currency math anywhere in the split/balance logic
  (prevents rounding-error drift across many expenses).

**CSV import**
- Expected file format: a header row followed by rows of `date,
  description, amount` (see Technical constraints for the exact grammar).
  Only rows with a positive amount are considered — zero/negative rows
  (payments, credits, refunds) are silently skipped: not imported and not
  shown on the review screen at all.
- "Merchant" = the transaction's `description` field. Matching against a
  remembered merchant is on that field (exact/normalized match — see Open
  / not yet decided for how forgiving that normalization is).
- The remembered-merchant list is scoped to **(uploading user, group)** —
  see user story 18.
- **No transaction is ever created without an explicit submit.** On
  upload, every parsed row is returned for review, each one either:
  1. **pre-selected** — its merchant is in this (user, group)'s
     remembered list, or
  2. **unselected** — a merchant this user hasn't imported in this group
     before.
  Both kinds are freely selectable and deselectable; the pre-selection is
  a convenience, not a commitment.
- On submit, exactly the still-selected rows become expenses. Deselected
  rows are not imported, and deselecting does *not* remove a merchant from
  the remembered list — it only skips it for this upload.
- Importing a row adds its merchant to the user's remembered list for this
  group if it isn't already there, so it is pre-selected on the *next*
  upload (not retroactively on past ones). There is no separate "always
  include" action — importing once is what remembers it.
- Every imported expense: `description` = the transaction's description,
  `amountCents` = the transaction's amount, `payerId` = the uploader's own
  member record in the group, `date` = the transaction's date,
  `splitMethod` = equal across all current group members, `createdByUserId`
  = the uploader. Identical in every other respect to a manually-logged
  expense (creator-only edit/delete, appears in balances, etc.).
- A transaction this user has already imported into this group is left off
  the review screen entirely (reported only as a count of skipped
  duplicates), so re-uploading a file or an overlapping date range can
  never double-import — see Technical
  constraints for the dedupe rule.

## Non-goals (this version)

- Inviting someone by email who doesn't have an account yet (a "pending
  invite" that resolves on signup) — the invitee must already have an
  account; until then, add them as a placeholder.
- Claiming/converting a placeholder member into a linked member later.
- OAuth/social login (Google, Apple, etc.) — email + password only.
- Password reset via email, or email verification at signup.
- Multiple currencies or currency conversion.
- Multiple payers on a single expense (log as two separate expenses
  instead).
- Removing a member from a group once added.
- Deleting or archiving an entire group.
- Transferring or sharing "creator" status on an expense/settlement — it's
  permanently whoever logged it (no reassignment, no admin override).
- Receipt photo attachments, categories/tags, or recurring expenses
  configured outside of CSV import.
- Notifications, reminders, or emails of any kind.
- Native mobile app — web only.
- Bank/card account aggregation (Plaid or similar) — CSV upload only, no
  live bank connection, no stored bank credentials of any kind.
- Configurable CSV column mapping — one fixed date/description/amount
  format (see Technical constraints); reformatting a bank's export to
  match is on the user.
- Per-merchant custom split method/ratio — CSV-imported expenses are
  always equal-split (like any new expense); edit afterward if a specific
  one needs a different split.
- Un-remembering a merchant, or any UI to view/manage the remembered-
  merchant list directly — the list is only ever visible as pre-selection
  on the review screen, and deselecting there skips that merchant for that
  upload without forgetting it. (Low stakes now that nothing imports
  without a review: a stale remembered merchant costs one unticked box,
  not an unwanted expense.)
- Fuzzy/approximate merchant matching (e.g. treating "AMAZON.COM*A1B2C"
  and "AMAZON MKTPLACE" as the same merchant) — matching is on the literal
  (normalized) description string.
- Retaining the uploaded CSV file itself after processing — only the
  resulting expenses are stored.

## Technical constraints

- Passwords hashed with a standard slow hash (bcrypt/argon2/scrypt) —
  never plaintext, never a fast general-purpose hash like raw SHA-256.
- Session/auth mechanism must survive a browser restart (a purely
  in-memory session is not sufficient) and must be usable from a
  separately-hosted frontend (CORS-aware if cookie-based).
- Every expense/settlement write requires an authenticated request; the
  server derives "who created this" from the session/token, never from a
  client-supplied field (a client claiming to be someone else must be
  rejected).
- Authorization (edit/delete = creator only; view/list = linked members
  only) is enforced server-side on every request, not just hidden in the
  UI — verified even if a client bypasses the normal app.
- Must work correctly with concurrent edits from multiple people/devices
  in the same group at once (no per-user locking exists to prevent this,
  so last-write-wins on non-conflicting fields is acceptable, but a write
  must never leave balances in a partially-computed/inconsistent state).
- Balance and settle-up computation must be a pure function of
  (expenses, settlements) — always derived, never stored as a mutable
  running total, so edits/deletes can never leave stale balances.
- All currency math in integer cents; never floating point.
- Must work on mobile browsers (responsive), even though there's no
  native app.

**CSV import**
- CSV grammar: header row required, columns `date` (ISO `YYYY-MM-DD`),
  `description` (free text), `amount` (plain decimal dollars, e.g.
  `42.50`; positive = charge). Header names matched case-insensitively;
  column order not assumed to be fixed as long as headers are present.
- Cell contents are always treated as plain text, never evaluated —
  standard CSV/spreadsheet formula-injection protection (a `description`
  starting with `=`, `+`, `-`, or `@` must not be treated specially by
  this app, and should be defused — e.g. prefixed — before ever being
  handed to a spreadsheet tool downstream).
- A reasonable upload size limit is enforced (row count and/or byte size;
  exact number is an implementation detail, not a product one) — this is
  a small-batch personal-finance tool, not a bulk data pipeline.
- Duplicate detection: a fingerprint of `(group_id, uploader_user_id,
  date, description, amount)` is computed server-side (never trusted from
  the client) and checked against already-imported transactions before
  creating a new expense from a row — re-uploading the same or an
  overlapping file must not double-import.
- Imported expenses are subject to the exact same authorization as any
  other expense (view = linked group members only, edit/delete = creator
  only) — importing doesn't create a new access-control path.

## Decided since (implementation details, revisit freely)

- Session mechanism: opaque bearer token, stored in `localStorage`
  (survives a browser restart, works from a separately-hosted frontend
  without cookie/CORS complications). Password hashing: bcrypt.
- Minimum password strength: length only, 8 characters.
- Duplicate placeholder-member names: warned about, not blocked — adding
  the same name twice asks for a confirming second submit.
- Merchant normalization for CSV matching: case-folding and
  whitespace-collapsing only. No trailing transaction-ID stripping, which
  would be the fuzzy matching the non-goals rule out.
- CSV limits: 1 MB and 2,000 rows. Unparseable rows are skipped and
  reported to the user with their line numbers; only a file-level problem
  (unreadable encoding, no header, a missing required column) rejects the
  whole file.

## Open / not yet decided

- Whether there's any limit on group size or number of expenses (assume
  none for MVP unless a real constraint shows up).
- Whether the merchant normalization above is forgiving enough in
  practice — banks that append a changing transaction ID to the
  description would defeat it, and we'd only find out from a real
  statement.

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
- Receipt photo attachments, categories/tags, or recurring expenses.
- Notifications, reminders, or emails of any kind.
- Native mobile app — web only.

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

## Open / not yet decided

- Tech stack (separate decision from this spec) — React + FastAPI is
  decided; session mechanism (cookie session vs. JWT) and password-hash
  algorithm choice are still open.
- Whether duplicate placeholder-member names should be blocked outright
  vs. just warned about.
- Whether there's any limit on group size or number of expenses (assume
  none for MVP unless a real constraint shows up).
- Minimum password strength rule (length-only vs. more).

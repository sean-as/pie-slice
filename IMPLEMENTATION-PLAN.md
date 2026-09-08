# pie-slice — spec gap analysis

A review of `product-spec.md` against the code, and what closing the gaps
took. Kept as a record of decisions; the spec itself is the live document.

## Findings (all now closed)

| # | Spec requirement | Was | Closed by |
|---|---|---|---|
| 1 | CSV import (user stories 15–19) | Missing entirely | `b2cb48e`, `0aa9fbe` |
| 2 | Payer / split / settlement participants must be existing members | Accepted unvalidated | `f254785` |
| 3 | Duplicate placeholder names should be discouraged | No warning | `0aa9fbe` |
| 4 | Must work on mobile browsers | No media queries | `0aa9fbe` |

Everything else traced to working code: bcrypt hashing, generic login
error, a token that survives a browser restart, 404-not-403 for non-member
group access, creator-only edit/delete enforced server-side, integer-cent
math throughout, and balances derived rather than stored.

## Notes on each

**#2 was the quiet one.** Nothing stopped a client from naming a member of
a *different* group as payer. The expense landed in this group's list, but
`compute_balances` only tallies ids in this group's member list — so the
money silently vanished from the group's totals rather than erroring.
`require_members` in `auth.py` now rejects it, on the payer, every resolved
split participant, and both settlement sides.

**#1 follows the revised spec**: an upload parses and stages but creates
nothing; every transaction comes back for review with previously-imported
merchants pre-ticked; a confirm call turns the chosen rows into ordinary
expenses. Two properties worth preserving if this is ever refactored:

- *The staged rows never leave the server.* Confirming sends only row ids,
  so amount, date and the dedupe fingerprint are always derived rather than
  restated by the client — the spec requires the fingerprint specifically.
- *Pre-selection is a UI default, not authority.* The confirm call's id list
  is what imports. A user can untick a remembered merchant (which does not
  forget it) or tick a brand-new one.

Already-imported transactions are dropped from the review list entirely and
only counted, so re-uploading an overlapping statement can't double-import.
Merchant memory is scoped to (user, group) — the property most likely to
regress under refactoring, and the one with the most tests.

**#4 is CSS-only** and was verified by inspection, not on a real handset.

## Decisions taken

Recorded in the spec's "Decided since" section: bcrypt + bearer token in
`localStorage`, 8-character password minimum, warn-don't-block on duplicate
placeholder names, case-and-whitespace-only merchant normalization, and
1 MB / 2,000-row CSV caps with per-row skip reporting.

## Verification

115 backend tests and 44 frontend tests pass; the frontend builds clean.
The import flow was also exercised end-to-end against a running backend:
upload creating nothing, a partial confirm, an overlapping re-upload
reporting the duplicate, and a following month arriving pre-selected.

# pie-slice — spec gap analysis

A review of `product-spec.md` against the code, and what closing the gaps
took. Kept as a record of decisions; the spec itself is the live document.

## Findings (all now closed)

| # | Spec requirement | Was | Closed by |
|---|---|---|---|
| 1 | CSV import (user stories 15–19) | Missing entirely | `b4f15a3`, `33dea8b` |
| 2 | Payer / split / settlement participants must be existing members | Accepted unvalidated | `b5b3d5e` |
| 3 | Duplicate placeholder names should be discouraged | No warning | `33dea8b` |
| 4 | Must work on mobile browsers | No media queries | `33dea8b` |

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

## Follow-up: configurable file formats

The spec originally called fixed CSV columns a non-goal ("reformatting a
bank's export to match is on the user"); that was reversed. Column names,
amount sign, and date format are now the user's to set, confirmed on a
mapping step before any transaction is interpreted.

Column names alone would have been a half-measure. Two adjacent differences
fail *silently* rather than loudly, which is the same class of bug as #2:

- **Amount sign.** Some banks write purchases as negative and payments as
  positive; others the reverse. Rows on the wrong side are dropped as "not a
  charge" — so mapping the columns correctly and still importing nothing was
  the likely outcome for a large share of banks.
- **Date format.** `09/01/2026` is genuinely ambiguous between US and EU
  order. Guessing would import transactions on the wrong dates without any
  error. It is inferred only when some row has a day > 12; otherwise the
  mapping form shows how a real row reads under the current choice and lets
  the user settle it.

`POST /imports/inspect` reads a file's shape without parsing a transaction
or storing anything, so the upload re-sends the file — one extra transfer of
a ≤1 MB file, traded against retaining statements server-side. A mapping
that parses is remembered per (user, group) and pre-fills next time; one
naming a missing column is rejected and not remembered, so a typo can't
become next month's default. Requests with no mapping still assume the
conventional headers, which is why every earlier test passed unchanged.

Still out of scope: CSV shapes that aren't one-row-per-transaction with a
single amount column — separate debit/credit columns, running balances,
preamble rows above the header.

## Confirmation step before import (implemented)

After the user picks rows on the review step, show a final confirmation
window listing **only the selected transactions** (date, merchant, amount,
category) and the total. The user can refine from there: deselect a row to
drop it, or go back to the review step to change the selection. Nothing is
created until they confirm on this window.

- Frontend-only change to the import flow: inspect → map → review →
  **confirm selected** → create. No new endpoint; the existing confirm call
  just fires from the new window instead of the review step.
- Deselecting on the confirmation window updates the same selection state,
  so "Back" returns to review with it intact.
- Empty selection disables the confirm button.
- Implemented in `CsvImportPanel.tsx` as a `confirming` state. No component
  test harness exists in the frontend (tests are domain-only), so this was
  verified by build/lint rather than automated tests.

## Balances by category per month — redone (implemented)

Redone as its own page, `/group/:groupId/spending` (`SpendingPage.tsx`), linked from the group header: month arrows, big month total with a "more/less than last month" line, one tappable row per category with a share bar and %, expanding to per-member paid/owes. Still client-side via `categoryByMonth`; tabular+bars, no chart lib. Update: defaults to year-to-date (Year/Month toggle; YTD compares to the same point last year), plus an SVG stacked bar chart of months by category (top 6 coloured, rest "Other"; tap a month to drill in). Not clicked through in a browser. Original plan below.

A group view showing spending broken down by category for each month, so
users can see where the money goes rather than only who owes whom.

- **Grouping.** Expenses bucketed by `YYYY-MM` of `date` and by `category`;
  uncategorised expenses fall into an explicit "Uncategorised" bucket so
  totals always reconcile with the overall figure.
- **What "balance" means here.** Per month and category: total spent, plus
  each member's share (what they paid vs. what they owe), reusing the
  existing integer-cent split math. Settlements carry no category and are
  excluded from category totals.
- **Category matching.** Case-and-whitespace-only normalization, same rule
  as merchants, so "Food" and "food " land in one bucket.
- **Backend.** Prefer a read-only `GET /groups/{groupId}/balances/by-category`
  (optional `from`/`to` month params), derived on read like existing
  balances — nothing stored. Add to `openapi.yaml`. Alternative: compute
  client-side from the expense list in `domain/`, which avoids an endpoint
  but duplicates the aggregation if other clients appear; decide when
  starting.
- **Frontend.** New view on the group page: month selector (default
  current month), table of categories with totals and per-member amounts,
  month-over-month navigation. Mobile layout must stack like the rest.
- **Tests.** Month boundaries (31st / 1st), uncategorised bucket, category
  normalization, cents summing exactly with uneven splits, settlements
  excluded, empty month.
- **Open questions.** Currency is single per group today (assumed); whether
  to chart it or keep it tabular (tabular first).

## dedicated members page per group (implemented)

Members management moves off the group page onto its own page, e.g.
`/group/:groupId/members`. The group page keeps expenses, balances and
import; the "Members" section with the add-linked / add-placeholder forms
is removed from it.

- **Header.** Group name, with an optional group description beneath it,
  then a member count ("5 members"). The count is a link/button that opens
  the editing mode for the member list.
- **Group description.** New optional field on groups: add to the group
  model, `openapi.yaml` (create + update + read), and the create-group form.
  Needs a way to edit it (and the name) from this page. Creator-only or any
  member is a decision to take; default to any member, matching how members
  are added today.
- **Add / edit.** Existing add-linked-member (by email) and add-placeholder
  forms move here, keeping the duplicate-name warning and the
  existing-member validation. "Edit" covers renaming a placeholder and
  removing a member; removal must be blocked (or require reassignment) for
  anyone referenced by an expense split or settlement, so balances never
  point at a missing member. Needs a backend rule and endpoint(s) — none
  exist for rename/remove today.
- **Navigation.** Group page header links to the members page (the count
  there is the entry point too); members page links back to the group.
  Route added in `App.tsx`; 404-not-403 for non-members, as elsewhere.
- **Tests.** Count reflects adds/removes; removal blocked when referenced;
  description optional and round-trips; non-member gets 404; duplicate-name
  warning still shown.

## group page layout — balances up top, one date-ordered ledger (implemented)

Reorder the group page to: group name and description → balances →
expenses. Today it is name → members → balances → expenses, with
settlements shown in the balances area and listed apart from expenses.
(Members leave the page entirely; see the members-page task.)

- **Balances section owns settling up.** The settle-up suggestions and the
  "record a settlement" action live inside the balances block. Recorded
  settlements are listed there too, each removable via the same "⋯" menu
  used elsewhere, so a mistaken settlement can be undone from where it was
  made. Deletion rules stay as today (creator-only, enforced server-side).
- **Settlements also appear as rows in the expenses list.** The list below
  balances becomes a single ledger of expenses *and* settlements, ordered
  by date, newest first. Settlement rows are visually distinct (e.g.
  "Alex paid Sam — $40.00", labelled "Settlement") and carry no category.
  Ties on the same date break by creation time so the order is stable.
- **No data-model change intended.** Settlements stay their own records
  (they have different semantics: no split, no category, and they must stay
  out of the category totals). The ledger is a merge of the two lists done
  at read time — either client-side in `domain/` or a combined endpoint;
  decide when starting. Settlement removal from a ledger row and from the
  balances block call the same delete, so the two views can't disagree.
- **Edit.** Expense rows keep edit + delete; settlement rows are
  delete-only (as today).
- **Tests.** Ordering by date with mixed types and same-day ties;
  settlement row appears after recording and disappears after removal from
  either place; balances update after removal; settlements excluded from
  category totals; mobile layout stacks.

## Implementation notes for the three tasks above

- **Category view** was built and then removed from the group page (the
  month-by-month list was not good UX). Reimplement with a better design.
  Kept for reuse: `domain/categoryMonths.ts` and its tests. Original notes:
  computed client-side (`domain/categoryMonths.ts`), no
  new endpoint; month navigation, not a month picker. Per-member figures are
  paid and owed per category.
- **Members page** at `/group/:groupId/members`. Backend adds
  `description` on groups, `PUT /groups/{id}`, `PUT`/`DELETE
  /groups/{id}/members/{memberId}`. Any member may edit group details;
  only account-less members can be renamed; removal is refused for
  yourself and for anyone in an expense or settlement. A small in-place
  `ALTER TABLE` in `main.py` adds the column to existing databases (no
  migration tool in this project).
- **Ledger** merged client-side (`domain/ledger.ts`). Settlement rows in the
  ledger are remove-only; editing a settlement is in the balances block.
- Verified by 196 backend tests (new member/group cases) and 104 frontend
  tests (new ledger/category cases) plus a clean build. The new pages have
  no component tests (no harness) and were not clicked through in a browser.

## TODO: make it deployable — phase 1 (private, founding users)

**Target:** one GCE `e2-micro` VM running Docker Compose, deployed by GitHub
Actions on push to `main`. Not public: no external ports, reached over
Tailscale. SQLite on a persistent disk (single process, two users).

### Done (app side, `backend/app`)
- Demo seed only when `SEED_DEMO=true` (default off).
- `CORS_ORIGINS` env; deployment is same-origin so it is unneeded there.
- Tokens expire (`TOKEN_TTL_DAYS`, default 90); expired rows are deleted on
  use. `tokens.created_at` added in place; pre-existing tokens count as
  expired (one-time re-login).
- `GET /api/health`; `DOCS_ENABLED=false` hides `/docs`.
- Backend serves the built frontend from `STATIC_DIR` (SPA fallback), so one
  container, one origin.

### Remaining

**1. Packaging**
- Multi-stage `Dockerfile` at the repo root: node stage builds the frontend
  with `VITE_API_URL=/api`; python stage runs `uv sync --frozen --no-dev`,
  copies `dist` to `/app/static`, runs `uvicorn app.main:app --host 0.0.0.0
  --port 8000` (no `--reload`, single worker — required by SQLite).
- `compose.yaml`: service `app`, image from Artifact Registry, volume
  `./data:/data`, `DATABASE_URL=sqlite:////data/pieslice.db`, `restart:
  unless-stopped`, healthcheck on `/api/health`, bound to `127.0.0.1:8000`.
- `.env.example` and a `.dockerignore`.
- The container runs as uid 1000, so the startup script must `install -d -o 1000
  -g 1000 /opt/pie-slice/data` after mounting the data disk (a bind mount hides
  the image's own `chown`).

**2. Infrastructure (Terraform, `infra/`)**

The code is public; the state and real values are not. See "What lives where"
below for the rule on every value.

*Bootstrap, once by hand* (the only steps outside Terraform, listed in
`infra/README.md`): create the project, link billing, create the state bucket
(versioned, uniform access, public access prevention on), then
`terraform init -backend-config=backend.hcl`.

*Layout:*

```
infra/
  versions.tf      provider pins; empty backend "gcs" {}
  variables.tf     project_id, region, zone, github_repository_id
  apis.tf          compute, artifactregistry, iap, iamcredentials,
                   secretmanager, billingbudgets
  network.tf       VPC, subnet, IAP-only firewall
  compute.tf       VM, boot disk, data disk
  registry.tf      Artifact Registry repo + cleanup policy
  iam.tf           the two service accounts and their roles
  wif.tf           Workload Identity pool and provider
  secrets.tf       secret containers + per-secret IAM (no values)
  storage.tf       backup bucket with a 7-day lifecycle
  budget.tf        billing budget alert
  outputs.tf       the values to copy into Actions variables
  startup.sh.tftpl
  terraform.tfvars.example
  backend.hcl.example
```

*Resources:*
- **Network:** custom VPC and subnet with Private Google Access. Firewall
  allows only the IAP range `35.235.240.0/20` on 22; nothing else inbound.
  Decided: Cloud NAT, no external IP (about $1/month plus data; an ephemeral
  IPv4 is billed too and would expose the VM).
- **VM:** `e2-micro`, Debian 12, in a free-tier region (us-west1, us-central1
  or us-east1), OS Login on. 30 GB standard disk in total, split into a boot
  disk and a **separate data disk** mounted at `/opt/pie-slice/data`, so
  replacing the VM never touches the database.
- **Startup script:** idempotent, since it runs on every boot. Installs Docker,
  the Compose plugin and Tailscale, adds a swap file (1 GB RAM is tight for
  pulls), mounts the data disk, configures Docker credentials for Artifact
  Registry, reads the Tailscale key from Secret Manager, runs `tailscale up`
  and `tailscale serve --bg 8000`. That gives
  `https://<vm>.<tailnet>.ts.net` with a real cert. Founding users join the
  tailnet or are shared the node.
- **Service account `vm`:** `artifactregistry.reader` on the repo,
  `secretmanager.secretAccessor` per secret, object admin on the backup bucket
  only, log and metric writer.
- **Service account `deployer`:** `artifactregistry.writer` on the repo,
  `iap.tunnelResourceAccessor`, `compute.osAdminLogin` on the VM (Docker access
  is root-equivalent anyway), `compute.viewer`, and `iam.serviceAccountUser` on
  the `vm` account. Nothing broader.
- **Workload Identity:** provider for
  `https://token.actions.githubusercontent.com`, with an attribute condition
  pinning `assertion.repository_id` (immutable, unlike the repo name) and
  `assertion.ref == "refs/heads/main"`. Required, because the repo is public.
  `deployer` is bound to that repository's principal set only.

*Terraform rules:*
- `prevent_destroy` on the data disk and backup bucket.
- Pass the startup script as `metadata["startup-script"]`, not
  `metadata_startup_script`, which forces VM replacement on any edit.
- Secret *values* never go through Terraform, or they land in state.
- Apply locally at first. CI runs only `terraform fmt -check` and
  `terraform validate` (`init -backend=false`), which need no credentials.
  Never run `plan` in Actions on this public repo: its output would expose
  real resource details in public logs.

**3. GitHub Actions** (`.github/workflows/`)
- `ci.yml` on PRs and pushes: backend `uv run pytest`, frontend `npm test`,
  lint, `npm run build`, Terraform fmt and validate.
- `deploy.yml` on push to `main` after CI passes: auth to GCP with
  **Workload Identity Federation** (no long-lived JSON key); build and push
  image tagged with the commit SHA (+ `latest`); then
  `gcloud compute ssh --tunnel-through-iap` to the VM and run
  `IMAGE_TAG=<sha> docker compose pull && docker compose up -d`; poll
  `/api/health` and fail the run if it never goes green.
- Reads only Actions **variables** (table below). There are no Actions
  secrets, because Workload Identity replaces the stored key.
- Runs in a `production` environment limited to `main`, on GitHub-hosted
  runners, never on `pull_request`.
- Rollback = re-run deploy with an older SHA (`workflow_dispatch` input).

**What lives where**

| Value | Where | Why |
|---|---|---|
| Tailscale auth key (tagged, so node key expiry is off) | Secret Manager: `tailscale-auth-key` | Credential; read by the VM at boot |
| Heartbeat ping URL (phase 2) | Secret Manager: `heartbeat-url` | Anyone holding it can fake a healthy ping |
| Future app secrets | Secret Manager, written to a root-only `/opt/pie-slice/.env` by the deploy step | Credentials. None exist today |
| `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_WIF_PROVIDER`, `GCP_DEPLOYER_SA`, `VM_NAME`, `VM_ZONE`, `AR_REPOSITORY` | GitHub Actions variables, copied from Terraform outputs | Needed to log in to GCP, so they can't come from Secret Manager; identifiers, not credentials |
| `DATABASE_URL`, `DOCS_ENABLED=false`, `SEED_DEMO=false`, `TOKEN_TTL_DAYS` | `compose.yaml`, committed | Not sensitive |
| `terraform.tfvars`, `backend.hcl` | Local only, gitignored | Real project details |
| Terraform state | Private GCS bucket | Holds real resource details; never in git |

Gitignore `*.tfvars`, `*.tfstate*`, `.terraform/` and `backend.hcl`; commit the
`.example` files and `.terraform.lock.hcl`. Add a secret value with
`gcloud secrets versions add <name> --data-file=-`.

**4. Data safety**
- Nightly: `sqlite3 .backup` to a temp file, then upload to a private GCS
  bucket (7-day lifecycle) from a cron/systemd timer on the VM; or daily
  disk snapshot schedule as the cheap start. **Do a test restore before
  trusting it.**
- DB lives on the VM disk, outside the container, so deploys never touch it.

**5. Safe incremental change**
- Schema changes go through Alembic (see "Before first deploy").
- Take a backup as the first step of every deploy.

**6. Smoke test (manual, after first deploy)**
Signup, create group, add expense, CSV import, settle up, spending page, over
the tailnet URL; confirm `/docs` is 404 and the demo users don't exist.

### Before first deploy (decided)
- **Alembic** baseline of the current schema; replace `_add_missing_columns`
  with `alembic upgrade head` on container start; SQLite batch mode.
- **Auth token in an `HttpOnly; Secure; SameSite=Lax` cookie** instead of
  `localStorage`; same-origin deployment keeps CSRF simple. Bearer header
  still accepted for tests/tools. Existing sessions are invalidated.
- **SQLite WAL mode + busy timeout** in `db.py`; Litestream is an option for
  continuous backup in place of the nightly job.

### Phase 2: monitoring (after initial deployment)
- The app is tailnet-only, so Google's uptime checks can't reach it. Use a
  dead-man's-switch: a systemd timer on the VM curls `/api/health` and pings
  a heartbeat service (e.g. healthchecks.io); missing pings email/notify.
- Alert on failed backup runs the same way (ping only on success).
- Cloud Monitoring VM alerts (disk > 80%, VM down) and Docker logs to Cloud
  Logging.

### Repo (decided)
Standalone public repo for portfolio use, so nothing committed may be
sensitive. The tree and history were scanned for secrets and real transaction
data before the move.

### Deferred (not needed while private)
Login/signup rate limiting, Sentry, public HTTPS/Caddy, Postgres. Revisit
before any public exposure. Signup is still open to anyone on the tailnet; add
an invite code or disable signup once the founding users have accounts.

### Order of work
1. ~~Scan, then move to the standalone repo.~~ Done.
2. Alembic, cookie auth, WAL.
3. Dockerfile + compose (verify locally with `docker compose up`).
4. `ci.yml`.
5. Terraform: bootstrap, apply, add secret values, copy outputs into Actions
   variables (needs your account).
6. `deploy.yml`, first deploy, smoke test.
7. Backups + restore test.

## Decisions taken

Recorded in the spec's "Decided since" section: bcrypt + bearer token in
`localStorage`, 8-character password minimum, warn-don't-block on duplicate
placeholder names, case-and-whitespace-only merchant normalization, and
1 MB / 2,000-row CSV caps with per-row skip reporting.

## Verification

155 backend tests and 68 frontend tests pass; the frontend builds clean.
The import flow was also exercised end-to-end against a running backend,
twice: first with a conventional file (upload creating nothing, a partial
confirm, an overlapping re-upload reporting the duplicate, a following month
arriving pre-selected), then with a deliberately hostile one — foreign
column names, purchases as negative numbers, US slash dates, and a decoy
second date column — confirming inspect → map → review → confirm, the
payment row correctly dropped, and the mapping remembered for next time.

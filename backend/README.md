# pie-slice backend

FastAPI implementation of [`../openapi.yaml`](../openapi.yaml) — that file
is the authoritative contract; this is one implementation of it. SQLAlchemy
+ SQLite by default, database-agnostic (see Database below).

## Run

```bash
uv sync
uv run uvicorn app.main:app --reload
```

API at `http://localhost:8000/api`, interactive docs at `/docs`.

Seeded on first run with two accounts (password `password123` for both) and
a demo group — safe to restart repeatedly, it only seeds once:

- `alice@example.com`
- `bob@example.com`

## Database

Configured via the `DATABASE_URL` env var (see `.env.example`; copy to
`.env` to override — loaded automatically). Defaults to a local SQLite
file, `./pieslice.db`, which persists across restarts.

No SQLite- or Postgres-specific SQL anywhere in the app — switching
backends is just changing `DATABASE_URL` and installing that backend's
driver, e.g.:

```bash
uv add psycopg2-binary
DATABASE_URL=postgresql://user:password@localhost:5432/pieslice uv run uvicorn app.main:app
```

Tables are created automatically on startup (`Base.metadata.create_all`) —
no separate migration step for this prototype.

## Test

```bash
uv run pytest
```

57 tests: `tests/test_domain.py` covers the split/balance math directly
(no HTTP); the rest drive the API through `TestClient`, including
cross-user permission checks (creator-only edit/delete, membership-gated
access). Tests run against an isolated in-memory SQLite database
(`conftest.py` sets `DATABASE_URL` before anything else is imported) —
never the file your dev server uses.

## Modules

| File | What it does |
| --- | --- |
| `app/models.py` | Pydantic schemas — camelCase wire format, mirrors `../openapi.yaml` components/schemas exactly |
| `app/domain.py` | Pure split/balance math, ported 1:1 from `../frontend/src/domain/{splitting,balances}.ts` |
| `app/db.py` | Engine/session setup — the only file that knows which database is configured |
| `app/db_models.py` | SQLAlchemy ORM tables |
| `app/store.py` | Data-access layer — converts ORM rows to the Pydantic schemas everything else uses; routers never touch SQLAlchemy directly |
| `app/auth.py` | Password hashing (bcrypt), bearer tokens, the `get_current_user` / `require_group_membership` dependencies every protected route uses |
| `app/routers/` | One file per resource (auth, groups, expenses, settlements, balances) |

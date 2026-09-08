from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db_models  # noqa: F401  (registers tables on Base.metadata)
from app.db import Base, engine
from app.routers import auth, balances, expenses, groups, imports, settlements
from app.store import seed

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="pie-slice API",
    version="0.2.0",
    description="Implements ../openapi.yaml. See that file for the authoritative contract.",
)

# Dev-only allowlist: the frontend's Vite dev server and preview server.
# Tighten this for any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173", "http://127.0.0.1:5173", "http://127.0.0.1:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(groups.router)
api.include_router(expenses.router)
api.include_router(settlements.router)
api.include_router(balances.router)
api.include_router(imports.router)
app.include_router(api)

# Demo data so the API has something to show immediately (e.g. via /docs).
# Login as alice@example.com / password123 or bob@example.com / password123.
seed()

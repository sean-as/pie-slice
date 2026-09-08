from __future__ import annotations

import logging

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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

logger = logging.getLogger("pieslice")


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """
    Turns an unexpected crash into a normal JSON response.

    Without this, an unhandled exception is rendered by Starlette's outermost
    error middleware — *outside* CORSMiddleware — so the 500 carries no
    `Access-Control-Allow-Origin` header. The browser then refuses to expose
    it and the frontend sees a bare "Failed to fetch", which looks like the
    server is down and hides the real error. Never let a bug masquerade as a
    network failure.
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Something went wrong on our end. Please try again."},
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

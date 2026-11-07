from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import db_models  # noqa: F401  (registers tables on Base.metadata)
from app.migrate import upgrade_to_head
from app.routers import auth, balances, expenses, groups, imports, settlements
from app.store import seed

# Schema is managed by Alembic (migrations/); this is `alembic upgrade head`.
upgrade_to_head()

def _env_flag(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# /docs is on for local dev; set DOCS_ENABLED=false to hide it when deployed.
_docs = _env_flag("DOCS_ENABLED", True)

app = FastAPI(
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
    title="pie-slice API",
    version="0.2.0",
    description="Implements ../openapi.yaml. See that file for the authoritative contract.",
)

# Defaults to the Vite dev/preview servers. Set CORS_ORIGINS (comma-separated)
# only if the frontend is served from a different origin than the API; the
# single-container deployment is same-origin and needs none.
_DEV_ORIGINS = "http://localhost:5173,http://localhost:4173,http://127.0.0.1:5173,http://127.0.0.1:4173"
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", _DEV_ORIGINS).split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("pieslice")

_BACKEND_PATHS = {"docs", "docs/oauth2-redirect", "redoc", "openapi.json"}


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


@api.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}


api.include_router(auth.router)
api.include_router(groups.router)
api.include_router(expenses.router)
api.include_router(settlements.router)
api.include_router(balances.router)
api.include_router(imports.router)
app.include_router(api)

def mount_frontend(target: FastAPI, static: Path) -> None:
    """
    Serves a built frontend from the same origin as the API, falling back to
    index.html so client-side routes survive a refresh. Backend paths are
    excluded from that fallback: a missing API route must stay a 404, not a
    200 of HTML, and disabled docs must actually be gone.
    """
    target.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @target.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/") or path in _BACKEND_PATHS:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
        candidate = (static / path).resolve()
        if path and candidate.is_file() and static.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(static / "index.html")


# The container image puts the build at STATIC_DIR.
_static = Path(os.environ.get("STATIC_DIR", "static"))
if _static.is_dir():
    mount_frontend(app, _static)


# Demo data (alice/bob, password123) is opt-in: SEED_DEMO=true for local dev.
if _env_flag("SEED_DEMO"):
    seed()

.PHONY: help install install-backend install-frontend \
        backend frontend dev \
        test test-backend test-frontend \
        build clean

help:
	@echo "pie-slice"
	@echo ""
	@echo "  make install          install backend + frontend dependencies"
	@echo "  make backend          run the FastAPI backend (foreground, :8000)"
	@echo "  make frontend         run the Vite dev server (foreground, :5173)"
	@echo "  make dev              run both together (Ctrl+C stops both)"
	@echo "  make test             run backend + frontend test suites"
	@echo "  make build            production-build the frontend"
	@echo "  make clean            remove venvs/node_modules/build output"

install: install-backend install-frontend

install-backend:
	cd backend && uv sync

install-frontend:
	cd frontend && npm install

backend:
	cd backend && uv run uvicorn app.main:app --reload

frontend:
	cd frontend && npm run dev

# Runs both dev servers in one terminal; Ctrl+C kills both (trap + wait
# keeps them in the same shell so the trap actually reaches them).
dev:
	@trap 'kill 0' EXIT; \
	(cd backend && uv run uvicorn app.main:app --reload) & \
	(cd frontend && npm run dev) & \
	wait

test: test-backend test-frontend

test-backend:
	cd backend && uv run pytest

test-frontend:
	cd frontend && npm test

build:
	cd frontend && npm run build

clean:
	rm -rf backend/.venv backend/.pytest_cache backend/pieslice.db
	find backend -name "__pycache__" -type d -prune -exec rm -rf {} +
	rm -rf frontend/node_modules frontend/dist

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import mount_frontend


@pytest.fixture
def frontend(tmp_path: Path) -> TestClient:
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('app')")
    (tmp_path / "index.html").write_text("<html>spa</html>")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path.parent / "secret.txt").write_text("secret")

    # Docs disabled, as deployed: nothing but the fallback could answer /docs.
    target = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @target.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    mount_frontend(target, tmp_path)
    return TestClient(target)


@pytest.mark.parametrize("path", ["/", "/login", "/group/abc/spending"])
def test_client_routes_get_index_html(frontend: TestClient, path: str):
    response = frontend.get(path)
    assert response.status_code == 200
    assert "spa" in response.text


def test_built_files_are_served(frontend: TestClient):
    assert frontend.get("/assets/app.js").text == "console.log('app')"
    assert frontend.get("/favicon.svg").text == "<svg/>"


def test_real_api_routes_win_over_the_fallback(frontend: TestClient):
    assert frontend.get("/api/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/api", "/api/nope", "/api/groups/x/nope", "/docs", "/redoc", "/openapi.json"])
def test_backend_paths_404_instead_of_serving_html(frontend: TestClient, path: str):
    response = frontend.get(path)
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_cannot_read_outside_the_static_dir(frontend: TestClient):
    response = frontend.get("/..%2fsecret.txt")
    assert "secret" not in response.text

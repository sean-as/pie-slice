from __future__ import annotations

from pathlib import Path

PUBLIC_ROBOTS = Path(__file__).resolve().parents[2] / "frontend" / "public" / "robots.txt"
INDEX_HTML = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def test_every_response_asks_crawlers_not_to_index(client):
    for path in ("/api/health", "/api/auth/me", "/api/nope"):
        header = client.get(path).headers["x-robots-tag"]
        assert "noindex" in header and "nofollow" in header


def test_robots_txt_disallows_everything():
    lines = PUBLIC_ROBOTS.read_text().splitlines()
    assert "User-agent: *" in lines and "Disallow: /" in lines


def test_html_shell_has_a_noindex_meta_tag():
    assert 'name="robots" content="noindex' in INDEX_HTML.read_text()


def test_server_errors_are_marked_noindex_too(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.store import store

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(store, "user_id_for_token", boom)
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/auth/me", headers={"Authorization": "Bearer x"}
    )
    assert response.status_code == 500
    assert "noindex" in response.headers["x-robots-tag"]

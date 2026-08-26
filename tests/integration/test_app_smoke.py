import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    app.state.ws_worker_disabled = True
    with TestClient(app) as c:
        yield c


def test_health_ok(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "db" in body


def test_cors_allowed_origin(client: TestClient):
    resp = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_unknown_origin_rejected(client: TestClient):
    resp = client.get("/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in resp.headers


def test_bind_loopback_only():
    from app.config import settings

    assert settings.host in ("127.0.0.1", "localhost")
    assert settings.cors_origin_list == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

from fastapi.testclient import TestClient


def test_ai_models_endpoint(client):
    resp = client.get("/api/ai/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "openrouter"
    assert "enabled" in body  # phụ thuộc .env, chỉ check field tồn tại
    assert "deepseek/deepseek-v4-flash-0731" in body["models"]
    # default model phải nằm trong whitelist
    assert body["default_model"] in body["models"]

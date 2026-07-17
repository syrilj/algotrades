from fastapi.testclient import TestClient

from services.market_runtime.api import create_app


def test_health_is_public_but_runtime_endpoints_require_configured_token(monkeypatch):
    monkeypatch.setenv("MARKET_RUNTIME_API_TOKEN", "secret-value")
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/metrics").status_code == 401
        assert client.get("/metrics", headers={"X-API-Key": "wrong"}).status_code == 401
        response = client.get("/metrics", headers={"X-API-Key": "secret-value"})
        assert response.status_code == 200
        assert response.json()["service"] == "market-runtime"


def test_plan_rejects_invalid_numeric_and_identifier_inputs(monkeypatch):
    monkeypatch.delenv("MARKET_RUNTIME_API_TOKEN", raising=False)
    with TestClient(create_app()) as client:
        assert client.post("/plan", json={"symbol": "SPY", "account": "nan"}).status_code == 400
        assert client.post("/plan", json={"symbol": "../../secret", "account": 1000}).status_code == 400
        assert client.post("/analyze", json={"symbol": "SPY", "top_n": 999}).status_code == 400

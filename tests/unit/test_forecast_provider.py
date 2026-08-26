from datetime import UTC, datetime

import pytest

from app.forecast.provider import ForecastProvider
from app.forecast.registry import ProviderRegistry
from app.forecast.schema import ForecastContext, Signal


class DummyProvider:
    name = "dummy"

    def forecast(self, ctx: ForecastContext) -> Signal:
        return Signal(
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            direction="LONG",
            probability=0.5,
            entry=100.0,
            model=self.name,
        )


class FailingProvider:
    name = "failing"

    def forecast(self, ctx: ForecastContext) -> Signal:
        raise RuntimeError("boom")


class TestProviderContract:
    def test_dummy_is_forecast_provider(self):
        assert isinstance(DummyProvider(), ForecastProvider)

    def test_forecast_returns_signal(self):
        ctx = ForecastContext(symbol="BTCUSDT", timeframe="1h")
        sig = DummyProvider().forecast(ctx)
        assert sig.symbol == "BTCUSDT"
        assert sig.timeframe == "1h"
        assert sig.model == "dummy"


class TestRegistry:
    def test_register_get_list(self):
        r = ProviderRegistry()
        r.register(DummyProvider())
        assert r.list() == ["dummy"]
        assert isinstance(r.get("dummy"), DummyProvider)
        assert r.get("nope") is None

    def test_health_tracks_success_and_error(self):
        r = ProviderRegistry()
        r.register(DummyProvider())
        r.register(FailingProvider())
        r.record_success("dummy")
        r.record_error("failing", "boom")
        h = {entry["name"]: entry for entry in r.health()}
        assert h["dummy"]["forecast_count"] == 1
        assert h["dummy"]["last_error"] is None
        assert h["failing"]["last_error"] == "boom"

    def test_global_registry_initialized(self):
        from app.forecast.registry import registry

        assert registry.list() == []


class TestRegistryWithApi:
    def test_forecast_health_empty(self, client):
        resp = client.get("/api/forecast/health")
        assert resp.status_code == 200
        assert resp.json()["providers"] == []

    def test_forecast_no_providers_503(self, client):
        resp = client.get("/api/forecast/BTCUSDT/1h")
        assert resp.status_code == 503

    def test_forecast_with_registered_provider(self, client, monkeypatch):
        from app.forecast.registry import registry as reg

        reg.register(DummyProvider())
        resp = client.get("/api/forecast/BTCUSDT/1h")
        assert resp.status_code == 200
        body = resp.json()
        assert body["model"] == "dummy"
        assert body["direction"] == "LONG"

    def test_forecast_unknown_provider_404(self, client):
        resp = client.get("/api/forecast/BTCUSDT/1h?provider=nope")
        assert resp.status_code == 404

    def test_forecast_provider_fails_502(self, client):
        from app.forecast.registry import registry as reg

        reg.register(FailingProvider())
        resp = client.get("/api/forecast/BTCUSDT/1h")
        assert resp.status_code == 502

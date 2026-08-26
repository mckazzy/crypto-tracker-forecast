import json

import httpx
import pytest

from app.forecast.ai_provider import AIProvider, TokenBudget
from app.forecast.llm_client import LLMClient
from app.forecast.schema import ForecastContext, SignalStatus


def make_ctx(**overrides) -> ForecastContext:
    base = {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "candles": [
            {
                "open_time": 1_760_000_000_000,
                "open": 40000.0,
                "high": 40200.0,
                "low": 39900.0,
                "close": 40100.0,
                "volume": 123.4,
            },
            {
                "open_time": 1_760_003_600_000,
                "open": 40100.0,
                "high": 40300.0,
                "low": 40050.0,
                "close": 40250.0,
                "volume": 150.0,
            },
        ],
    }
    base.update(overrides)
    return ForecastContext(**base)


def llm_client_for(json_response: dict | str, status=200) -> LLMClient:
    """LLMClient with a MockTransport returning a fixed JSON response."""

    class FakeTransport(httpx.BaseTransport):
        def handle_request(self, request):
            return httpx.Response(status, json=json_response)

    return LLMClient(
        base_url="http://fake.local/v1",
        api_key="test",
        model="test-model",
        transport=FakeTransport(),
    )


class FakeTransport(httpx.BaseTransport):
    def __init__(self, responses: list):
        self.responses = responses
        self.calls = 0

    def handle_request(self, request):
        self.calls += 1
        resp = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        return resp


class TestLLMClient:
    def test_chat_json_parses_content(self):
        client = llm_client_for({"choices": [{"message": {"content": '{"direction":"LONG"}'}}]})
        assert client.chat_json("sys", "user") == {"direction": "LONG"}

    def test_chat_json_http_error_raises(self):
        client = llm_client_for({}, status=500)
        with pytest.raises(httpx.HTTPStatusError):
            client.chat_json("sys", "user")


class TestTokenBudget:
    def test_under_budget(self):
        b = TokenBudget(100)
        assert not b.over_budget()
        b.record(30)
        assert not b.over_budget(20)
        assert b.used == 30

    def test_over_budget(self):
        b = TokenBudget(100)
        b.record(90)
        assert b.over_budget(20)
        b.record(10)  # still over
        assert b.used == 100


class TestAIProvider:
    def test_valid_signal(self):
        client = llm_client_for(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "direction": "LONG",
                                    "probability": 0.63,
                                    "entry": 67200.0,
                                    "take_profit": [68500.0],
                                    "stop_loss": 66100.0,
                                    "rr_ratio": 1.8,
                                }
                            )
                        }
                    }
                ]
            }
        )
        p = AIProvider(client=client)
        sig = p.forecast(make_ctx())
        assert sig.direction.value == "LONG"
        assert sig.probability == 0.63
        assert sig.status == SignalStatus.OK
        assert sig.model == "ai"

    def test_invalid_json_retry_once(self):
        """First response invalid → retry → valid on second try."""
        bad = {"choices": [{"message": {"content": "not json"}}]}
        good = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"direction": "SHORT", "probability": 0.5, "entry": 100.0}
                        )
                    }
                }
            ]
        }
        transport = FakeTransport(
            [
                httpx.Response(200, json=bad),
                httpx.Response(200, json=good),
            ]
        )
        client = LLMClient("http://fake/v1", "k", "m", transport=transport)
        p = AIProvider(client=client)
        sig = p.forecast(make_ctx())
        assert sig.direction.value == "SHORT"
        assert transport.calls == 2

    def test_both_invalid_failed(self):
        bad = {"choices": [{"message": {"content": "not json"}}]}
        transport = FakeTransport(
            [
                httpx.Response(200, json=bad),
                httpx.Response(200, json=bad),
            ]
        )
        client = LLMClient("http://fake/v1", "k", "m", transport=transport)
        p = AIProvider(client=client)
        sig = p.forecast(make_ctx())
        assert sig.status == SignalStatus.FAILED

    def test_http_error_failed(self):
        transport = FakeTransport([httpx.Response(503, json={})])
        client = LLMClient("http://fake/v1", "k", "m", transport=transport)
        p = AIProvider(client=client)
        sig = p.forecast(make_ctx())
        assert sig.status == SignalStatus.FAILED

    def test_token_budget_skip(self):
        b = TokenBudget(10)
        b.record(10)
        p = AIProvider(client=llm_client_for({"choices": []}), budget=b)
        sig = p.forecast(make_ctx())
        assert sig.status == SignalStatus.FAILED

    def test_build_prompt_minimal_context(self):
        p = AIProvider(client=llm_client_for({}))
        prompt = p._build_prompt(make_ctx())
        assert "BTCUSDT" in prompt
        assert "1h" in prompt
        assert "40000.0" in prompt

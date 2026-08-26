import httpx
import pytest

from app.alerts.telegram import TelegramSender, build_alert_message


class TestBuildAlertMessage:
    def test_long_template(self):
        msg = build_alert_message(
            symbol="BTCUSDT", timeframe="1h", direction="LONG", entry=67200.0,
            tp=[68500.0, 69200.0], sl=66100.0, model="meta-lgbm@v14",
        )
        assert "BTCUSDT" in msg and "1h" in msg and "LONG" in msg
        assert "67200" in msg and "68500" in msg and "69200" in msg and "66100" in msg
        assert "meta-lgbm@v14" in msg

    def test_short_template(self):
        msg = build_alert_message(
            symbol="ETHUSDT", timeframe="4h", direction="SHORT", entry=3000.0,
            tp=[2900.0], sl=3100.0, model="ai",
        )
        assert "SHORT" in msg and "3000" in msg and "2900" in msg and "3100" in msg


class FakeTransport(httpx.BaseTransport):
    def __init__(self, ok=True):
        self.ok = ok
        self.calls = 0
        self.last_url = None

    def handle_request(self, request):
        self.calls += 1
        self.last_url = str(request.url)
        if self.ok:
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(500, json={"ok": False})


class TestTelegramSender:
    def test_send_ok(self):
        transport = FakeTransport(ok=True)
        sender = TelegramSender(
            bot_token="test-token", chat_id="123", transport=transport
        )
        ok = sender.send("hello")
        assert ok is True
        assert transport.calls == 1
        assert "test-token" in transport.last_url

    def test_send_failure_returns_false(self):
        transport = FakeTransport(ok=False)
        sender = TelegramSender(
            bot_token="test-token", chat_id="123", transport=transport
        )
        assert sender.send("hello") is False

    def test_missing_config_disabled(self):
        sender = TelegramSender(bot_token="", chat_id="")
        assert sender.enabled is False
        assert sender.send("hello") is False

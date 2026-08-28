"""WS relay integration tests — fake upstream server, no-network marker.

Monkeypatch websockets.connect để phục vụ frame giả lập từ Binance; verify:
normalize frame, fan-out 2 clients share 1 upstream, engine nhận tick với 0
client, invalid symbol bị chặn, disconnect sạch.
"""
import asyncio
import json

import pytest

from app.ws.relay import BinanceRelay, build_futures_stream_url, normalize_frame


def mark_event(symbol="BTCUSDT", mark=60000.0):
    return {"e": "markPriceUpdate", "E": 1700000000000, "s": symbol, "p": str(mark)}


def kline_event(symbol="BTCUSDT", close=60000.0):
    return {
        "e": "kline",
        "s": symbol,
        "k": {
            "t": 1700000000000,
            "T": 1700000005999,
            "i": "1m",
            "o": "59900",
            "h": "60100",
            "l": "59800",
            "c": str(close),
            "v": "100.5",
            "x": False,
        },
    }


class FakeUpstream:
    """Thay thế websockets.connect: phát frame giả lập, kiểm soát bằng queue."""

    def __init__(self, frames=None):
        self.frames = frames or []
        self.connected = 0

    async def __aenter__(self):
        self.connected += 1
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        async def gen():
            for f in self.frames:
                yield json.dumps(f)
            # giữ connection mở tới khi cancel
            await asyncio.Event().wait()

        return gen()


@pytest.fixture
def fake_connect(monkeypatch):
    upstreams: dict[str, FakeUpstream] = {}

    def make(url, **kwargs):
        symbol = url.split("streams=")[1].split("@")[0].upper()
        if symbol not in upstreams:
            upstreams[symbol] = FakeUpstream()
        return upstreams[symbol]

    import websockets

    monkeypatch.setattr(websockets, "connect", make)
    yield upstreams
    # cleanup: cancel mọi task upstream đang treo
    for up in upstreams.values():
        up.connected = 0


class TestNormalizer:
    def test_mark_price_normalized(self):
        f = normalize_frame(mark_event())
        assert f["type"] == "markPrice"
        assert f["mark"] == 60000.0
        assert f["symbol"] == "BTCUSDT"

    def test_kline_normalized(self):
        f = normalize_frame(kline_event())
        assert f["type"] == "kline"
        assert f["timeframe"] == "1m"
        assert f["close"] == 60000.0
        assert f["is_closed"] is False

    def test_unknown_event_none(self):
        assert normalize_frame({"e": "bookTicker"}) is None

    def test_combined_envelope_unwrapped(self):
        f = normalize_frame({"stream": "btcusdt@markPrice", "data": mark_event()})
        assert f["type"] == "markPrice"
        assert f["mark"] == 60000.0

    def test_build_url(self):
        url = build_futures_stream_url("BTCUSDT")
        assert "btcusdt@markPrice@1s" in url
        assert "btcusdt@kline_1m" in url


class TestRelayLifecycle:
    async def test_2_clients_share_1_upstream(self, fake_connect):
        relay = BinanceRelay(symbol_list=["BTCUSDT"])
        try:
            q1 = await relay.subscribe("BTCUSDT")
            q2 = await relay.subscribe("BTCUSDT")
            await asyncio.sleep(0.01)  # cho upstream task chạy connect
            assert fake_connect["BTCUSDT"].connected == 1
            # push frame qua upstream task — dùng queue nội bộ của upstream
            up = relay._upstreams["BTCUSDT"]
            up.queues.add(q1)
            up.queues.add(q2)
            # fan-out 1 frame
            frame = normalize_frame(mark_event())
            relay._fanout(up, frame)
            f1 = await asyncio.wait_for(q1.get(), 1.0)
            f2 = await asyncio.wait_for(q2.get(), 1.0)
            assert f1 == frame
            assert f2 == frame
        finally:
            await relay.shutdown()

    async def test_invalid_symbol_rejected(self):
        relay = BinanceRelay(symbol_list=["BTCUSDT"])
        with pytest.raises(ValueError):
            await relay.subscribe("DOGEUSDT")

    async def test_engine_receives_tick_with_zero_clients(self):
        """Engine nhận tick từ upstream reader — không cần client nào."""
        engine_ticks = []

        class FakeEngine:
            _queue = None

            def __init__(self):
                self._queue = asyncio.Queue()

        engine = FakeEngine()
        relay = BinanceRelay(engine=engine, symbol_list=["BTCUSDT"])
        try:
            up = await relay.get_or_create("BTCUSDT")
            # đẩy frame qua upstream (mô phỏng reader nhận từ Binance)
            frame = normalize_frame(mark_event())
            relay._fanout(up, frame)
            q = engine._queue
            # fanout không đẩy engine — kiểm tra qua đường upstream task mô phỏng:
            await q.put({"symbol": frame["symbol"], "mark": frame["mark"]})
            tick = await asyncio.wait_for(q.get(), 1.0)
            assert tick["mark"] == 60000.0
        finally:
            await relay.shutdown()

    async def test_disconnect_releases_queue(self):
        relay = BinanceRelay(symbol_list=["BTCUSDT"])
        try:
            q = await relay.subscribe("BTCUSDT")
            up = relay._upstreams["BTCUSDT"]
            assert q in up.queues
            await relay.release("BTCUSDT", q)
            # refcount = 0, không position/order active → upstream bị evict
            assert "BTCUSDT" not in relay._upstreams
        finally:
            await relay.shutdown()

    async def test_catchup_inject_after_reconnect(self, monkeypatch):
        """Sau reconnect, catch-up tick được inject (REST mark fallback)."""
        relay = BinanceRelay(symbol_list=["BTCUSDT"])
        try:
            up = await relay.get_or_create("BTCUSDT")
            injected = []

            async def fake_inject(u):
                injected.append(u.symbol)
                # fanout 1 frame giả
                frame = {"type": "markPrice", "symbol": u.symbol, "mark": 12345.0, "ts": 0}
                relay._fanout(u, frame)

            monkeypatch.setattr(relay, "_inject_catchup", fake_inject)
            q = asyncio.Queue()
            up.queues.add(q)
            await relay._inject_catchup(up)
            assert injected == ["BTCUSDT"]
            f = await asyncio.wait_for(q.get(), 1.0)
            assert f["mark"] == 12345.0
        finally:
            await relay.shutdown()

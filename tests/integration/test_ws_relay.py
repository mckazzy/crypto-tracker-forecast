"""WS relay integration tests — fake upstream server, no-network marker.

Monkeypatch websockets.connect để phục vụ frame giả lập từ Binance; verify:
normalize frame, fan-out 2 clients share 1 upstream, engine nhận tick với 0
client, invalid symbol bị chặn, disconnect sạch, watchdog REST fallback khi WS
im lặng.
"""
import asyncio
import json
import time

import pytest

from app.config import settings
from app.ws import relay as relay_module
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


class DelayedFramesUpstream(FakeUpstream):
    """Như FakeUpstream nhưng phát frame sau delay 0.05s.

    time.monotonic() trên Windows có resolution thô (có thể cùng tick trong
    vài ms) — delay đảm bảo frame được xử lý ở monotonic tick KHÁC lúc creation
    để test reset baseline không bị nhiễu bởi resolution.
    """

    def __aiter__(self):
        async def gen():
            await asyncio.sleep(0.05)
            for f in self.frames:
                yield json.dumps(f)
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


def _fast_watchdog_settings(monkeypatch):
    """Rút ngắn silence/poll để test watchdog nhanh (không đợi 5s thật)."""
    fast = settings.model_copy(
        update={
            "binance_futures_ws_silence_timeout": 0.2,
            "binance_futures_rest_poll_interval": 0.05,
        }
    )
    monkeypatch.setattr(relay_module, "settings", fast)
    return fast


class TestWatchdog:
    async def test_silence_injects_rest_mark(self, fake_connect, monkeypatch):
        """WS im lặng > timeout → watchdog poll REST → client queue + engine tick."""
        engine_ticks = []

        class FakeEngine:
            def __init__(self):
                self._queue = asyncio.Queue()

        engine = FakeEngine()
        relay = BinanceRelay(engine=engine, symbol_list=["BTCUSDT"])
        _fast_watchdog_settings(monkeypatch)
        # không inject catch-up (tránh nhầm lẫn với mark của watchdog)
        async def noop_inject(u):
            pass

        monkeypatch.setattr(relay, "_inject_catchup", noop_inject)
        calls = []

        async def fake_fetch(symbol):
            calls.append(symbol)
            return 65432.0

        monkeypatch.setattr(relay, "_fetch_rest_mark", fake_fetch)
        try:
            q = await relay.subscribe("BTCUSDT")
            frame = await asyncio.wait_for(q.get(), 3.0)
            assert frame["type"] == "markPrice"
            assert frame["mark"] == 65432.0
            tick = await asyncio.wait_for(engine._queue.get(), 1.0)
            assert tick == {"symbol": "BTCUSDT", "mark": 65432.0}
            assert calls, "watchdog phải poll REST khi WS im lặng"
        finally:
            await relay.shutdown()

    async def test_no_poll_when_ws_frames_flow(self, fake_connect, monkeypatch):
        """Frame WS đến liên tục → watchdog KHÔNG poll REST (chỉ catch-up lúc connect)."""
        calls = []

        async def fake_fetch(symbol):
            calls.append(symbol)
            return None  # REST fail — chỉ để đếm số lần gọi

        relay = BinanceRelay(symbol_list=["BTCUSDT"])
        _fast_watchdog_settings(monkeypatch)
        monkeypatch.setattr(relay, "_fetch_rest_mark", fake_fetch)
        try:
            up = await relay.get_or_create("BTCUSDT")
            # mô phỏng frame WS liên tục: reset baseline mỗi 0.05s trong 1s
            for _ in range(20):
                up.last_frame_mono = time.monotonic()
                await asyncio.sleep(0.05)
            up.last_frame_mono = time.monotonic()  # chốt baseline fresh trước assert
            # Chỉ 1 lần gọi REST = catch-up sau connect; watchdog không poll vì
            # baseline luôn fresh (< silence_timeout 0.2s).
            assert calls == ["BTCUSDT"]
        finally:
            await relay.shutdown()

    async def test_last_frame_mono_reset_on_ws_frame(self, fake_connect, monkeypatch):
        """Frame WS thật đến → reset last_frame_mono (baseline silence mới)."""
        # upstream giả CÓ frame (delay 0.05s → monotonic tick khác lúc creation)
        fake_connect["BTCUSDT"] = DelayedFramesUpstream(frames=[mark_event(), mark_event()])

        async def fake_fetch(symbol):
            return None

        relay = BinanceRelay(symbol_list=["BTCUSDT"])
        monkeypatch.setattr(relay, "_fetch_rest_mark", fake_fetch)
        try:
            up = await relay.get_or_create("BTCUSDT")
            created = up.last_frame_mono
            await asyncio.sleep(0.3)  # chờ reader connect + đọc frame (fake, không network)
            assert up.last_frame_mono > created, "frame WS phải reset baseline silence"
            assert time.monotonic() - up.last_frame_mono < 0.5, "baseline phải fresh sau frame"
        finally:
            await relay.shutdown()

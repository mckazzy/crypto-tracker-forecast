"""BinanceRelay — fan-out Binance futures markPrice + kline WS streams.

1 upstream connection per symbol (single-flight get_or_create), fanned out to
client queues AND fed to the FuturesEngine queue (independent of clients — the
engine stays alive with 0 connected clients). Frames are normalized
server-side to `{type: 'markPrice'|'kline', ...}` — clients never parse the
raw Binance envelope. Auto-reconnect with exponential backoff + jitter and a
catch-up tick injected from REST mark after reconnect.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field

import websockets

from app.config import settings

logger = logging.getLogger(__name__)

MARK_RE = None  # validate ở route/trước get_or_create (regex ^[A-Z0-9]{4,20}$)

MAX_UPSTREAM_CONNECTIONS = 10


def normalize_mark_price(event: dict) -> dict:
    """Binance markPrice @1s event → relay frame contract."""
    return {
        "type": "markPrice",
        "symbol": event["s"],
        "mark": float(event["p"]),
        "ts": int(event["E"]),
    }


def normalize_kline(event: dict) -> dict:
    """Binance kline event → relay frame contract."""
    k = event["k"]
    return {
        "type": "kline",
        "symbol": event["s"],
        "timeframe": k["i"],
        "open_time": k["t"],
        "close_time": k["T"],
        "open": float(k["o"]),
        "high": float(k["h"]),
        "low": float(k["l"]),
        "close": float(k["c"]),
        "volume": float(k["v"]),
        "is_closed": bool(k["x"]),
    }


def normalize_frame(event: dict) -> dict | None:
    """Normalize 1 raw Binance WS event → relay frame; None nếu không nhận diện."""
    if "data" in event and isinstance(event["data"], dict):  # combined-stream envelope
        event = event["data"]
    if event.get("e") == "markPriceUpdate":
        return normalize_mark_price(event)
    if event.get("e") == "kline":
        return normalize_kline(event)
    return None


def build_futures_stream_url(symbol: str, timeframe: str = "1m") -> str:
    base = settings.binance_futures_ws_base.rstrip("/")
    return f"{base}/stream?streams={symbol.lower()}@markPrice@1s/{symbol.lower()}@kline_{timeframe}"


@dataclass
class _Upstream:
    symbol: str
    refcount: int = 0
    queues: set[asyncio.Queue] = field(default_factory=set)
    task: asyncio.Task | None = None
    watchdog_task: asyncio.Task | None = None
    # Baseline đo WS silence (time.monotonic). Tính từ lúc tạo upstream để bao
    # phủ cả giai đoạn connect/backoff (WS down → watchdog vẫn poll REST).
    # Chỉ được RESET bởi frame THẬT từ WS (không tính frame tự inject).
    last_frame_mono: float = field(default_factory=time.monotonic)


class BinanceRelay:
    def __init__(self, engine=None, symbol_list: list[str] | None = None):
        self.engine = engine
        self.symbol_list = symbol_list or settings.symbol_list
        self._upstreams: dict[str, _Upstream] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    def _validate_symbol(self, symbol: str) -> bool:
        import re

        return bool(re.match(r"^[A-Z0-9]{4,20}$", symbol)) and symbol in self.symbol_list

    async def get_or_create(self, symbol: str) -> _Upstream | None:
        """Single-flight: trả upstream của symbol, tạo nếu chưa có (refcount +1)."""
        symbol = symbol.upper()
        if not self._validate_symbol(symbol):
            return None
        if len(self._upstreams) >= MAX_UPSTREAM_CONNECTIONS:
            raise RuntimeError("too many upstream connections")
        async with self._lock:
            up = self._upstreams.get(symbol)
            if up is None:
                up = _Upstream(symbol=symbol)
                up.task = asyncio.create_task(self._run_upstream(up))
                up.watchdog_task = asyncio.create_task(self._watchdog(up))
                self._upstreams[symbol] = up
            up.refcount += 1
            return up

    def release(self, symbol: str, queue: asyncio.Queue) -> None:
        """Client disconnect: bỏ queue khỏi fan-out, refcount -1, evict nếu hết."""
        async def _do():
            async with self._lock:
                up = self._upstreams.get(symbol)
                if up is None:
                    return
                up.queues.discard(queue)
                up.refcount = max(0, up.refcount - 1)
                # Engine giữ reference vĩnh viễn cho symbol có OPEN position/order —
                # evict chỉ khi không client VÀ không position/order (check qua engine store)
                if up.refcount == 0 and not self._symbol_active(symbol):
                    up.task.cancel()
                    if up.watchdog_task:
                        up.watchdog_task.cancel()
                    self._upstreams.pop(symbol, None)

        # release được gọi từ client disconnect handler (async context)
        return _do()

    def _symbol_active(self, symbol: str) -> bool:
        """Có OPEN position/order cho symbol không (engine keep-alive)."""
        if self.engine is None:
            return False
        store = getattr(self.engine, "store", None)
        if store is None:
            return False
        try:
            if hasattr(store, "get_orders_by_status_all"):
                for o in store.get_orders_by_status_all("OPEN"):
                    if o["symbol"] == symbol:
                        return True
            if hasattr(store, "get_all_open_positions"):
                for p in store.get_all_open_positions(symbol):
                    if p["status"] == "OPEN":
                        return True
        except Exception:
            return False
        return False

    async def subscribe(self, symbol: str) -> asyncio.Queue:
        """Client WS handler: lấy upstream + đăng ký queue fan-out."""
        up = await self.get_or_create(symbol)
        if up is None:
            raise ValueError(f"invalid symbol: {symbol}")
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        up.queues.add(q)
        return q

    async def _run_upstream(self, up: _Upstream) -> None:
        url = build_futures_stream_url(up.symbol)
        backoff = 1.0
        try:
            while not self._closed:
                try:
                    async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                        logger.info("futures ws connected: %s", url)
                        backoff = 1.0
                        # baseline silence tính từ lúc connect (frame WS thật sẽ reset)
                        up.last_frame_mono = time.monotonic()
                        # catch-up: inject 1 tick REST mark ngay sau reconnect (không miss
                        # liquidation window khi vừa kết nối)
                        await self._inject_catchup(up)
                        async for raw in ws:
                            try:
                                event = json.loads(raw)
                                # frame THẬT từ WS → reset watchdog silence baseline
                                up.last_frame_mono = time.monotonic()
                                if "data" in event:  # combined-stream envelope
                                    event = event["data"]
                                frame = normalize_frame(event)
                                if frame is None:
                                    continue
                                self._fanout(up, frame)
                                # engine nhận tick độc lập client
                                if self.engine is not None and frame["type"] == "markPrice":
                                    q = getattr(self.engine, "_queue", None)
                                    if q is not None:
                                        await q.put({"symbol": frame["symbol"], "mark": frame["mark"]})
                            except json.JSONDecodeError:
                                logger.warning("drop non-JSON frame from %s", up.symbol)
                            except Exception as e:  # noqa: BLE001
                                logger.warning("frame handling error %s: %s", up.symbol, e)
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001
                    logger.warning("futures ws disconnected %s (%s), retry in %.1fs", up.symbol, e, backoff)
                    await asyncio.sleep(backoff + random.uniform(0, 0.5))
                    backoff = min(backoff * 2, 60.0)
        finally:
            # reader chết (cancel/evict/closed) → watchdog cũng dừng, tránh poll REST vô chủ
            if up.watchdog_task and up.watchdog_task is not asyncio.current_task():
                up.watchdog_task.cancel()

    async def _fetch_rest_mark(self, symbol: str) -> float | None:
        """GET fapi premiumIndex → markPrice; None nếu REST lỗi (không raise)."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"{settings.binance_futures_rest_base}/fapi/v1/premiumIndex",
                    params={"symbol": symbol},
                )
                r.raise_for_status()
                return float(r.json()["markPrice"])
        except Exception as e:  # noqa: BLE001
            logger.warning("rest mark fetch failed %s: %s", symbol, e)
            return None

    async def _emit_mark(self, up: _Upstream, mark: float) -> None:
        """Fanout frame markPrice + push engine tick — dùng chung catch-up & watchdog."""
        frame = {"type": "markPrice", "symbol": up.symbol, "mark": mark, "ts": 0}
        self._fanout(up, frame)
        if self.engine is not None:
            q = getattr(self.engine, "_queue", None)
            if q is not None:
                await q.put({"symbol": up.symbol, "mark": mark})

    async def _inject_catchup(self, up: _Upstream) -> None:
        """Inject 1 tick từ REST mark (premiumIndex) để không miss liquidation window."""
        mark = await self._fetch_rest_mark(up.symbol)
        if mark is not None:
            await self._emit_mark(up, mark)

    async def _watchdog(self, up: _Upstream) -> None:
        """WS im lặng > silence_timeout → poll REST premiumIndex mỗi rest_poll_interval.

        Chạy song song _run_upstream. Silence đo bằng time.monotonic() trên frame
        THẬT từ WS (reset khi frame đến). Poll REST cho tới khi WS sống lại — bao
        phủ cả lúc WS disconnect/backoff (engine vẫn nhận tick trong lúc chờ).
        """
        silence_timeout = settings.binance_futures_ws_silence_timeout
        poll_interval = settings.binance_futures_rest_poll_interval
        while not self._closed:
            if time.monotonic() - up.last_frame_mono > silence_timeout:
                # im lặng: poll cho tới khi frame WS thật đến (reset) hoặc relay đóng
                while not self._closed and time.monotonic() - up.last_frame_mono > silence_timeout:
                    mark = await self._fetch_rest_mark(up.symbol)
                    if mark is not None:
                        await self._emit_mark(up, mark)
                    await asyncio.sleep(poll_interval)
            await asyncio.sleep(1.0)

    def _fanout(self, up: _Upstream, frame: dict) -> None:
        for q in list(up.queues):
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:
                # drop oldest để giữ realtime
                try:
                    q.get_nowait()
                    q.put_nowait(frame)
                except Exception:
                    pass

    async def shutdown(self) -> None:
        self._closed = True
        async with self._lock:
            for up in self._upstreams.values():
                if up.task:
                    up.task.cancel()
                if up.watchdog_task:
                    up.watchdog_task.cancel()
            self._upstreams.clear()

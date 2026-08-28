import httpx
import pytest

from app.connectors.binance_rest import BinanceRestClient


def make_kline_row(open_ms: int, *, closed: bool = True) -> list:
    """Binance raw kline array format."""
    close_ms = open_ms + 3_600_000 - 1  # 1h candle minus 1ms
    return [
        open_ms,
        "40000.0",
        "40100.0",
        "39900.0",
        "40050.0",
        "100.5",
        close_ms,
        "500000.0",
        1500,
        "60.0",
        "300000.0",
        "0" if closed else "1",
    ]


class FakeTransport(httpx.BaseTransport):
    """httpx mock transport driven by a page-builder function."""

    def __init__(self, pages: dict, requests_log: list | None = None):
        # pages: (start_ms) -> list of raw klines; simple single-page default
        self.pages = pages
        self.requests_log = requests_log if requests_log is not None else []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests_log.append(str(request.url))
        if "/api/v3/ping" in request.url.path:
            return httpx.Response(200, content=b"{}")
        if "klines" in request.url.path:
            start = int(request.url.params["startTime"])
            key = start
            rows = self.pages.get(key, [])
            return httpx.Response(200, json=rows)
        return httpx.Response(404, json={})


@pytest.fixture
def client_factory():
    def _make(pages, log=None):
        transport = FakeTransport(pages, log)
        return BinanceRestClient(transport=transport)

    return _make


def test_ping_ok(client_factory):
    client = client_factory({}, None)
    assert client.ping() is True


def test_geo_block_451_raises_clear_error(client_factory):
    def _geo(request: httpx.Request) -> httpx.Response:
        return httpx.Response(451, json={"code": 0, "msg": "Service unavailable from a restricted location"})

    client = BinanceRestClient(transport=httpx.MockTransport(_geo))
    with pytest.raises(RuntimeError, match="451"):
        client.ping()


def test_fetch_klines_normalization(client_factory):
    rows = [make_kline_row(1_760_000_000_000)]
    client = client_factory({1_760_000_000_000: rows}, None)
    out = client.fetch_klines("BTCUSDT", "1h", start_ms=1_760_000_000_000)
    assert len(out) == 1
    k = out[0]
    assert k["symbol"] == "BTCUSDT"
    assert k["timeframe"] == "1h"
    assert k["open_time"].year == 2025
    assert k["open_time"].tzinfo is not None  # tz-aware UTC
    assert k["close_time"].tzinfo is not None
    assert k["open"] == 40000.0
    assert k["close"] == 40050.0
    assert k["high"] == 40100.0
    assert k["low"] == 39900.0


def test_drop_unclosed_candle(client_factory):
    rows = [
        make_kline_row(1_760_000_000_000),
        make_kline_row(1_760_003_600_000, closed=False),  # still-open last row
    ]
    client = client_factory({1_760_000_000_000: rows}, None)
    out = client.fetch_klines("BTCUSDT", "1h", start_ms=1_760_000_000_000)
    assert len(out) == 1
    assert out[0]["open_time"].timestamp() * 1000 == 1_760_000_000_000


def test_pagination(client_factory):
    # two pages of 1000 each
    page1 = [make_kline_row(1_760_000_000_000 + i * 3_600_000) for i in range(1000)]
    page2 = [make_kline_row(1_760_000_000_000 + (1000 + i) * 3_600_000) for i in range(1000)]
    log: list[str] = []
    client = client_factory(
        {
            1_760_000_000_000: page1,
            1_760_000_000_000 + 1000 * 3_600_000: page2,
            1_760_000_000_000 + 2000 * 3_600_000: [],
        },
        log,
    )
    out = client.fetch_klines("BTCUSDT", "1h", start_ms=1_760_000_000_000)
    assert len(out) == 2000
    # boundary: no loss / no duplicate across page seam
    times = [k["open_time"].timestamp() * 1000 for k in out]
    assert len(set(times)) == 2000
    assert times == sorted(times)


def test_pagination_boundary_overlap(client_factory):
    """Server returns an overlapping row at the seam — client must dedupe."""
    page1 = [make_kline_row(1_760_000_000_000 + i * 3_600_000) for i in range(1000)]
    # page2 starts with a repeat of page1's last candle
    page2 = [make_kline_row(1_760_000_000_000 + 999 * 3_600_000)] + [
        make_kline_row(1_760_000_000_000 + (1000 + i) * 3_600_000) for i in range(10)
    ]
    client = client_factory(
        {
            1_760_000_000_000: page1,
            1_760_000_000_000 + 999 * 3_600_000: page2,
            1_760_000_000_000 + 2009 * 3_600_000: [],
        },
        None,
    )
    out = client.fetch_klines("BTCUSDT", "1h", start_ms=1_760_000_000_000)
    times = [k["open_time"].timestamp() * 1000 for k in out]
    assert len(times) == len(set(times))  # no duplicates


def test_get_ticker_price():
    def _handler(request: httpx.Request) -> httpx.Response:
        if "/api/v3/ticker/price" in request.url.path:
            return httpx.Response(200, json={"symbol": "BTCUSDT", "price": "68540.25"})
        return httpx.Response(404, json={})

    client = BinanceRestClient(transport=httpx.MockTransport(_handler))
    price = client.get_ticker_price("BTCUSDT")
    assert price == 68540.25


def test_fetch_recent_klines():
    row = make_kline_row(1_760_000_000_000, closed=False)

    def _handler(request: httpx.Request) -> httpx.Response:
        if "/api/v3/klines" in request.url.path:
            return httpx.Response(200, json=[row])
        return httpx.Response(404, json={})

    client = BinanceRestClient(transport=httpx.MockTransport(_handler))
    klines = client.fetch_recent_klines("BTCUSDT", "1h", limit=5)
    assert len(klines) == 1
    assert klines[0]["close"] == 40050.0

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.connectors.binance_rest import BinanceRestClient
from app.ingest.backfill import BackfillRunner
from app.storage.duckdb_store import DuckDBStore


def raw_row(open_ms: int) -> list:
    return [
        open_ms,
        "40000.0",
        "40100.0",
        "39900.0",
        "40050.0",
        "100.5",
        open_ms + 3_600_000 - 1,
        "500000.0",
        1500,
        "60.0",
        "300000.0",
        "0",
    ]


class PageTransport(httpx.BaseTransport):
    """Serves klines Binance-style: rows with open_time >= startTime (up to 1000),
    drawn from one flat list per instance."""

    def __init__(self, all_rows: list, server_time_ms: int | None = None, page_size: int = 1000):
        self.all_rows = all_rows
        self.server_time_ms = server_time_ms
        self.page_size = page_size

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/ping"):
            return httpx.Response(200, content=b"{}")
        if request.url.path.endswith("/time"):
            st = self.server_time_ms
            if st is None:
                st = self.all_rows[-1][0] + 3_600_000 if self.all_rows else 0
            return httpx.Response(200, json={"serverTime": st})
        start = int(request.url.params["startTime"])
        end = int(request.url.params.get("endTime", 9_999_999_999_999))
        rows = [r for r in self.all_rows if start <= r[0] <= end][: self.page_size]
        return httpx.Response(200, json=rows)


class ExplodingTransport(PageTransport):
    """Raises after serving any page whose startTime >= explode_after_ms."""

    def __init__(self, all_rows: list, explode_after_ms: int, **kw):
        super().__init__(all_rows, **kw)
        self.explode_after_ms = explode_after_ms
        self.exploded = False

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/klines"):
            start = int(request.url.params.get("startTime", 0))
            if start >= self.explode_after_ms:
                self.exploded = True
                raise httpx.ConnectError("boom")
        return super().handle_request(request)


@pytest.fixture
def store(tmp_duckdb) -> DuckDBStore:
    return DuckDBStore(tmp_duckdb)


def make_runner(store: DuckDBStore, client: BinanceRestClient) -> BackfillRunner:
    return BackfillRunner(store=store, client=client)


def test_backfill_inserts_all_candles(store):
    t0 = 1_760_000_000_000
    rows = [raw_row(t0 + i * 3_600_000) for i in range(25)]
    client = BinanceRestClient(transport=PageTransport(rows, server_time_ms=t0 + 26 * 3_600_000))
    runner = make_runner(store, client)
    inserted = runner.backfill("BTCUSDT", ["1h"], days=2)
    assert inserted == 25
    assert store.count("BTCUSDT", "1h") == 25


def test_backfill_resume_interrupted(store):
    """First run dies after page 1; --resume continues from checkpoint → zero-gap."""
    t0 = 1_760_000_000_000
    hour = 3_600_000
    all_rows = [raw_row(t0 + i * hour) for i in range(150)]
    explode_after = t0 + 100 * hour

    # Run 1: dies mid-way after 2 pages (page_size=60 → 120 served, explode at row 100)
    client1 = BinanceRestClient(
        transport=ExplodingTransport(
            all_rows, explode_after_ms=explode_after, server_time_ms=t0 + 151 * hour, page_size=60
        )
    )
    runner1 = make_runner(store, client1)
    with pytest.raises(Exception):
        runner1.backfill("BTCUSDT", ["1h"], days=7)
    count_run1 = store.count("BTCUSDT", "1h")
    assert count_run1 > 0
    cursor = store.get_backfill_cursor("BTCUSDT", "1h")
    assert cursor is not None

    # Run 2 (resume): full data available, continues from cursor
    client2 = BinanceRestClient(
        transport=PageTransport(all_rows, server_time_ms=t0 + 151 * hour, page_size=60)
    )
    runner2 = make_runner(store, client2)
    runner2.backfill("BTCUSDT", ["1h"], days=7, resume=True)

    count = store.count("BTCUSDT", "1h")
    assert count == 150
    rows = store.get_klines("BTCUSDT", "1h", limit=1000)
    times = [r["open_time"] for r in rows]
    expected = [datetime.fromtimestamp((t0 + i * hour) / 1000, tz=UTC) for i in range(150)]
    assert sorted(times) == expected  # zero gap, no duplicates


def test_backfill_idempotent_rerun(store):
    t0 = 1_760_000_000_000
    rows = [raw_row(t0 + i * 3_600_000) for i in range(30)]
    client = BinanceRestClient(transport=PageTransport(rows, server_time_ms=t0 + 31 * 3_600_000))
    runner = make_runner(store, client)
    runner.backfill("BTCUSDT", ["1h"], days=2)
    first = store.count("BTCUSDT", "1h")
    assert first == 30
    runner.backfill("BTCUSDT", ["1h"], days=2)
    assert store.count("BTCUSDT", "1h") == first

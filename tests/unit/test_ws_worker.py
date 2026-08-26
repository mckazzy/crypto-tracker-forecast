"""Tests for the realtime kline WS worker (Phase 3).

The worker is structured as a pure message-pipeline (`handle_ws_message`)
plus a thin network loop, so tests drive JSON frames without real sockets.
"""

import json
from datetime import UTC, datetime

import pytest

from app.ingest.ws_worker import KlineStreamNormalizer, handle_ws_message


def kline_event(symbol="BTCUSDT", interval="1h", open_ms=None, closed=True):
    open_ms = open_ms or 1_760_000_000_000
    return {
        "e": "kline",
        "s": symbol,
        "k": {
            "t": open_ms,
            "T": open_ms + 3_600_000 - 1,
            "s": symbol,
            "i": interval,
            "o": "40000.0",
            "c": "40100.0",
            "h": "40200.0",
            "l": "39900.0",
            "v": "123.4",
            "V": "60.0",
            "n": 500,
            "x": closed,
        },
    }


class TestNormalizer:
    def test_normalize_closed_kline(self):
        n = KlineStreamNormalizer()
        k = n.normalize(kline_event())
        assert k["symbol"] == "BTCUSDT"
        assert k["timeframe"] == "1h"
        assert k["open_time"].tzinfo is not None
        assert k["close"] == 40100.0
        assert k["trades"] == 500
        assert k["is_closed"] is True

    def test_normalize_open_kline(self):
        n = KlineStreamNormalizer()
        k = n.normalize(kline_event(closed=False))
        assert k["is_closed"] is False


class TestHandleMessage:
    def test_valid_message_yields_kline(self):
        n = KlineStreamNormalizer()
        out = handle_ws_message(json.dumps(kline_event()), n)
        assert len(out) == 1

    def test_invalid_json_ignored(self):
        n = KlineStreamNormalizer()
        out = handle_ws_message("not-json{", n)
        assert out == []

    def test_non_kline_event_ignored(self):
        n = KlineStreamNormalizer()
        msg = json.dumps({"e": "aggTrade", "s": "BTCUSDT"})
        assert handle_ws_message(msg, n) == []

    def test_combined_stream_envelope(self):
        """Combined streams wrap payload in {"stream": ..., "data": ...}."""
        n = KlineStreamNormalizer()
        msg = json.dumps({"stream": "btcusdt@kline_1h", "data": kline_event()})
        out = handle_ws_message(msg, n)
        assert len(out) == 1
        assert out[0]["symbol"] == "BTCUSDT"

    def test_open_candle_not_persisted_but_returned_flagged(self):
        n = KlineStreamNormalizer()
        out = handle_ws_message(json.dumps(kline_event(closed=False)), n)
        assert len(out) == 1
        assert out[0]["is_closed"] is False

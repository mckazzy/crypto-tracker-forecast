import pytest
from app.trading.scoring import score_forecast


def test_score_forecast_long_positive_and_100():
    # Entry = 100, TP = 110 (100% = 10 points)
    # Price moved up 5 points -> +50%
    score_half = score_forecast("LONG", entry=100.0, tp=110.0, sl=95.0, exit_price=105.0)
    assert score_half == 50.0

    # Price reached TP -> +100%
    score_full = score_forecast("LONG", entry=100.0, tp=110.0, sl=95.0, exit_price=110.0)
    assert score_full == 100.0

    # Price exceeded TP -> +150%
    score_surpassed = score_forecast("LONG", entry=100.0, tp=110.0, sl=95.0, exit_price=115.0)
    assert score_surpassed == 150.0


def test_score_forecast_long_negative():
    # Entry = 100, TP = 110
    # Price moved down 5 points (opposite direction) -> -50%
    score_down = score_forecast("LONG", entry=100.0, tp=110.0, sl=95.0, exit_price=95.0)
    assert score_down == -50.0

    # Price moved down 10 points -> -100%
    score_down_100 = score_forecast("LONG", entry=100.0, tp=110.0, sl=95.0, exit_price=90.0)
    assert score_down_100 == -100.0


def test_score_forecast_short_positive_and_100():
    # Entry = 100, TP = 90 (100% = 10 points)
    # Price moved down 5 points -> +50%
    score_half = score_forecast("SHORT", entry=100.0, tp=90.0, sl=105.0, exit_price=95.0)
    assert score_half == 50.0

    # Price reached TP -> +100%
    score_full = score_forecast("SHORT", entry=100.0, tp=90.0, sl=105.0, exit_price=90.0)
    assert score_full == 100.0

    # Price surpassed TP -> +120%
    score_surpassed = score_forecast("SHORT", entry=100.0, tp=90.0, sl=105.0, exit_price=88.0)
    assert score_surpassed == 120.0


def test_score_forecast_short_negative():
    # Entry = 100, TP = 90
    # Price moved up 5 points (opposite direction) -> -50%
    score_up = score_forecast("SHORT", entry=100.0, tp=90.0, sl=105.0, exit_price=105.0)
    assert score_up == -50.0


def test_score_forecast_no_tp_fallback():
    # Long without TP: (105 - 100) / 100 * 100 = +5.0%
    assert score_forecast("LONG", entry=100.0, tp=None, sl=None, exit_price=105.0) == 5.0
    # Short without TP: (100 - 95) / 100 * 100 = +5.0%
    assert score_forecast("SHORT", entry=100.0, tp=None, sl=None, exit_price=95.0) == 5.0


def test_score_forecast_invalid_inputs():
    assert score_forecast("LONG", entry=0.0, tp=110.0, sl=90.0, exit_price=105.0) == 0.0
    assert score_forecast("FLAT", entry=100.0, tp=110.0, sl=90.0, exit_price=105.0) == 0.0


def test_exit_price_at_live_ticker():
    from datetime import UTC, datetime
    from unittest.mock import MagicMock
    from app.trading.scoring import exit_price_at

    mock_client = MagicMock()
    mock_client.get_ticker_price.return_value = 97500.50
    mock_store = MagicMock()

    now = datetime.now(UTC)
    price = exit_price_at(mock_store, "BTCUSDT", "4h", valid_until=now, client=mock_client)
    assert price == 97500.50
    mock_client.get_ticker_price.assert_called_with("BTCUSDT")


def test_exit_price_at_binance_klines():
    from datetime import UTC, datetime, timedelta
    from unittest.mock import MagicMock
    from app.trading.scoring import exit_price_at

    past = datetime.now(UTC) - timedelta(hours=8)
    mock_client = MagicMock()
    mock_client.get_ticker_price.return_value = None
    mock_client.fetch_recent_klines.return_value = [
        {"open_time": past - timedelta(hours=4), "close_time": past, "close": 96200.0, "symbol": "BTCUSDT", "timeframe": "4h"}
    ]
    mock_store = MagicMock()

    price = exit_price_at(mock_store, "BTCUSDT", "4h", valid_until=past, client=mock_client)
    assert price == 96200.0
    mock_store.upsert_klines.assert_called_once()


def test_exit_price_at_store_fallback():
    from datetime import UTC, datetime, timedelta
    from unittest.mock import MagicMock
    from app.trading.scoring import exit_price_at

    past = datetime.now(UTC) - timedelta(hours=12)
    mock_client = MagicMock()
    mock_client.get_ticker_price.side_effect = RuntimeError("network error")
    mock_client.fetch_recent_klines.side_effect = RuntimeError("network error")

    mock_store = MagicMock()
    mock_store.get_klines.return_value = [
        {"open_time": past - timedelta(hours=4), "close_time": past, "close": 94800.0}
    ]

    price = exit_price_at(mock_store, "BTCUSDT", "4h", valid_until=past, client=mock_client)
    assert price == 94800.0

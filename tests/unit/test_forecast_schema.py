from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.forecast.schema import Signal, SignalDirection, SignalStatus


def make_signal(**overrides) -> Signal:
    base = {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "direction": "LONG",
        "probability": 0.63,
        "entry": 67200.0,
        "take_profit": [68500.0, 69200.0],
        "stop_loss": 66100.0,
        "rr_ratio": 1.8,
        "model": "test@v1",
    }
    base.update(overrides)
    return Signal(**base)


class TestSignalValidation:
    def test_valid_signal(self):
        s = make_signal()
        assert s.direction == SignalDirection.LONG
        assert s.status == SignalStatus.OK
        assert s.version == "1.0"

    def test_invalid_direction_rejected(self):
        with pytest.raises(ValidationError):
            make_signal(direction="SIDEWAYS")

    def test_probability_range(self):
        with pytest.raises(ValidationError):
            make_signal(probability=1.5)

    def test_negative_take_profit_rejected(self):
        with pytest.raises(ValidationError):
            make_signal(take_profit=[-100.0])

    def test_negative_entry_rejected(self):
        with pytest.raises(ValidationError):
            make_signal(entry=-10.0)

    def test_json_mode_serializable(self):
        s = make_signal(valid_until=datetime(2026, 8, 26, tzinfo=UTC))
        d = s.model_dump(mode="json")
        assert isinstance(d["valid_until"], str)
        assert d["direction"] == "LONG"
        assert isinstance(d["take_profit"], list)

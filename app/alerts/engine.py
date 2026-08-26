from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from app.alerts.telegram import TelegramSender, build_alert_message
from app.config import settings

logger = logging.getLogger(__name__)


class AlertEngine:
    """Dispatch signal → alert với dedup (không spam signal trùng)."""

    def __init__(self, store, sender: TelegramSender | None = None):
        self.store = store
        self.sender = sender or TelegramSender(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )
        self._last_signal: dict | None = None
        self._last_sent_at: datetime | None = None

    def should_alert(self, signal: dict) -> bool:
        """Dedup: alert nếu direction đổi, hoặc entry/TP/SL đổi > 0.5%, hoặc sau 10 phút."""
        if self._last_signal is None:
            return True
        if signal.get("direction") != self._last_signal.get("direction"):
            return True
        for key in ("entry", "sl"):
            a = self._last_signal.get(key)
            b = signal.get(key)
            if a and b and abs(b - a) / a > 0.005:
                return True
        if self._last_sent_at is None or (datetime.now(UTC) - self._last_sent_at) > timedelta(minutes=10):
            return True
        return False

    def dispatch(self, signal: dict) -> dict:
        """Gửi alert (telegram → webhook fallback), lưu history. Returns alert record."""
        channel = "webhook"
        status = "sent"
        if self.sender.enabled:
            msg = build_alert_message(
                symbol=signal["symbol"],
                timeframe=signal["timeframe"],
                direction=signal["direction"],
                entry=signal.get("entry") or 0.0,
                tp=signal.get("take_profit") or [],
                sl=signal.get("stop_loss") or 0.0,
                model=signal.get("model") or "unknown",
            )
            ok = self.sender.send(msg)
            if ok:
                channel = "telegram"
                status = "sent"
            else:
                status = "failed"  # fallback: vẫn lưu webhook
        record = {
            "symbol": signal["symbol"],
            "timeframe": signal["timeframe"],
            "direction": signal["direction"],
            "entry": signal.get("entry"),
            "tp": "/".join(str(t) for t in (signal.get("take_profit") or [])),
            "sl": signal.get("stop_loss"),
            "model": signal.get("model"),
            "channel": channel,
            "status": status,
        }
        self.store.save_alert(record)
        self._last_signal = signal
        self._last_sent_at = datetime.now(UTC)
        return record

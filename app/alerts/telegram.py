from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


def build_alert_message(
    symbol: str,
    timeframe: str,
    direction: str,
    entry: float,
    tp: list[float],
    sl: float,
    model: str,
) -> str:
    """Template alert: BTCUSDT 1h LONG @ 67200 · TP 68500/69200 · SL 66100 · model=x"""
    tp_str = "/".join(f"{t:.2f}" for t in tp) if tp else "-"
    return (
        f"{symbol} {timeframe} {direction} @ {entry:.2f} · "
        f"TP {tp_str} · SL {sl:.2f} · model={model}"
    )


class TelegramSender:
    """Telegram Bot API sender (httpx, mockable transport)."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        transport: httpx.BaseTransport | None = None,
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, message: str) -> bool:
        if not self.enabled:
            logger.warning("telegram not configured — alert not sent")
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": message}
        try:
            with httpx.Client(timeout=15.0, transport=self._transport) as client:
                resp = client.post(url, json=payload)
            if resp.status_code == 200 and resp.json().get("ok"):
                return True
            logger.warning("telegram send failed: HTTP %s", resp.status_code)
            return False
        except httpx.HTTPError as e:
            logger.warning("telegram send error: %s", e)
            return False

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

from app.config import settings
from app.forecast.provider import ForecastProvider

logger = logging.getLogger(__name__)


class ProviderEntry:
    def __init__(self, provider: ForecastProvider):
        self.provider = provider
        self.last_forecast_at: datetime | None = None
        self.last_error: str | None = None
        self.forecast_count = 0


class ProviderRegistry:
    """Thread-safe registry của mọi provider + health tracking."""

    def __init__(self):
        self._lock = threading.Lock()
        self._entries: dict[str, ProviderEntry] = {}

    def register(self, provider: ForecastProvider) -> None:
        with self._lock:
            self._entries[provider.name] = ProviderEntry(provider)

    def get(self, name: str) -> ForecastProvider | None:
        with self._lock:
            entry = self._entries.get(name)
            return entry.provider if entry else None

    def list(self) -> list[str]:
        with self._lock:
            return sorted(self._entries)

    def health(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "name": name,
                    "last_forecast_at": entry.last_forecast_at.isoformat()
                    if entry.last_forecast_at
                    else None,
                    "last_error": entry.last_error,
                    "forecast_count": entry.forecast_count,
                }
                for name, entry in sorted(self._entries.items())
            ]

    def record_success(self, name: str) -> None:
        with self._lock:
            entry = self._entries.get(name)
            if entry:
                entry.last_forecast_at = datetime.now(UTC)
                entry.last_error = None
                entry.forecast_count += 1

    def record_error(self, name: str, error: str) -> None:
        with self._lock:
            entry = self._entries.get(name)
            if entry:
                entry.last_error = error


registry = ProviderRegistry()


def register_defaults() -> None:
    """Đăng ký baselines mặc định + AI provider (nếu enabled) — gọi lúc startup."""
    from app.forecast.baselines import EwmaVolProvider, RandomWalkProvider

    registry.register(RandomWalkProvider())
    registry.register(EwmaVolProvider())

    if settings.ai_enabled:
        from app.forecast.ai_provider import AIProvider

        registry.register(AIProvider())
        logger.info("AI provider registered (model=%s)", settings.ai_model)

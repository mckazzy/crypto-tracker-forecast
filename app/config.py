from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    binance_rest_base: str = "https://api.binance.com"
    binance_ws_base: str = "wss://stream.binance.com:9443"
    data_dir: str = "./data"
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    symbols: str = "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT"
    timeframes: str = "5m,15m,1h,4h,1d,1w"

    # AI provider (SP2 Phase 4) — OpenRouter (OpenAI-compatible)
    ai_enabled: bool = False
    ai_base_url: str = "https://openrouter.ai/api/v1"
    ai_api_key: str = ""
    ai_model: str = "deepseek/deepseek-v4-flash-0731"
    ai_daily_token_budget: int = 200_000

    # Curated model whitelist hiển thị trên front-end (OpenRouter model IDs, đã xác minh tồn tại 08/2026)
    ai_model_choices: str = (
        "deepseek/deepseek-v4-flash-0731,"
        "qwen/qwen3.8-flash,"
        "z-ai/glm-5.3-flash,"
        "openai/gpt-5.6-luna,"
        "google/gemini-3.7-flash,"
        "deepseek/deepseek-v4-pro-0813,"
        "anthropic/claude-opus-5"
    )

    # Alerts (SP4)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    feedback_min_signals: int = 10

    # Futures demo exchange (SP5) — auth + Binance futures WS
    jwt_secret: str = ""  # fail-fast: phải set, >= 32 chars (validator bên dưới)
    jwt_expire_minutes: int = 60 * 24  # 24h
    binance_futures_ws_base: str = "wss://fstream.binance.com"
    # Futures relay fallback (SP5 follow-up): WS im lặng > silence_timeout →
    # poll REST premiumIndex mỗi rest_poll_interval giây. Base riêng cho fapi —
    # binance_rest_base (https://api.binance.com) là SPOT, /fapi/v1/* không
    # hợp lệ trên đó (QA ghi nhận fapi REST không bị chặn, chỉ WS streams drop).
    binance_futures_rest_base: str = "https://fapi.binance.com"
    binance_futures_ws_silence_timeout: float = 5.0
    binance_futures_rest_poll_interval: float = 3.0

    @model_validator(mode="after")
    def _validate_jwt_secret(self) -> "Settings":
        if len(self.jwt_secret) < 32:
            raise ValueError(
                "jwt_secret must be set in .env and be at least 32 characters (fail-closed)"
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def symbol_list(self) -> list[str]:
        return [s.strip() for s in self.symbols.split(",") if s.strip()]

    @property
    def timeframe_list(self) -> list[str]:
        return [t.strip() for t in self.timeframes.split(",") if t.strip()]

    @property
    def ai_model_choice_list(self) -> list[str]:
        return [m.strip() for m in self.ai_model_choices.split(",") if m.strip()]

    @property
    def ai_model_is_choice(self) -> bool:
        return self.ai_model in self.ai_model_choice_list

    @property
    def db_path(self) -> str:
        import os

        return os.path.join(self.data_dir, "market.duckdb")


settings = Settings()

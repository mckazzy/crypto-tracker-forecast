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

    # AI provider (SP2 Phase 4)
    ai_enabled: bool = False
    ai_base_url: str = "http://localhost:20128/v1"
    ai_api_key: str = ""
    ai_model: str = ""
    ai_daily_token_budget: int = 200_000

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
    def db_path(self) -> str:
        import os

        return os.path.join(self.data_dir, "market.duckdb")


settings = Settings()

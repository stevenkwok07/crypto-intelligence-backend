import os
from dataclasses import dataclass

@dataclass
class Settings:
    coinpaprika_base: str = os.getenv("COINPAPRIKA_BASE", "https://api.coinpaprika.com/v1")
    binance_base: str = os.getenv("BINANCE_BASE", "https://data-api.binance.vision")
    cors_origins: list = None
    request_timeout: float = float(os.getenv("REQUEST_TIMEOUT", "20"))

    def __post_init__(self):
        raw = os.getenv("CORS_ORIGINS", "*")
        self.cors_origins = ["*"] if raw == "*" else [x.strip() for x in raw.split(",")]

settings = Settings()

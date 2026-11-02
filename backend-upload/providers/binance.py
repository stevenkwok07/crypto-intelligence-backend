from config import settings
from providers.http import get_json


async def get_klines(symbol: str, interval: str, limit: int = 500):
    return await get_json(
        f"{settings.binance_base}/api/v3/klines",
        {"symbol": symbol.upper(), "interval": interval, "limit": min(limit, 1000)},
    )


async def get_book_ticker(symbol: str):
    return await get_json(
        f"{settings.binance_base}/api/v3/ticker/bookTicker",
        {"symbol": symbol.upper()},
    )


async def get_depth(symbol: str, limit: int = 100):
    return await get_json(
        f"{settings.binance_base}/api/v3/depth",
        {"symbol": symbol.upper(), "limit": limit},
    )

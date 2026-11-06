from config import settings
from providers.http import get_json

import time

_TICKER_CACHE = {"data": None, "fetched_at": 0.0}
_TICKER_TTL_SECONDS = 300


async def get_tickers(limit: int = 100):
    """Fetch tickers with a 5-minute cache; serve the last good list if the provider errors."""
    now = time.monotonic()
    cached = _TICKER_CACHE["data"]
    if cached is not None and now - _TICKER_CACHE["fetched_at"] < _TICKER_TTL_SECONDS:
        return cached[:limit]
    try:
        data = await get_json(f"{settings.coinpaprika_base}/tickers")
    except Exception:
        if cached is not None:
            return cached[:limit]
        raise
    _TICKER_CACHE["data"] = data
    _TICKER_CACHE["fetched_at"] = now
    return data[:limit]

async def get_coin(coin_id: str):
    return await get_json(f"{settings.coinpaprika_base}/coins/{coin_id}")

async def get_ohlcv_daily(coin_id: str, limit: int = 365):
    # CoinPaprika free historical OHLCV endpoint. Provider availability and limits can change.
    import datetime
    end = datetime.datetime.now(datetime.timezone.utc).date()
    start = end - datetime.timedelta(days=limit)
    return await get_json(
        f"{settings.coinpaprika_base}/coins/{coin_id}/ohlcv/historical",
        {"start": start.isoformat(), "end": end.isoformat()}
    )

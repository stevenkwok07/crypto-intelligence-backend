from config import settings
from providers.http import get_json

async def get_tickers(limit: int = 100):
    data = await get_json(f"{settings.coinpaprika_base}/tickers")
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

from services.market import get_coin_universe

async def scan_coins(limit=30):
    universe = await get_coin_universe(limit)
    # Scanner foundation returns the eligible universe. Full multi-timeframe analysis
    # is added after provider candle coverage and rate limits are validated.
    return {
        "count": universe["count"],
        "status": "UNIVERSE_ONLY",
        "assets": universe["assets"],
        "note": "This is a universe preview, not a scored scanner yet."
    }

"""Public Kraken Spot OHLC provider used when Binance data is unavailable."""
import asyncio
import time

from providers.http import get_json

BASE_URL = "https://api.kraken.com/0/public"
INTERVALS = {"1h": 60, "4h": 240, "1d": 1440}
_pair_cache = None
_pair_cache_at = 0.0
_pair_lock = asyncio.Lock()


def _normalized_asset(code):
    code = str(code or "").upper()
    return {"XBT": "BTC", "XXBT": "BTC", "XDG": "DOGE", "XXDG": "DOGE"}.get(code, code)


async def _usd_pairs():
    global _pair_cache, _pair_cache_at
    if _pair_cache is not None and time.monotonic() - _pair_cache_at < 3600:
        return _pair_cache
    async with _pair_lock:
        if _pair_cache is not None and time.monotonic() - _pair_cache_at < 3600:
            return _pair_cache
        payload = await get_json(f"{BASE_URL}/AssetPairs")
        if payload.get("error"):
            raise RuntimeError(f"Kraken AssetPairs error: {payload['error']}")
        pairs = {}
        for pair in payload.get("result", {}).values():
            if pair.get("quote") not in ("ZUSD", "USD") or pair.get("status") != "online":
                continue
            wsname = pair.get("wsname", "")
            if "/" not in wsname:
                continue
            base, quote = wsname.split("/", 1)
            if quote != "USD":
                continue
            symbol = _normalized_asset(base)
            pairs.setdefault(symbol, pair.get("altname") or pair.get("wsname"))
        _pair_cache = pairs
        _pair_cache_at = time.monotonic()
        return pairs


async def get_klines(symbol: str, interval: str, limit: int = 500):
    interval = interval.lower()
    if interval not in INTERVALS:
        raise ValueError(f"Unsupported Kraken interval: {interval}")
    asset = symbol.upper()
    for suffix in ("USDT", "USD"):
        if asset.endswith(suffix):
            asset = asset[:-len(suffix)]
            break
    pairs = await _usd_pairs()
    pair = pairs.get(_normalized_asset(asset))
    if not pair:
        raise ValueError(f"Kraken Spot has no USD market for {asset}")
    payload = await get_json(
        f"{BASE_URL}/OHLC",
        {"pair": pair, "interval": INTERVALS[interval]},
    )
    if payload.get("error"):
        raise RuntimeError(f"Kraken OHLC error for {pair}: {payload['error']}")
    result = payload.get("result", {})
    rows = next((value for key, value in result.items() if key != "last"), [])
    rows = rows[-min(max(int(limit), 1), 720):]
    interval_ms = INTERVALS[interval] * 60 * 1000
    normalized = []
    for row in rows:
        if len(row) < 8:
            continue
        open_ms = int(float(row[0]) * 1000)
        close = float(row[4])
        volume = float(row[6])
        normalized.append([
            open_ms, row[1], row[2], row[3], row[4], row[6],
            open_ms + interval_ms - 1, str(close * volume), int(row[7]),
            "0", "0", "0",
        ])
    if not normalized:
        raise RuntimeError(f"Kraken returned no OHLC candles for {pair}")
    return normalized


import asyncio

from services.market import get_coin_universe
from services.analyzer import analyze_coin
from engine.allocation import build_simulated_allocation


STABLECOIN_SYMBOLS = {
    "USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE", "USDD", "PYUSD", "BUSD",
    "USDS", "USD1", "RLUSD", "USDP", "GUSD", "FRAX", "LUSD", "EURC", "EURT",
    "USDB", "USD0", "SUSDE", "BFUSD", "USDF", "USDTB", "USDG",
}


def _is_stablecoin(asset):
    symbol = str(asset.get("symbol") or "").strip().upper()
    return symbol in STABLECOIN_SYMBOLS


async def scan_coins(limit=10):
    """Score a bounded slice of the largest listed non-stablecoin assets for research review."""
    requested = min(max(int(limit), 1), 10)
    # Fetch extra tickers so stablecoins can be skipped without shrinking the scan.
    raw_universe = await get_coin_universe(requested + 15)
    universe = {
        "assets": [
            asset for asset in raw_universe.get("assets", []) if not _is_stablecoin(asset)
        ][:requested]
    }
    semaphore = asyncio.Semaphore(2)

    async def analyze(asset):
        async with semaphore:
            try:
                result = await analyze_coin(asset["id"])
                return {
                    "asset": asset,
                    "technical_score": result.get("technical_score"),
                    "classification": result.get("classification", "INSUFFICIENT_DATA"),
                    "status": result.get("status", "MULTI_TIMEFRAME_INCOMPLETE"),
                    "timeframe_alignment": result.get("timeframe_alignment"),
                    "recommendation": result.get("recommendation"),
                    "timeframes": result.get("timeframes"),
                }
            except Exception as exc:
                return {
                    "asset": asset,
                    "technical_score": None,
                    "classification": "INSUFFICIENT_DATA",
                    "status": "ANALYSIS_ERROR",
                    "error": str(exc),
                }

    results = await asyncio.gather(*(analyze(asset) for asset in universe["assets"]))
    results.sort(
        key=lambda item: item.get("technical_score")
        if item.get("technical_score") is not None else -1,
        reverse=True,
    )
    candidates = []
    for item in results:
        recommendation = item.get("recommendation")
        if not isinstance(recommendation, dict):
            continue
        if (
            recommendation.get("status") == "PROVISIONAL"
            and recommendation.get("research_setup") in ("LONG_CANDIDATE", "LONG_CANDIDATE_REDUCED")
        ):
            candidates.append(item)
    allocation = build_simulated_allocation(results)
    return {
        "count": len(results),
        "status": "RESEARCH_SCAN",
        "source": "CoinPaprika universe + Kraken Spot OHLC",
        "assets": results,
        "research_candidates": len(candidates),
        "system_recommendation": allocation,
        "note": "Provisional technical simulation. Backtest with fees/slippage and market-liquidity validation are incomplete; use as research, not a guaranteed return or order instruction.",
    }


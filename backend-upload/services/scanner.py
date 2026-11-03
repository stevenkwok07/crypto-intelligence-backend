import asyncio

from services.market import get_coin_universe
from services.analyzer import analyze_coin
from engine.allocation import build_simulated_allocation


async def scan_coins(limit=10):
    """Score a bounded slice of the largest listed assets for research review."""
    requested = min(max(int(limit), 1), 10)
    universe = await get_coin_universe(requested)
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
    candidates = [
        item for item in results
        if item.get("recommendation", {}).get("status") == "PROVISIONAL"
        and item.get("recommendation", {}).get("research_setup") == "LONG_CANDIDATE"
    ]
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


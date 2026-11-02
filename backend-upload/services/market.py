from providers.coinpaprika import get_tickers

async def get_market_overview():
    tickers = await get_tickers(100)
    valid = [x for x in tickers if x.get("quotes", {}).get("USD", {}).get("market_cap") is not None]
    total_cap = sum(x["quotes"]["USD"]["market_cap"] for x in valid)
    return {
        "source": "CoinPaprika",
        "assets_sampled": len(valid),
        "sample_market_cap_usd": total_cap,
        "note": "Sample based on first 100 provider tickers, not total crypto market capitalization."
    }

async def get_coin_universe(limit=100):
    tickers = await get_tickers(limit)
    result = []
    for item in tickers:
        usd = item.get("quotes", {}).get("USD", {})
        result.append({
            "id": item.get("id"),
            "symbol": item.get("symbol"),
            "name": item.get("name"),
            "rank": item.get("rank"),
            "price_usd": usd.get("price"),
            "volume_24h": usd.get("volume_24h"),
            "market_cap": usd.get("market_cap"),
            "change_24h": usd.get("percent_change_24h"),
            "source": "CoinPaprika"
        })
    return {"count": len(result), "assets": result}

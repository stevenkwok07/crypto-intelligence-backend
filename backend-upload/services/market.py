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

# Used only when CoinPaprika is unreachable and nothing is cached: large, liquid
# assets with Kraken USD markets, roughly in market-cap order.
FALLBACK_UNIVERSE = [
    ("btc-bitcoin", "BTC", "Bitcoin"), ("eth-ethereum", "ETH", "Ethereum"),
    ("xrp-xrp", "XRP", "XRP"), ("sol-solana", "SOL", "Solana"),
    ("doge-dogecoin", "DOGE", "Dogecoin"), ("ada-cardano", "ADA", "Cardano"),
    ("trx-tron", "TRX", "TRON"), ("link-chainlink", "LINK", "Chainlink"),
    ("xlm-stellar", "XLM", "Stellar"), ("bch-bitcoin-cash", "BCH", "Bitcoin Cash"),
    ("avax-avalanche", "AVAX", "Avalanche"), ("ltc-litecoin", "LTC", "Litecoin"),
    ("sui-sui", "SUI", "Sui"), ("hbar-hedera-hashgraph", "HBAR", "Hedera"),
    ("dot-polkadot", "DOT", "Polkadot"), ("zec-zcash", "ZEC", "Zcash"),
    ("xmr-monero", "XMR", "Monero"), ("uni-uniswap", "UNI", "Uniswap"),
    ("aave-new", "AAVE", "Aave"), ("near-near-protocol", "NEAR", "NEAR Protocol"),
]


def _fallback_universe(limit):
    assets = [
        {"id": coin_id, "symbol": symbol, "name": name, "rank": index + 1,
         "price_usd": None, "volume_24h": None, "market_cap": None,
         "change_24h": None, "source": "Fallback list (CoinPaprika unavailable)"}
        for index, (coin_id, symbol, name) in enumerate(FALLBACK_UNIVERSE[:limit])
    ]
    return {"count": len(assets), "assets": assets, "fallback": True}


async def get_coin_universe(limit=100):
    try:
        tickers = await get_tickers(limit)
    except Exception:
        return _fallback_universe(limit)
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

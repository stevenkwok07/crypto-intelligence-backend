"""Small, explicitly provisional spot portfolio simulation."""


def build_simulated_allocation(scan_assets, max_assets=3, total_cap_pct=30.0, per_asset_cap_pct=10.0):
    """Allocate only among clean candlestick candidates; leave the rest in cash.

    Weights use a simple heuristic: 4H pattern strength divided by 4H ATR percent,
    so stronger patterns get more and more volatile assets get less.
    This sizing rule is not backtested.
    """
    candidates = []
    for item in scan_assets:
        recommendation = item.get("recommendation") or {}
        quality = recommendation.get("timeframe_data_quality") or {}
        if (
            recommendation.get("research_setup") != "LONG_CANDIDATE"
            or recommendation.get("status") != "PROVISIONAL"
            or any(quality.get(tf) != "OK" for tf in ("4H", "1H"))
        ):
            continue
        atr_pct = (recommendation.get("volatility_context_4H") or {}).get("atr_pct")
        try:
            strength = float(recommendation.get("pattern_strength_4H") or 0)
            atr_pct = float(atr_pct)
        except (TypeError, ValueError):
            continue
        if strength <= 0 or atr_pct <= 0:
            continue
        asset = item.get("asset") or {}
        symbol = str(asset.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        score = item.get("technical_score")
        candidates.append({
            "symbol": symbol,
            "name": asset.get("name"),
            "pattern_strength_4h": strength,
            "technical_score": round(float(score), 2) if isinstance(score, (int, float)) else None,
            "atr_pct_4h": round(atr_pct, 4),
            "patterns_4h": [p.get("name") for p in (recommendation.get("patterns") or {}).get("4H", []) if p.get("direction") == "BULLISH"],
            "raw_weight": strength / atr_pct,
        })

    candidates.sort(key=lambda item: (item["pattern_strength_4h"], item["raw_weight"]), reverse=True)
    candidates = candidates[:max_assets]
    if not candidates:
        return {
            "status": "WITHHELD",
            "allocations": [],
            "deployed_pct": 0.0,
            "cash_pct": 100.0,
            "withheld_reasons": ["Belum ada koin dengan pola candlestick bullish 4H yang terkonfirmasi candle 1H."],
        }

    cap = float(per_asset_cap_pct)
    target = min(float(total_cap_pct), cap * len(candidates))
    remaining = target
    open_symbols = {item["symbol"]: item for item in candidates}
    weights = {item["symbol"]: 0.0 for item in candidates}
    while remaining > 1e-9 and open_symbols:
        raw_total = sum(item["raw_weight"] for item in open_symbols.values())
        capped = []
        for symbol, item in open_symbols.items():
            proposed = remaining * item["raw_weight"] / raw_total
            room = cap - weights[symbol]
            if proposed >= room - 1e-9:
                weights[symbol] += room
                remaining -= room
                capped.append(symbol)
        if not capped:
            for symbol, item in open_symbols.items():
                weights[symbol] += remaining * item["raw_weight"] / raw_total
            remaining = 0.0
        else:
            for symbol in capped:
                open_symbols.pop(symbol, None)

    allocations = [
        {
            "symbol": item["symbol"],
            "name": item["name"],
            "weight_pct": round(weights[item["symbol"]], 2),
            "pattern_strength_4h": item["pattern_strength_4h"],
            "patterns_4h": item["patterns_4h"],
            "technical_score": item["technical_score"],
            "atr_pct_4h": item["atr_pct_4h"],
            "status": "SIMULATION_ONLY",
        }
        for item in candidates if weights[item["symbol"]] > 0
    ]
    deployed = round(sum(item["weight_pct"] for item in allocations), 2)
    return {
        "status": "PROVISIONAL_SIMULATION",
        "allocations": allocations,
        "deployed_pct": deployed,
        "cash_pct": round(100.0 - deployed, 2),
        "method_note": "Simulasi berbasis pola candlestick (setup 4H, konfirmasi 1H), bukan probabilitas atau strategi tervalidasi. Maksimal 30% modal masuk crypto, maksimal 10% per aset; sisanya tetap cash. Bobot relatif memakai kekuatan pola 4H / ATR 4H.",
        "limitations": [
            "Pola candlestick adalah heuristik dan sering gagal tanpa konteks tren.",
            "Aturan bobot belum diuji out-of-sample setelah biaya dan slippage.",
            "Likuiditas dan kecocokan dengan situasi keuangan pribadi belum dinilai.",
        ],
    }

"""Small, explicitly provisional spot portfolio simulation."""


def build_simulated_allocation(scan_assets, max_assets=3, total_cap_pct=50.0, per_asset_cap_pct=20.0):
    """Allocate only among clean, fully-confirmed candidates; leave the rest in cash.

    Weights use a simple heuristic: technical strength divided by 4H ATR percent.
    The score is not a probability and this sizing rule is not backtested.
    """
    candidates = []
    for item in scan_assets:
        recommendation = item.get("recommendation") or {}
        quality = recommendation.get("timeframe_data_quality") or {}
        if (
            recommendation.get("research_setup") != "LONG_CANDIDATE"
            or recommendation.get("status") != "PROVISIONAL"
            or any(quality.get(tf) != "OK" for tf in ("1D", "4H", "1H"))
        ):
            continue
        score = item.get("technical_score")
        atr_pct = (recommendation.get("volatility_context_4H") or {}).get("atr_pct")
        try:
            score = float(score)
            atr_pct = float(atr_pct)
        except (TypeError, ValueError):
            continue
        if score < 65 or atr_pct <= 0:
            continue
        asset = item.get("asset") or {}
        symbol = str(asset.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        candidates.append({
            "symbol": symbol,
            "name": asset.get("name"),
            "technical_score": round(score, 2),
            "atr_pct_4h": round(atr_pct, 4),
            "raw_weight": max(score - 60.0, 1.0) / atr_pct,
        })

    candidates.sort(key=lambda item: (item["technical_score"], item["raw_weight"]), reverse=True)
    candidates = candidates[:max_assets]
    if not candidates:
        return {
            "status": "WITHHELD",
            "allocations": [],
            "deployed_pct": 0.0,
            "cash_pct": 100.0,
            "withheld_reasons": ["Belum ada setup long dengan data 1D/4H/1H bersih dan terkonfirmasi."],
        }

    target = min(float(total_cap_pct), float(per_asset_cap_pct) * len(candidates))
    remaining = target
    open_symbols = {item["symbol"]: item for item in candidates}
    weights = {item["symbol"]: 0.0 for item in candidates}
    while remaining > 1e-9 and open_symbols:
        raw_total = sum(item["raw_weight"] for item in open_symbols.values())
        capped = []
        for symbol, item in open_symbols.items():
            proposed = remaining * item["raw_weight"] / raw_total
            room = float(per_asset_cap_pct) - weights[symbol]
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
        "method_note": "Simulasi teknikal, bukan probabilitas atau strategi tervalidasi. Maksimal 50% modal masuk crypto, maksimal 20% per aset; sisanya tetap cash. Bobot relatif memakai (skor teknikal - 60) / ATR 4H.",
        "limitations": [
            "Skor teknikal bukan probabilitas keberhasilan.",
            "Aturan bobot belum diuji out-of-sample setelah biaya dan slippage.",
            "Likuiditas dan kecocokan dengan situasi keuangan pribadi belum dinilai.",
        ],
    }


from datetime import datetime, timezone
import asyncio

import pandas as pd

from providers.coinpaprika import get_coin
from providers.kraken import get_klines
from indicators.core import add_indicators
from engine.market_structure import analyze_market_structure
from engine.divergence import detect_macd_divergence
from engine.recommendations import build_multi_timeframe_recommendation
from engine.scoring import (
    trend_score, momentum_score, volume_score, volatility_score,
    technical_score, classify, analyze_volume,
)


BINANCE_INTERVAL_MS = {
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}


def binance_rows_to_df(rows, interval="1h"):
    if not rows:
        raise ValueError("Binance returned no candles")
    if interval not in BINANCE_INTERVAL_MS:
        raise ValueError(f"Unsupported Binance interval: {interval}")
    columns = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore",
    ]
    df = pd.DataFrame(rows, columns=columns)
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    numeric = ["open", "high", "low", "close", "volume"]
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    # Exclude the currently-forming candle to avoid look-ahead.
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    df["close_time"] = pd.to_numeric(df["close_time"], errors="coerce")
    df = df[df["close_time"] < now_ms]
    closed_rows = len(df)
    df = df.dropna(subset=numeric + ["timestamp"])
    invalid_rows = closed_rows - len(df)
    interval_ms = BINANCE_INTERVAL_MS[interval]
    duplicate_count = int(df["timestamp"].duplicated().sum())
    out_of_order_count = int((df["timestamp"].diff().dropna() < pd.Timedelta(0)).sum())

    unique_times = df["timestamp"].drop_duplicates().sort_values()
    # pandas may store datetimes at microsecond resolution; normalize explicitly
    # before comparing against Binance's millisecond timestamps.
    epoch_ms = unique_times.dt.as_unit("ms").astype("int64")
    aligned_count = int((epoch_ms % interval_ms != 0).sum())
    deltas = epoch_ms.diff().dropna()
    mismatch_count = int((deltas % interval_ms != 0).sum())
    missing_intervals = int(sum(
        max(int(delta // interval_ms) - 1, 0)
        for delta in deltas
        if delta > interval_ms and delta % interval_ms == 0
    ))
    quality_issues = any((
        invalid_rows, duplicate_count, out_of_order_count,
        aligned_count, mismatch_count, missing_intervals,
    ))
    quality = {
        "status": "WARN" if quality_issues else "OK",
        "interval": interval,
        "raw_rows": len(rows),
        "closed_candles": closed_rows,
        "invalid_candles": invalid_rows,
        "duplicate_candles": duplicate_count,
        "out_of_order_candles": out_of_order_count,
        "missing_intervals": missing_intervals,
        "interval_mismatch_count": mismatch_count,
        "timestamp_alignment_issues": aligned_count,
        "note": "Checks internal candle spacing and timestamps; does not verify missing history before the first returned candle.",
    }

    df = df.sort_values("timestamp")
    df = df.drop_duplicates("timestamp").reset_index(drop=True)
    if df.empty:
        raise ValueError("No closed candles returned by Binance")
    df.attrs["data_quality"] = quality
    return df


def analyze_timeframe(rows, interval="1h"):
    candles = binance_rows_to_df(rows, interval)
    data_quality = candles.attrs["data_quality"]
    df = add_indicators(candles)
    if len(df) < 220:
        return {
            "status": "INSUFFICIENT_DATA",
            "valid_candles": len(df),
            "required_candles": 220,
            "data_quality": data_quality,
        }
    t = trend_score(df)
    m = momentum_score(df)
    volume_analysis = analyze_volume(df)
    v = volume_analysis["score"]
    r = volatility_score(df)
    score = technical_score(t, m, v, r)
    x = df.iloc[-1]
    structure = analyze_market_structure(df)
    macd_divergence = (
        detect_macd_divergence(df, left=8, right=8)
        if interval == "4h" else None
    )
    return {
        "status": "PROVISIONAL",
        "valid_candles": len(df),
        "technical_score": round(score, 2),
        "classification": classify(score),
        "components": {
            "trend": round(t, 2), "momentum": round(m, 2),
            "volume": round(v, 2), "volatility": round(r, 2),
        },
        "market_structure": structure,
        "volume_analysis": volume_analysis,
        "macd_divergence": macd_divergence,
        "data_quality": data_quality,
        "indicators": {
            "close": float(x["close"]),
            "ema20": float(x["ema20"]),
            "ema50": float(x["ema50"]),
            "ema200": float(x["ema200"]),
            "rsi14": float(x["rsi14"]),
            "previous_rsi14": float(df.iloc[-2]["rsi14"]),
            "macd": float(x["macd"]),
            "macd_signal": float(x["macd_signal"]),
            "macd_hist": float(x["macd_hist"]),
            "previous_macd_hist": float(df.iloc[-2]["macd_hist"]),
            "atr_pct": float(x["atr_pct"]),
            "relative_volume": float(x["relative_volume"]) if pd.notna(x["relative_volume"]) else None,
            "bbw": float(x["bbw"]) if pd.notna(x["bbw"]) else None,
        },
    }


def summarize_timeframe_alignment(analyses):
    """Describe directional agreement without changing the technical score."""
    structure = {
        tf: analyses.get(tf, {}).get("market_structure", {})
        for tf in ("1D", "4H", "1H")
    }
    trends = {tf: item.get("trend", "UNKNOWN") for tf, item in structure.items()}
    event_biases = {tf: item.get("event_bias", "UNKNOWN") for tf, item in structure.items()}

    daily = trends["1D"]
    swing = trends["4H"]
    hourly = trends["1H"]
    if daily == "UNKNOWN" or swing == "UNKNOWN" or hourly == "UNKNOWN":
        alignment = "INCOMPLETE"
    elif daily == swing == hourly and daily in ("BULLISH", "BEARISH"):
        alignment = "FULL_ALIGNMENT"
    elif daily == swing and daily in ("BULLISH", "BEARISH"):
        alignment = "MACRO_SWING_ALIGNED_HOURLY_MIXED"
    elif swing == hourly and swing in ("BULLISH", "BEARISH"):
        alignment = "SWING_CONFIRMATION_WITHOUT_MACRO"
    elif daily in ("BULLISH", "BEARISH") and swing in ("BULLISH", "BEARISH") and daily != swing:
        alignment = "MACRO_SWING_CONFLICT"
    else:
        alignment = "MIXED_OR_UNCONFIRMED"

    return {
        "status": alignment,
        "structure_trends": trends,
        "latest_event_bias": event_biases,
        "note": "Descriptive alignment only; it does not alter scores or represent a probability."
    }


async def analyze_coin(coin_id: str):
    coin = await get_coin(coin_id)
    symbol = str(coin.get("symbol", "")).upper()
    if not symbol or not symbol.isalnum():
        raise ValueError(f"Invalid asset symbol for Kraken market mapping: {symbol!r}")
    pair = f"{symbol}USDT"

    # Kraken Spot public OHLC is the primary source; no exchange credentials needed.
    results = await asyncio.gather(
        get_klines(pair, "1d", 500),
        get_klines(pair, "4h", 500),
        get_klines(pair, "1h", 500),
        return_exceptions=True,
    )
    timeframes = {
        "1D": (results[0], "1d"),
        "4H": (results[1], "4h"),
        "1H": (results[2], "1h"),
    }
    analyses = {}
    for tf, (rows, interval) in timeframes.items():
        if isinstance(rows, Exception):
            analyses[tf] = {"status": "DATA_UNAVAILABLE", "error": str(rows)}
            continue
        try:
            analyses[tf] = analyze_timeframe(rows, interval)
        except Exception as exc:
            analyses[tf] = {"status": "DATA_ERROR", "error": str(exc)}

    ready = all(analyses[tf].get("status") == "PROVISIONAL" for tf in ("1D", "4H", "1H"))
    if not ready:
        return {
            "asset": {"id": coin_id, "name": coin.get("name"), "symbol": symbol},
            "asset_symbol": symbol,
            "classification": "INSUFFICIENT_DATA",
            "status": "MULTI_TIMEFRAME_INCOMPLETE",
            "source": "Kraken Spot + CoinPaprika metadata",
            "timeframes": analyses,
            "note": "A timeframe is missing, unavailable, or has fewer than 220 closed candles. No combined score is issued.",
        }

    daily = analyses["1D"]["technical_score"]
    four_hour = analyses["4H"]["technical_score"]
    hourly = analyses["1H"]["technical_score"]
    # 4H is the primary swing score; 1D is the macro filter and 1H is confirmation.
    combined = round(0.60 * four_hour + 0.25 * daily + 0.15 * hourly, 2)
    macro_conflict = (daily >= 65 and four_hour <= 44) or (daily <= 44 and four_hour >= 65)
    hourly_conflict = (hourly >= 65 and four_hour <= 44) or (hourly <= 44 and four_hour >= 65)
    if macro_conflict:
        status = "COUNTER_TREND"
    elif hourly_conflict:
        status = "CONFIRMATION_WEAK"
    else:
        status = "PROVISIONAL_MULTI_TIMEFRAME"

    return {
        "asset": {"id": coin_id, "name": coin.get("name"), "symbol": symbol},
        "asset_symbol": symbol,
        "timeframe_role": {"1D": "macro_filter", "4H": "primary_swing_score", "1H": "confirmation"},
        "technical_score": combined,
        "classification": classify(combined),
        "status": status,
        "timeframe_alignment": summarize_timeframe_alignment(analyses),
        "recommendation": build_multi_timeframe_recommendation(analyses),
        "timeframes": analyses,
        "market_quality": {
            "score": None,
            "status": "NOT_YET_IMPLEMENTED",
            "note": "Spread, order-book depth and cross-exchange liquidity are not included in this score.",
        },
        "data_quality": {
            "source": "Kraken Spot OHLC; CoinPaprika asset metadata",
            "closed_candles_only": True,
            "confidence": "LOW",
            "note": "Provisional technical model. Market structure is heuristic; confirmed MACD divergence, market-quality scoring, backtesting, fees and slippage validation are not yet implemented.",
        },
    }


"""Explainable multi-timeframe spot setup screening.

This module identifies research scenarios only. It does not estimate returns,
set portfolio weights, or authorize orders.
"""
from math import isfinite


def _number(value):
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _frame(analyses, timeframe):
    return analyses.get(timeframe, {}) if isinstance(analyses, dict) else {}


def _indicators(frame):
    result = frame.get("indicators", {})
    return result if isinstance(result, dict) else {}


def _structure(frame):
    result = frame.get("market_structure", {})
    return result if isinstance(result, dict) else {}


def _macro_regime(daily):
    ind = _indicators(daily)
    structure = _structure(daily)
    ema50, ema200, close = (_number(ind.get(key)) for key in ("ema50", "ema200", "close"))
    trend = structure.get("trend", "UNKNOWN")
    if ema50 is None or ema200 is None or close is None:
        return "UNKNOWN"
    if ema50 > ema200 and close > ema50 and trend == "BULLISH":
        return "BULLISH"
    if ema50 < ema200 and close < ema50 and trend == "BEARISH":
        return "BEARISH"
    return "SIDEWAYS"


def _check(name, passed, detail):
    return {"check": name, "passed": bool(passed), "detail": detail}


def build_multi_timeframe_recommendation(
    analyses, backtest_validated=False, market_quality_validated=False
):
    """Build a conservative 1D filter / 4H setup / 1H confirmation readout."""
    daily = _frame(analyses, "1D")
    four_hour = _frame(analyses, "4H")
    hourly = _frame(analyses, "1H")
    frames = {"1D": daily, "4H": four_hour, "1H": hourly}
    complete = all(frame.get("status") == "PROVISIONAL" for frame in frames.values())
    data_quality = {
        timeframe: frame.get("data_quality", {}).get("status", "UNKNOWN")
        for timeframe, frame in frames.items()
    }
    quality_ok = complete and all(status == "OK" for status in data_quality.values())

    macro = _macro_regime(daily) if complete else "UNKNOWN"
    h4 = _indicators(four_hour)
    h4_structure = _structure(four_hour)
    h4_score = _number(four_hour.get("technical_score"))
    h4_ema20, h4_ema50, h4_ema200, h4_close = (
        _number(h4.get(key)) for key in ("ema20", "ema50", "ema200", "close")
    )
    h4_rsi = _number(h4.get("rsi14"))
    h4_macd, h4_signal, h4_hist = (
        _number(h4.get(key)) for key in ("macd", "macd_signal", "macd_hist")
    )
    h4_volume = four_hour.get("volume_analysis", {})
    h4_pressure = h4_volume.get("directional_pressure", "UNKNOWN")
    h4_divergence = four_hour.get("macd_divergence") or {"direction": "NONE"}
    divergence_direction = h4_divergence.get("direction", "NONE")

    h4_checks = [
        _check("Skor teknikal 4H >= 65", h4_score is not None and h4_score >= 65,
               f"Skor 4H: {h4_score if h4_score is not None else 'tidak tersedia'}; ambang 65."),
        _check("EMA 20 > EMA 50 > EMA 200", None not in (h4_ema20, h4_ema50, h4_ema200) and h4_ema20 > h4_ema50 > h4_ema200,
               "Menilai susunan tren utama pada 4H."),
        _check("Close di atas EMA 200", h4_close is not None and h4_ema200 is not None and h4_close > h4_ema200,
               "Harga 4H perlu berada di atas tren panjangnya."),
        _check("Struktur 4H bullish", h4_structure.get("trend") == "BULLISH",
               f"Struktur 4H: {h4_structure.get('trend', 'UNKNOWN')} (pivot major terkonfirmasi)."),
        _check("Event struktur major tidak bearish", h4_structure.get("event_bias") != "BEARISH",
               f"Bias event major terakhir: {h4_structure.get('event_bias', 'UNKNOWN')} (BOS/CHoCH terkonfirmasi)."),
        _check("MACD 4H mendukung momentum", h4_macd is not None and h4_signal is not None and h4_hist is not None and h4_macd > h4_signal and h4_hist >= 0,
               "MACD line harus di atas signal line dan histogram tidak negatif."),
        _check("RSI 4H berada di rentang kerja", h4_rsi is not None and 50 <= h4_rsi <= 75,
               f"RSI 4H: {h4_rsi if h4_rsi is not None else 'tidak tersedia'}; rentang 50–75."),
        _check("Tekanan volume mendukung atau netral", h4_pressure in ("BUYING_PRESSURE", "NEUTRAL"),
               f"Tekanan volume: {h4_pressure}."),
        _check("Tidak ada divergence bearish 4H", divergence_direction != "BEARISH",
               f"Divergence MACD 4H: {divergence_direction}."),
    ]

    # The score is a screening feature, never interpreted as a probability.
    # Divergence is handled as a setup downgrade below, so the underlying 4H
    # structure remains visible as a watch scenario instead of disappearing.
    four_hour_bullish = all(item["passed"] for item in h4_checks[:-1])
    four_hour_bearish = (
        h4_score is not None and h4_score <= 44 and
        h4_structure.get("trend") == "BEARISH" and
        h4_ema20 is not None and h4_ema50 is not None and h4_ema200 is not None and
        h4_close is not None and h4_ema20 < h4_ema50 < h4_ema200 and h4_close < h4_ema200
    )
    four_hour_direction = "BULLISH" if four_hour_bullish else "BEARISH" if four_hour_bearish else "MIXED"

    h1 = _indicators(hourly)
    h1_ema20, h1_ema50, h1_rsi, h1_hist, h1_prev_hist, h1_rv = (
        _number(h1.get(key)) for key in (
            "ema20", "ema50", "rsi14", "macd_hist", "previous_macd_hist", "relative_volume"
        )
    )
    h1_checks = [
        _check("EMA 20 1H di atas EMA 50", h1_ema20 is not None and h1_ema50 is not None and h1_ema20 > h1_ema50,
               "Konfirmasi tren pendek 1H."),
        _check("RSI 1H di atas 50", h1_rsi is not None and h1_rsi > 50,
               f"RSI 1H: {h1_rsi if h1_rsi is not None else 'tidak tersedia'}."),
        _check("Histogram MACD 1H menguat", h1_hist is not None and h1_prev_hist is not None and h1_hist >= 0 and h1_hist >= h1_prev_hist,
               "Histogram harus non-negatif dan tidak melemah dari candle sebelumnya."),
        _check("Relative volume 1H >= 0.70", h1_rv is not None and h1_rv >= 0.70,
               f"Relative volume 1H: {h1_rv if h1_rv is not None else 'tidak tersedia'}; di bawah 0.70 dianggap partisipasi tipis."),
    ]
    hourly_confirmed = all(item["passed"] for item in h1_checks)

    if not complete:
        setup = "INCOMPLETE_DATA"
    elif four_hour_bearish:
        setup = "NO_LONG_SETUP"
    elif macro == "BEARISH" and four_hour_direction == "BULLISH":
        setup = "WAIT_MACRO_CONFLICT"
    elif macro == "BEARISH":
        setup = "NO_LONG_SETUP"
    elif macro != "BULLISH" or four_hour_direction != "BULLISH":
        setup = "WAIT_MIXED"
    elif divergence_direction == "BEARISH":
        setup = "WATCH_DIVERGENCE"
    elif hourly_confirmed:
        setup = "LONG_CANDIDATE"
    else:
        setup = "WATCH_1H_CONFIRMATION"

    withheld_reasons = []
    if not complete:
        withheld_reasons.append("Satu atau lebih timeframe tidak tersedia atau belum cukup candle.")
    if not quality_ok:
        withheld_reasons.append("Kualitas candle belum berstatus OK di seluruh timeframe.")
    if not backtest_validated:
        withheld_reasons.append("Aturan ini belum lulus backtest out-of-sample dengan biaya dan slippage.")
    if not market_quality_validated:
        withheld_reasons.append("Spread, depth order book, dan likuiditas belum divalidasi.")
    recommendation_status = "WITHHELD" if withheld_reasons else "REVIEW_REQUIRED"

    return {
        "status": recommendation_status,
        "research_setup": setup,
        "eligible_for_automatic_allocation": False,
        "roles": {"1D": "macro_filter", "4H": "primary_setup", "1H": "confirmation"},
        "macro_regime_1D": macro,
        "primary_direction_4H": four_hour_direction,
        "confirmation_1H": "CONFIRMED" if hourly_confirmed else "NOT_CONFIRMED",
        "timeframe_data_quality": data_quality,
        "checks": {"4H": h4_checks, "1H": h1_checks},
        "volatility_context_4H": {
            "atr_pct": h4.get("atr_pct"),
            "bollinger_band_width": h4.get("bbw"),
            "note": "ATR dan BBW memberi konteks volatilitas; belum digunakan sebagai klaim arah atau target harga.",
        },
        "withheld_reasons": withheld_reasons,
        "method_note": "Long-only spot screening. Technical scores are heuristics, not probabilities. A candidate is a scenario for review, not a buy instruction.",
    }

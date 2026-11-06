"""Candlestick-pattern spot setup screening for provisional simulations.

4H candlestick patterns define the setup, 1H candles confirm it. EMA/RSI/MACD are
still reported by the analyzer for context but no longer gate recommendations.
This identifies research scenarios, not returns or probabilities.
"""
from math import isfinite

from engine.candlestick import recent_bias

SETUP_WINDOW_4H = 3        # pattern must complete within the last 3 closed 4H candles
BEARISH_WINDOW_1H = 3      # no bearish 1H pattern within the last 3 closed 1H candles
CONFIRM_WINDOW_1H = 6      # bullish 1H pattern within the last 6 closed 1H candles


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
    """Informational only: daily trend context shown next to the candlestick setup."""
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


def _names(patterns):
    return ", ".join(f"{p['name']} ({p['candles_ago']} candle lalu)" for p in patterns) or "tidak ada"


def build_multi_timeframe_recommendation(
    analyses, backtest_validated=False, market_quality_validated=False
):
    """Build a 4H candlestick setup / 1H candlestick confirmation readout."""
    daily = _frame(analyses, "1D")
    four_hour = _frame(analyses, "4H")
    hourly = _frame(analyses, "1H")
    frames = {"1D": daily, "4H": four_hour, "1H": hourly}
    complete = all(frame.get("status") == "PROVISIONAL" for frame in (four_hour, hourly))
    data_quality = {
        timeframe: frame.get("data_quality", {}).get("status", "UNKNOWN")
        for timeframe, frame in frames.items()
    }
    quality_ok = complete and all(data_quality[tf] == "OK" for tf in ("4H", "1H"))
    macro = _macro_regime(daily) if daily.get("status") == "PROVISIONAL" else "UNKNOWN"

    h4_candles = four_hour.get("candlestick") or {}
    h1_candles = hourly.get("candlestick") or {}
    h4 = recent_bias(h4_candles, SETUP_WINDOW_4H)
    h1_bear = recent_bias(h1_candles, BEARISH_WINDOW_1H)
    h1_confirm = recent_bias(h1_candles, CONFIRM_WINDOW_1H)
    last_1h = h1_candles.get("last_candle") or {}

    four_hour_direction = h4["bias"]  # BULLISH / BEARISH / NONE
    h4_checks = [
        _check("Pola bullish 4H dalam 3 candle terakhir", h4["bullish"],
               f"Pola bullish 4H: {_names(h4['bullish'])}."),
        _check("Tidak ada pola bearish 4H yang lebih baru", four_hour_direction != "BEARISH",
               f"Pola bearish 4H: {_names(h4['bearish'])}."),
    ]

    no_fresh_bearish_1h = h1_bear["bias"] != "BEARISH"
    h1_momentum = bool(h1_confirm["bullish"]) or (
        bool(last_1h.get("bullish")) and bool(last_1h.get("close_above_previous"))
    )
    h1_checks = [
        _check("Tidak ada pola bearish 1H terbaru", no_fresh_bearish_1h,
               f"Pola bearish 1H (3 candle terakhir): {_names(h1_bear['bearish'])}."),
        _check("Konfirmasi 1H: pola bullish atau candle terakhir naik", h1_momentum,
               f"Pola bullish 1H (6 candle terakhir): {_names(h1_confirm['bullish'])}; "
               f"candle 1H terakhir {'hijau dan close di atas candle sebelumnya' if last_1h.get('bullish') and last_1h.get('close_above_previous') else 'belum menguat'}."),
    ]
    hourly_confirmed = no_fresh_bearish_1h and h1_momentum

    if not complete:
        setup = "INCOMPLETE_DATA"
    elif four_hour_direction == "BEARISH":
        setup = "NO_LONG_SETUP"
    elif four_hour_direction == "BULLISH" and hourly_confirmed:
        setup = "LONG_CANDIDATE"
    elif four_hour_direction == "BULLISH":
        setup = "WATCH_1H_CONFIRMATION"
    else:
        setup = "NO_PATTERN"

    withheld_reasons = []
    if not complete:
        withheld_reasons.append("Timeframe 4H atau 1H tidak tersedia atau belum cukup candle.")
    if not quality_ok:
        withheld_reasons.append("Kualitas candle 4H/1H belum berstatus OK.")
    if not complete or not quality_ok:
        recommendation_status = "WITHHELD"
    elif setup == "LONG_CANDIDATE":
        recommendation_status = "PROVISIONAL"
    else:
        recommendation_status = "NO_SETUP"

    limitations = []
    if not backtest_validated:
        limitations.append("Aturan pola candlestick ini belum lulus backtest out-of-sample dengan biaya dan slippage.")
    if not market_quality_validated:
        limitations.append("Spread, depth order book, dan likuiditas belum divalidasi.")

    h4_ind = _indicators(four_hour)
    return {
        "status": recommendation_status,
        "research_setup": setup,
        "method": "CANDLESTICK_4H_1H",
        "eligible_for_simulated_allocation": recommendation_status == "PROVISIONAL",
        "eligible_for_automatic_allocation": False,
        "roles": {"1D": "context_only", "4H": "candlestick_setup", "1H": "candlestick_confirmation"},
        "macro_regime_1D": macro,
        "primary_direction_4H": four_hour_direction,
        "confirmation_1H": "CONFIRMED" if hourly_confirmed else "NOT_CONFIRMED",
        "pattern_strength_4H": h4["bullish_strength"],
        "patterns": {
            "4H": h4["bullish"] + h4["bearish"],
            "1H": h1_confirm["bullish"] + h1_bear["bearish"],
        },
        "timeframe_data_quality": data_quality,
        "checks": {"4H": h4_checks, "1H": h1_checks},
        "volatility_context_4H": {
            "atr_pct": h4_ind.get("atr_pct"),
            "bollinger_band_width": h4_ind.get("bbw"),
            "note": "ATR dipakai untuk mengecilkan bobot aset yang lebih volatil.",
        },
        "withheld_reasons": withheld_reasons,
        "limitations": limitations,
        "method_note": "Simulasi long-only spot berbasis pola candlestick: pola bullish 4H sebagai setup, candle 1H sebagai konfirmasi. Indikator EMA/RSI/MACD hanya konteks. Nominal bukan instruksi transaksi dan strategi belum tervalidasi.",
    }

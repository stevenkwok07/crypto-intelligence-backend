from math import isfinite
from engine.market_structure import analyze_market_structure


def clamp(value, low=0, high=100):
    return max(low, min(high, value))


def trend_score(df):
    x = df.iloc[-1]
    score = 50.0
    if x["ema20"] > x["ema50"]:
        score += 20
    elif x["ema20"] < x["ema50"]:
        score -= 20
    if x["close"] > x["ema200"]:
        score += 15
    elif x["close"] < x["ema200"]:
        score -= 15
    structure = analyze_market_structure(df)
    score += (structure["score"] - 50.0) * 0.20
    return clamp(score)


def momentum_score(df):
    x = df.iloc[-1]
    rsi_value = float(x["rsi14"])
    # RSI is centered around 50; extremes are not automatically bullish.
    rsi_component = clamp(50 + (rsi_value - 50) * 1.2)
    # Divergence remains neutral until a confirmed detector is implemented.
    div_component = 50.0
    return clamp(0.5 * rsi_component + 0.5 * div_component)


def analyze_volume(df):
    """
    Score volume direction without allowing low participation to erase it.

    OBV pressure is normalized by total traded volume over the same lookback,
    so the directional measure is comparable across assets and price scales.
    Relative volume attenuates confidence smoothly; it does not switch the
    directional contribution abruptly on/off at a threshold.
    """
    x = df.iloc[-1]

    def finite_number(value, default):
        try:
            value = float(value)
            return value if isfinite(value) else default
        except (TypeError, ValueError):
            return default

    rv = finite_number(x.get("relative_volume", 1.0), 1.0)

    # Normalize the 20-candle OBV change by total volume in those candles.
    # This is bounded approximately to [-1, 1] and avoids raw OBV scale effects.
    lookback = min(20, len(df))
    volume_sum = finite_number(df["volume"].tail(lookback).sum(), 0.0)
    obv_change = finite_number(
        df["obv"].iloc[-1] - df["obv"].iloc[-lookback], 0.0
    ) if "obv" in df.columns and len(df) > 1 else 0.0

    if volume_sum > 0:
        normalized_pressure = clamp(obv_change / volume_sum, -1.0, 1.0)
    else:
        normalized_pressure = 0.0

    participation = "LOW" if rv < 0.70 else "HIGH" if rv > 1.30 else "NORMAL"
    if normalized_pressure > 0.02:
        pressure = "BUYING_PRESSURE"
    elif normalized_pressure < -0.02:
        pressure = "SELLING_PRESSURE"
    else:
        pressure = "NEUTRAL"

    # Confidence rises continuously with relative volume, capped at normal-high.
    # Low volume weakens the signal but does not force the score to exactly 50.
    participation_confidence = clamp(rv / 1.30, 0.0, 1.0)
    score = clamp(
        50.0 + 20.0 * normalized_pressure * participation_confidence
    )

    return {
        "relative_volume": round(rv, 4),
        "participation": participation,
        "obv_slope20": round(finite_number(x.get("obv_slope20", 0.0), 0.0), 4),
        "normalized_obv_pressure": round(normalized_pressure, 4),
        "participation_confidence": round(participation_confidence, 4),
        "directional_pressure": pressure,
        "score": round(score, 2),
        "method": "20-candle OBV change normalized by 20-candle total volume; relative volume smoothly attenuates directional contribution",
        "note": "OBV is a price-direction-weighted volume proxy, not proof of buyer/seller control. Low participation reduces confidence."
    }


def volume_score(df):
    return analyze_volume(df)["score"]


def volatility_score(df):
    # Direction-neutral placeholder until a validated breakout model exists.
    return 50.0


def technical_score(t, m, v, r):
    return (35 * t + 20 * m + 20 * v + 15 * r) / 90


def classify(score):
    if score >= 80:
        return "STRONG_BULLISH"
    if score >= 65:
        return "BULLISH"
    if score >= 45:
        return "NEUTRAL"
    if score >= 30:
        return "BEARISH"
    return "STRONG_BEARISH"

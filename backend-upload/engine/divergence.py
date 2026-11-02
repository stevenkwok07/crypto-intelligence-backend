"""Confirmed MACD-line divergence checks for closed-candle data."""
from math import isfinite

from engine.market_structure import _confirmed_pivots


def detect_macd_divergence(df, left: int = 8, right: int = 8, lookback: int = 160):
    """Return the latest regular divergence using confirmed price pivots.

    Bullish divergence means price makes a lower pivot low while the MACD line
    makes a higher low. Bearish divergence means price makes a higher pivot
    high while the MACD line makes a lower high. A pivot is only usable after
    its right-side confirmation candles are present in ``df``.
    """
    empty = {
        "direction": "NONE",
        "type": None,
        "price_pivots": [],
        "macd_values": [],
        "confirmation": "CLOSED_CANDLES_ONLY",
    }
    if df is None or "macd" not in df or len(df) < left + right + 3:
        return {**empty, "note": "Insufficient data for confirmed MACD divergence."}

    high_pivots, low_pivots = _confirmed_pivots(df, left=left, right=right)
    cutoff = max(0, len(df) - lookback)

    def latest_pair(pivots):
        usable = [
            pivot for pivot in pivots
            if pivot["index"] >= cutoff and pivot["confirmed_index"] < len(df)
        ]
        for current_index in range(len(usable) - 1, 0, -1):
            previous, current = usable[current_index - 1], usable[current_index]
            try:
                previous_macd = float(df.iloc[previous["index"]]["macd"])
                current_macd = float(df.iloc[current["index"]]["macd"])
            except (TypeError, ValueError):
                continue
            if isfinite(previous_macd) and isfinite(current_macd):
                return previous, current, previous_macd, current_macd
        return None

    low_pair = latest_pair(low_pivots)
    if low_pair:
        previous, current, previous_macd, current_macd = low_pair
        if current["price"] < previous["price"] and current_macd > previous_macd:
            return {
                "direction": "BULLISH",
                "type": "REGULAR",
                "price_pivots": [round(float(previous["price"]), 8), round(float(current["price"]), 8)],
                "macd_values": [round(previous_macd, 8), round(current_macd, 8)],
                "pivot_timestamps": [previous["timestamp"], current["timestamp"]],
                "confirmed_at": str(df.iloc[current["confirmed_index"]]["timestamp"]),
                "confirmation": "CLOSED_CANDLES_ONLY",
            }

    high_pair = latest_pair(high_pivots)
    if high_pair:
        previous, current, previous_macd, current_macd = high_pair
        if current["price"] > previous["price"] and current_macd < previous_macd:
            return {
                "direction": "BEARISH",
                "type": "REGULAR",
                "price_pivots": [round(float(previous["price"]), 8), round(float(current["price"]), 8)],
                "macd_values": [round(previous_macd, 8), round(current_macd, 8)],
                "pivot_timestamps": [previous["timestamp"], current["timestamp"]],
                "confirmed_at": str(df.iloc[current["confirmed_index"]]["timestamp"]),
                "confirmation": "CLOSED_CANDLES_ONLY",
            }

    return {**empty, "note": "No regular divergence found in the latest confirmed pivots."}

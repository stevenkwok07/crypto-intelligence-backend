"""Classic candlestick pattern detection on closed candles.

Patterns are rule-based heuristics, not probabilities. Each detected pattern
reports how many candles ago it completed (0 = latest closed candle).
"""
from math import isfinite

BULLISH, BEARISH = "BULLISH", "BEARISH"
TREND_LOOKBACK = 5


def _f(value):
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _candle(row):
    o, h, l, c = (_f(row.get(k)) for k in ("open", "high", "low", "close"))
    if None in (o, h, l, c) or h < l:
        return None
    body = abs(c - o)
    rng = h - l
    return {
        "o": o, "h": h, "l": l, "c": c,
        "body": body, "range": rng,
        "upper": h - max(o, c), "lower": min(o, c) - l,
        "bull": c > o, "bear": c < o,
        "mid": (o + c) / 2.0,
    }


def _downtrend(closes, i):
    """Prior context: close before the pattern is below the close TREND_LOOKBACK bars earlier."""
    j = i - 1
    return j - TREND_LOOKBACK >= 0 and closes[j] < closes[j - TREND_LOOKBACK]


def _uptrend(closes, i):
    j = i - 1
    return j - TREND_LOOKBACK >= 0 and closes[j] > closes[j - TREND_LOOKBACK]


def _big(k):
    return k["range"] > 0 and k["body"] >= 0.5 * k["range"]


def _patterns_at(cs, closes, i):
    found = []
    cur = cs[i]
    prev = cs[i - 1] if i >= 1 else None
    prev2 = cs[i - 2] if i >= 2 else None
    if cur is None:
        return found
    down, up = _downtrend(closes, i), _uptrend(closes, i)

    # Single-candle reversals.
    if cur["range"] > 0 and cur["body"] > 0:
        if down and cur["lower"] >= 2 * cur["body"] and cur["upper"] <= 0.5 * cur["body"]:
            found.append(("Hammer", BULLISH, 1))
        if up and cur["upper"] >= 2 * cur["body"] and cur["lower"] <= 0.5 * cur["body"]:
            found.append(("Shooting Star", BEARISH, 1))

    if prev is not None:
        # Engulfing.
        if down and prev["bear"] and cur["bull"] and cur["c"] >= prev["o"] and cur["o"] <= prev["c"] and cur["body"] > prev["body"]:
            found.append(("Bullish Engulfing", BULLISH, 2))
        if up and prev["bull"] and cur["bear"] and cur["c"] <= prev["o"] and cur["o"] >= prev["c"] and cur["body"] > prev["body"]:
            found.append(("Bearish Engulfing", BEARISH, 2))
        # Piercing line / dark cloud cover.
        if down and prev["bear"] and _big(prev) and cur["bull"] and cur["o"] < prev["c"] and prev["mid"] < cur["c"] < prev["o"]:
            found.append(("Piercing Line", BULLISH, 2))
        if up and prev["bull"] and _big(prev) and cur["bear"] and cur["o"] > prev["c"] and prev["o"] < cur["c"] < prev["mid"]:
            found.append(("Dark Cloud Cover", BEARISH, 2))

    if prev is not None and prev2 is not None:
        small_middle = prev["body"] <= 0.3 * prev2["body"]
        # Morning / evening star (context measured before the first candle).
        if _downtrend(closes, i - 2) and prev2["bear"] and _big(prev2) and small_middle and cur["bull"] and cur["c"] > prev2["mid"]:
            found.append(("Morning Star", BULLISH, 3))
        if _uptrend(closes, i - 2) and prev2["bull"] and _big(prev2) and small_middle and cur["bear"] and cur["c"] < prev2["mid"]:
            found.append(("Evening Star", BEARISH, 3))
        trio = (prev2, prev, cur)
        if all(k["bull"] and _big(k) and k["upper"] <= 0.3 * k["body"] for k in trio) and \
                prev2["c"] < prev["c"] < cur["c"] and \
                prev2["o"] <= prev["o"] <= prev2["c"] and prev["o"] <= cur["o"] <= prev["c"]:
            found.append(("Three White Soldiers", BULLISH, 3))
        if all(k["bear"] and _big(k) and k["lower"] <= 0.3 * k["body"] for k in trio) and \
                prev2["c"] > prev["c"] > cur["c"] and \
                prev2["c"] <= prev["o"] <= prev2["o"] and prev["c"] <= cur["o"] <= prev["o"]:
            found.append(("Three Black Crows", BEARISH, 3))
    return found


def detect_candlestick_patterns(df, scan_last=10):
    """Return patterns completed within the last `scan_last` closed candles of df."""
    records = df.to_dict("records") if hasattr(df, "to_dict") else list(df)
    candles = [_candle(row) for row in records]
    closes = [k["c"] if k else None for k in candles]
    # Fill gaps so trend context never compares against None.
    for idx in range(1, len(closes)):
        if closes[idx] is None:
            closes[idx] = closes[idx - 1]
    if closes and closes[0] is None:
        closes[0] = next((c for c in closes if c is not None), 0.0)

    n = len(candles)
    patterns = []
    for i in range(max(0, n - scan_last), n):
        for name, direction, strength in _patterns_at(candles, closes, i):
            row = records[i]
            ts = row.get("timestamp")
            patterns.append({
                "name": name,
                "direction": direction,
                "strength": strength,
                "candles_ago": n - 1 - i,
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else ts,
            })
    patterns.sort(key=lambda p: (p["candles_ago"], -p["strength"]))

    last = candles[-1] if candles else None
    prev = candles[-2] if n >= 2 else None
    return {
        "patterns": patterns,
        "last_candle": {
            "bullish": bool(last and last["bull"]),
            "close_above_previous": bool(last and prev and last["c"] > prev["c"]),
        },
        "note": "Pola candlestick klasik pada candle tertutup; heuristik, bukan probabilitas.",
    }


def recent_bias(candlestick, window):
    """Summarize patterns within `window` candles: newest direction wins."""
    patterns = [p for p in (candlestick or {}).get("patterns", []) if p.get("candles_ago", 99) < window]
    bullish = [p for p in patterns if p["direction"] == BULLISH]
    bearish = [p for p in patterns if p["direction"] == BEARISH]
    newest_bull = min((p["candles_ago"] for p in bullish), default=None)
    newest_bear = min((p["candles_ago"] for p in bearish), default=None)
    if newest_bull is not None and (newest_bear is None or newest_bull < newest_bear):
        bias = BULLISH
    elif newest_bear is not None and (newest_bull is None or newest_bear <= newest_bull):
        bias = BEARISH
    else:
        bias = "NONE"
    return {
        "bias": bias,
        "bullish": bullish,
        "bearish": bearish,
        "bullish_strength": max((p["strength"] for p in bullish), default=0),
    }

"""Hierarchical swing structure with major-level BOS/CHoCH reconstruction.

Major pivots define external structure and BOS/CHoCH. Minor pivots describe
internal structure only; they cannot independently flip the major event bias.
Provisional educational analysis, not a trading signal.
"""
from __future__ import annotations


def _confirmed_pivots(df, left: int = 3, right: int = 3):
    highs = df["high"].astype(float).tolist()
    lows = df["low"].astype(float).tolist()
    high_pivots, low_pivots = [], []
    for i in range(left, len(df) - right):
        hw = highs[i-left:i+right+1]
        lw = lows[i-left:i+right+1]
        if highs[i] == max(hw) and hw.count(highs[i]) == 1:
            high_pivots.append({
                "index": i, "confirmed_index": i + right,
                "price": highs[i], "timestamp": str(df.iloc[i]["timestamp"])
            })
        if lows[i] == min(lw) and lw.count(lows[i]) == 1:
            low_pivots.append({
                "index": i, "confirmed_index": i + right,
                "price": lows[i], "timestamp": str(df.iloc[i]["timestamp"])
            })
    return high_pivots, low_pivots


def _label_pivots(items, higher_label, lower_label):
    out = []
    for i, item in enumerate(items):
        label = "PIVOT" if i == 0 else (
            higher_label if item["price"] > items[i-1]["price"] else lower_label
        )
        out.append({**item, "label": label})
    return out


def _sequence_bias(highs, lows, window=4):
    rh, rl = highs[-window:], lows[-window:]
    hh = sum(p["label"] == "HH" for p in rh)
    lh = sum(p["label"] == "LH" for p in rh)
    hl = sum(p["label"] == "HL" for p in rl)
    ll = sum(p["label"] == "LL" for p in rl)
    bull = hh >= 2 and hl >= 2 and hh > lh and hl > ll
    bear = lh >= 2 and ll >= 2 and lh > hh and ll > hl
    bias = "BULLISH" if bull else "BEARISH" if bear else "MIXED"
    return bias, {
        "higher_highs": hh, "lower_highs": lh,
        "higher_lows": hl, "lower_lows": ll
    }


def _historical_break_events(df, highs, lows, buffer_atr=0.05):
    """Reconstruct one external-structure event per candle from major pivots."""
    events = []
    closes = df["close"].astype(float).tolist()
    atrs = df["atr14"].astype(float).tolist() if "atr14" in df else [0.0] * len(df)
    volumes = df["relative_volume"].tolist() if "relative_volume" in df else [None] * len(df)
    consumed_highs, consumed_lows = set(), set()
    bias = "MIXED"

    for i in range(1, len(df)):
        eligible_h = [p for p in highs if p["confirmed_index"] < i and p["index"] not in consumed_highs]
        eligible_l = [p for p in lows if p["confirmed_index"] < i and p["index"] not in consumed_lows]
        prev_close, close = closes[i-1], closes[i]
        atr = atrs[i]
        try:
            atr = float(atr)
            if atr != atr:
                atr = 0.0
        except (TypeError, ValueError):
            atr = 0.0
        buffer = max(0.0, atr * buffer_atr)
        up = [p for p in eligible_h if prev_close <= p["price"] and close > p["price"] + buffer]
        down = [p for p in eligible_l if prev_close >= p["price"] and close < p["price"] - buffer]
        # OHLC candles cannot establish intrabar path if both sides break.
        if (up and down) or (not up and not down):
            continue

        direction = "BULLISH" if up else "BEARISH"
        candidates = up if up else down
        pivot = max(candidates, key=lambda p: (p["confirmed_index"], p["index"]))
        event_type = "CHoCH" if (
            (bias == "BULLISH" and direction == "BEARISH") or
            (bias == "BEARISH" and direction == "BULLISH")
        ) else "BOS"
        rv = volumes[i]
        try:
            rv = float(rv)
            volume_confirmation = (
                "UNKNOWN" if rv != rv else
                "CONFIRMED" if rv >= 1.0 else "LOW_PARTICIPATION"
            )
        except (TypeError, ValueError):
            volume_confirmation = "UNKNOWN"

        events.append({
            "event": event_type, "structure_scope": "MAJOR",
            "direction": direction, "level": round(float(pivot["price"]), 8),
            "pivot_timestamp": pivot["timestamp"],
            "break_timestamp": str(df.iloc[i]["timestamp"]),
            "close": round(close, 8), "buffer": round(buffer, 8),
            "validation": "CLOSE_ABOVE_BUFFER" if direction == "BULLISH" else "CLOSE_BELOW_BUFFER",
            "volume_confirmation": volume_confirmation,
            "prior_bias": bias, "updated_bias": direction,
            "same_candle_crossed_levels": len(candidates)
        })
        consumed = consumed_highs if direction == "BULLISH" else consumed_lows
        consumed.update(p["index"] for p in candidates)
        bias = direction
    return events[-10:]


def _compact(items, limit=4):
    return [{
        "price": round(float(p["price"]), 8),
        "timestamp": p["timestamp"],
        "label": p["label"]
    } for p in items[-limit:]]


def analyze_market_structure(
    df, left: int = 3, right: int = 3,
    major_left: int = 8, major_right: int = 8,
    buffer_atr: float = 0.05
):
    empty = {
        "status": "INSUFFICIENT_DATA", "trend": "UNKNOWN",
        "event_bias": "MIXED", "score": 50.0,
        "swing_highs": [], "swing_lows": [],
        "major_swing_highs": [], "major_swing_lows": [],
        "minor_swing_highs": [], "minor_swing_lows": [],
        "sequence_counts": {}, "events": [],
        "note": "Not enough candles for confirmed major/minor pivots."
    }
    if df is None or len(df) < max(left + right, major_left + major_right) + 10:
        return empty

    # Minor pivots are internal structure; major pivots define external structure.
    minor_h_raw, minor_l_raw = _confirmed_pivots(df, left, right)
    major_h_raw, major_l_raw = _confirmed_pivots(df, major_left, major_right)
    minor_h = _label_pivots(minor_h_raw, "HH", "LH")
    minor_l = _label_pivots(minor_l_raw, "HL", "LL")
    major_h = _label_pivots(major_h_raw, "HH", "LH")
    major_l = _label_pivots(major_l_raw, "HL", "LL")

    trend, counts = _sequence_bias(major_h, major_l)
    events = _historical_break_events(df, major_h_raw, major_l_raw, buffer_atr)
    event_bias = events[-1]["updated_bias"] if events else "MIXED"

    # Continuous score from the balance of major swing sequences.
    # Highs and lows are weighted equally; BOS/CHoCH events are not added again,
    # avoiding double-counting the same structural break.
    high_total = counts["higher_highs"] + counts["lower_highs"]
    low_total = counts["higher_lows"] + counts["lower_lows"]
    high_balance = (
        (counts["higher_highs"] - counts["lower_highs"]) / high_total
        if high_total else 0.0
    )
    low_balance = (
        (counts["higher_lows"] - counts["lower_lows"]) / low_total
        if low_total else 0.0
    )
    structure_balance = (high_balance + low_balance) / 2.0
    score = max(15.0, min(85.0, 50.0 + 35.0 * structure_balance))
    structure_confidence = (
        "LOW" if high_total < 2 or low_total < 2 else
        "MEDIUM" if min(high_total, low_total) < 4 else "HIGH"
    )

    return {
        "status": "PROVISIONAL",
        "trend": trend,
        "event_bias": event_bias,
        "score": round(score, 2),
        "score_components": {
            "major_high_balance": round(high_balance, 4),
            "major_low_balance": round(low_balance, 4),
            "combined_balance": round(structure_balance, 4),
            "confidence": structure_confidence,
            "method": "equal-weight normalized HH/LH and HL/LL balance over the latest four major pivots per side"
        },
        # Backward-compatible aliases now explicitly represent major structure.
        "swing_highs": _compact(major_h),
        "swing_lows": _compact(major_l),
        "major_swing_highs": _compact(major_h),
        "major_swing_lows": _compact(major_l),
        "minor_swing_highs": _compact(minor_h),
        "minor_swing_lows": _compact(minor_l),
        "sequence_counts": counts,
        "events": events,
        "parameters": {
            "minor_pivot_left": left, "minor_pivot_right": right,
            "major_pivot_left": major_left, "major_pivot_right": major_right,
            "confirmation": "closed candles only",
            "break_buffer_atr": buffer_atr,
            "event_history": "last 10 reconstructed major-structure events",
            "event_policy": "major pivots only; sequential bias; one event per candle",
            "minor_role": "internal structure only; cannot flip major event bias",
            "major_role": "external structure and BOS/CHoCH reference",
            "level_priority": "most recently confirmed crossed major pivot",
            "deduplication": "major pivot levels consumed once within supplied candle history"
        },
        "note": (
            "Major pivots use the wider confirmation window and alone drive external "
            "BOS/CHoCH and sequence trend. Minor pivots describe internal structure and "
            "do not flip major bias. Initial event bias is MIXED; the first major break "
            "is BOS, and an opposite break after bias is established is CHoCH. Events "
            "are reconstructed from supplied candles, not persisted or predictively validated."
        )
    }

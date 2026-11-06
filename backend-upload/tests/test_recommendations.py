import unittest

import pandas as pd

from engine.divergence import detect_macd_divergence
from engine.recommendations import build_multi_timeframe_recommendation


def pattern(name, direction, strength, ago):
    return {"name": name, "direction": direction, "strength": strength, "candles_ago": ago, "timestamp": None}


def bullish_analysis():
    return {
        "1D": {
            "status": "PROVISIONAL",
            "data_quality": {"status": "OK"},
            "indicators": {"close": 110, "ema50": 105, "ema200": 100},
            "market_structure": {"trend": "MIXED"},
        },
        "4H": {
            "status": "PROVISIONAL",
            "data_quality": {"status": "OK"},
            "technical_score": 40,
            "indicators": {"atr_pct": 1.2, "bbw": 0.05},
            "candlestick": {
                "patterns": [pattern("Bullish Engulfing", "BULLISH", 2, 1)],
                "last_candle": {"bullish": True, "close_above_previous": True},
            },
        },
        "1H": {
            "status": "PROVISIONAL",
            "data_quality": {"status": "OK"},
            "candlestick": {
                "patterns": [],
                "last_candle": {"bullish": True, "close_above_previous": True},
            },
        },
    }


class CandlestickRecommendationTests(unittest.TestCase):
    def test_bullish_4h_pattern_confirmed_by_1h_is_candidate_regardless_of_indicators(self):
        result = build_multi_timeframe_recommendation(bullish_analysis())

        self.assertEqual(result["method"], "CANDLESTICK_4H_1H")
        self.assertEqual(result["primary_direction_4H"], "BULLISH")
        self.assertEqual(result["confirmation_1H"], "CONFIRMED")
        self.assertEqual(result["research_setup"], "LONG_CANDIDATE")
        self.assertEqual(result["status"], "PROVISIONAL")
        self.assertEqual(result["pattern_strength_4H"], 2)
        self.assertTrue(result["eligible_for_simulated_allocation"])
        self.assertFalse(result["eligible_for_automatic_allocation"])

    def test_old_4h_pattern_outside_window_is_ignored(self):
        analyses = bullish_analysis()
        analyses["4H"]["candlestick"]["patterns"] = [pattern("Hammer", "BULLISH", 1, 5)]

        result = build_multi_timeframe_recommendation(analyses)

        self.assertEqual(result["research_setup"], "NO_PATTERN")
        self.assertEqual(result["status"], "NO_SETUP")

    def test_newer_bearish_4h_pattern_blocks_long(self):
        analyses = bullish_analysis()
        analyses["4H"]["candlestick"]["patterns"].append(pattern("Shooting Star", "BEARISH", 1, 0))

        result = build_multi_timeframe_recommendation(analyses)

        self.assertEqual(result["primary_direction_4H"], "BEARISH")
        self.assertEqual(result["research_setup"], "NO_LONG_SETUP")

    def test_unconfirmed_1h_gives_watch(self):
        analyses = bullish_analysis()
        analyses["1H"]["candlestick"]["last_candle"] = {"bullish": False, "close_above_previous": False}

        result = build_multi_timeframe_recommendation(analyses)

        self.assertEqual(result["research_setup"], "WATCH_1H_CONFIRMATION")
        self.assertEqual(result["confirmation_1H"], "NOT_CONFIRMED")

    def test_bullish_1h_pattern_confirms_even_if_last_candle_red(self):
        analyses = bullish_analysis()
        analyses["1H"]["candlestick"] = {
            "patterns": [pattern("Hammer", "BULLISH", 1, 4)],
            "last_candle": {"bullish": False, "close_above_previous": False},
        }

        result = build_multi_timeframe_recommendation(analyses)

        self.assertEqual(result["research_setup"], "LONG_CANDIDATE")

    def test_fresh_bearish_1h_pattern_blocks_confirmation(self):
        analyses = bullish_analysis()
        analyses["1H"]["candlestick"]["patterns"] = [pattern("Bearish Engulfing", "BEARISH", 2, 0)]

        result = build_multi_timeframe_recommendation(analyses)

        self.assertEqual(result["research_setup"], "WATCH_1H_CONFIRMATION")

    def test_bad_candle_quality_withholds(self):
        analyses = bullish_analysis()
        analyses["4H"]["data_quality"]["status"] = "WARN"

        result = build_multi_timeframe_recommendation(analyses)

        self.assertEqual(result["research_setup"], "LONG_CANDIDATE")
        self.assertEqual(result["status"], "WITHHELD")
        self.assertTrue(any("Kualitas candle" in reason for reason in result["withheld_reasons"]))

    def test_incomplete_timeframe_blocks_candidate(self):
        analyses = bullish_analysis()
        analyses["1H"]["status"] = "DATA_UNAVAILABLE"

        result = build_multi_timeframe_recommendation(analyses)

        self.assertEqual(result["research_setup"], "INCOMPLETE_DATA")
        self.assertEqual(result["status"], "WITHHELD")

    def test_confirmed_bullish_macd_divergence_uses_two_lower_lows(self):
        size = 30
        lows = [10.0] * size
        lows[10] = 8.0
        lows[22] = 7.5
        df = pd.DataFrame({
            "low": lows,
            "high": [12.0] * size,
            "macd": [0.0] * size,
            "timestamp": [f"candle-{i}" for i in range(size)],
        })
        df.loc[10, "macd"] = -2.0
        df.loc[22, "macd"] = -1.0

        result = detect_macd_divergence(df, left=2, right=2)

        self.assertEqual(result["direction"], "BULLISH")
        self.assertEqual(result["price_pivots"], [8.0, 7.5])
        self.assertEqual(result["macd_values"], [-2.0, -1.0])
        self.assertEqual(result["confirmed_at"], "candle-24")

    def test_unconfirmed_right_side_pivot_cannot_emit_divergence(self):
        size = 24
        lows = [10.0] * size
        lows[10] = 8.0
        lows[22] = 7.5
        df = pd.DataFrame({
            "low": lows,
            "high": [12.0] * size,
            "macd": [0.0] * size,
            "timestamp": [f"candle-{i}" for i in range(size)],
        })
        df.loc[10, "macd"] = -2.0
        df.loc[22, "macd"] = -1.0

        result = detect_macd_divergence(df, left=2, right=2)

        self.assertEqual(result["direction"], "NONE")


if __name__ == "__main__":
    unittest.main()


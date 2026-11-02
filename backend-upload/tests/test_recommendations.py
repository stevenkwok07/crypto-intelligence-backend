import unittest

import pandas as pd

from engine.divergence import detect_macd_divergence
from engine.recommendations import build_multi_timeframe_recommendation


def bullish_analysis():
    return {
        "1D": {
            "status": "PROVISIONAL",
            "data_quality": {"status": "OK"},
            "indicators": {"close": 110, "ema50": 105, "ema200": 100},
            "market_structure": {"trend": "BULLISH"},
        },
        "4H": {
            "status": "PROVISIONAL",
            "data_quality": {"status": "OK"},
            "technical_score": 70,
            "indicators": {
                "close": 110, "ema20": 108, "ema50": 105, "ema200": 100,
                "rsi14": 60, "macd": 2, "macd_signal": 1,
                "macd_hist": 1, "previous_macd_hist": 0.5,
                "relative_volume": 1.1, "atr_pct": 1.2, "bbw": 0.05,
            },
            "market_structure": {"trend": "BULLISH", "event_bias": "BULLISH"},
            "volume_analysis": {"directional_pressure": "BUYING_PRESSURE"},
            "macd_divergence": {"direction": "NONE"},
        },
        "1H": {
            "status": "PROVISIONAL",
            "data_quality": {"status": "OK"},
            "indicators": {
                "ema20": 104, "ema50": 102, "rsi14": 55,
                "macd_hist": 0.3, "previous_macd_hist": 0.2,
                "relative_volume": 0.9,
            },
        },
    }


class MultiTimeframeRecommendationTests(unittest.TestCase):
    def test_full_alignment_yields_long_candidate_but_withholds_live_recommendation(self):
        result = build_multi_timeframe_recommendation(bullish_analysis())

        self.assertEqual(result["macro_regime_1D"], "BULLISH")
        self.assertEqual(result["primary_direction_4H"], "BULLISH")
        self.assertEqual(result["confirmation_1H"], "CONFIRMED")
        self.assertEqual(result["research_setup"], "LONG_CANDIDATE")
        self.assertEqual(result["status"], "WITHHELD")
        self.assertFalse(result["eligible_for_automatic_allocation"])
        self.assertTrue(any("backtest" in reason for reason in result["withheld_reasons"]))

    def test_daily_bear_market_blocks_bullish_four_hour_setup(self):
        analyses = bullish_analysis()
        analyses["1D"]["indicators"].update({"close": 80, "ema50": 90, "ema200": 100})
        analyses["1D"]["market_structure"]["trend"] = "BEARISH"

        result = build_multi_timeframe_recommendation(analyses)

        self.assertEqual(result["macro_regime_1D"], "BEARISH")
        self.assertEqual(result["primary_direction_4H"], "BULLISH")
        self.assertEqual(result["research_setup"], "WAIT_MACRO_CONFLICT")

    def test_unconfirmed_hourly_momentum_only_generates_watch(self):
        analyses = bullish_analysis()
        analyses["1H"]["indicators"]["ema20"] = 100

        result = build_multi_timeframe_recommendation(analyses)

        self.assertEqual(result["research_setup"], "WATCH_1H_CONFIRMATION")
        self.assertEqual(result["confirmation_1H"], "NOT_CONFIRMED")

    def test_bearish_four_hour_divergence_downgrades_to_watch(self):
        analyses = bullish_analysis()
        analyses["4H"]["macd_divergence"] = {"direction": "BEARISH", "type": "REGULAR"}

        result = build_multi_timeframe_recommendation(analyses)

        self.assertEqual(result["primary_direction_4H"], "BULLISH")
        self.assertEqual(result["research_setup"], "WATCH_DIVERGENCE")
        divergence_check = result["checks"]["4H"][-1]
        self.assertFalse(divergence_check["passed"])

    def test_passed_model_gates_only_allow_human_review(self):
        result = build_multi_timeframe_recommendation(
            bullish_analysis(), backtest_validated=True, market_quality_validated=True
        )

        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertFalse(result["eligible_for_automatic_allocation"])

    def test_bad_candle_quality_still_shows_simulation_but_withholds_recommendation(self):
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
        self.assertEqual(result["macro_regime_1D"], "UNKNOWN")
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

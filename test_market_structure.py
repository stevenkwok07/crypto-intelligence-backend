import unittest

import pandas as pd
from unittest.mock import patch

from engine.market_structure import (
    _confirmed_pivots,
    _historical_break_events,
    analyze_market_structure,
)
from services.analyzer import analyze_timeframe, binance_rows_to_df


def candle_frame(highs, lows, closes):
    return pd.DataFrame({
        "timestamp": [f"candle-{i}" for i in range(len(closes))],
        "high": highs,
        "low": lows,
        "close": closes,
        "atr14": [0.0] * len(closes),
        "relative_volume": [1.0] * len(closes),
    })


def binance_row(open_time):
    return [
        open_time, "10", "11", "9", "10", "100",
        open_time + 3_599_999, "1000", 10, "50", "500", "0",
    ]


class ConfirmedPivotTests(unittest.TestCase):
    def test_pivot_is_confirmed_only_after_right_side_candles(self):
        df = candle_frame(
            highs=[2, 4, 10, 5, 3],
            lows=[1, 2, 3, 2, 1],
            closes=[2, 3, 8, 4, 2],
        )

        highs, _ = _confirmed_pivots(df, left=1, right=2)

        pivot = next(item for item in highs if item["index"] == 2)
        self.assertEqual(pivot["confirmed_index"], 4)


class HistoricalBreakEventTests(unittest.TestCase):
    def test_unconfirmed_pivot_cannot_emit_event_and_later_break_can(self):
        df = candle_frame(
            highs=[9, 9, 12, 9, 12],
            lows=[7, 8, 9, 8, 9],
            closes=[8, 9, 11, 9, 11],
        )
        major_highs = [{
            "index": 1,
            "confirmed_index": 3,
            "price": 10.0,
            "timestamp": "pivot-high",
        }]

        events = _historical_break_events(df, major_highs, [])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["direction"], "BULLISH")
        self.assertEqual(events[0]["break_timestamp"], "candle-4")
        self.assertEqual(events[0]["event"], "BOS")

    def test_opposite_confirmed_break_changes_bos_to_choch(self):
        df = candle_frame(
            highs=[9, 9, 12, 11, 10],
            lows=[7, 8, 9, 8, 7],
            closes=[8, 9, 11, 10, 8],
        )
        major_highs = [{
            "index": 0,
            "confirmed_index": 1,
            "price": 10.0,
            "timestamp": "pivot-high",
        }]
        major_lows = [{
            "index": 1,
            "confirmed_index": 2,
            "price": 9.0,
            "timestamp": "pivot-low",
        }]

        events = _historical_break_events(df, major_highs, major_lows)

        self.assertEqual([event["event"] for event in events], ["BOS", "CHoCH"])
        self.assertEqual([event["direction"] for event in events], ["BULLISH", "BEARISH"])
        self.assertEqual(events[1]["prior_bias"], "BULLISH")
        self.assertEqual(events[1]["updated_bias"], "BEARISH")


class MarketStructureIntegrationTests(unittest.TestCase):
    def test_minor_pivot_cannot_create_external_structure_event(self):
        closes = [5.0] * 29 + [12.0]
        df = candle_frame(
            highs=[13.0] * len(closes),
            lows=[4.0] * len(closes),
            closes=closes,
        )
        minor_high = [{
            "index": 1,
            "confirmed_index": 1,
            "price": 10.0,
            "timestamp": "minor-high",
        }]

        with patch(
            "engine.market_structure._confirmed_pivots",
            side_effect=[(minor_high, []), ([], [])],
        ):
            result = analyze_market_structure(df)

        self.assertEqual(result["minor_swing_highs"][0]["timestamp"], "minor-high")
        self.assertEqual(result["major_swing_highs"], [])
        self.assertEqual(result["events"], [])

    def test_no_confirmed_swings_produce_neutral_score_and_low_confidence(self):
        size = 30
        df = candle_frame(
            highs=[10.0] * size,
            lows=[9.0] * size,
            closes=[9.5] * size,
        )

        result = analyze_market_structure(df)

        self.assertEqual(result["score"], 50.0)
        self.assertEqual(result["score_components"]["major_high_balance"], 0.0)
        self.assertEqual(result["score_components"]["major_low_balance"], 0.0)
        self.assertEqual(result["score_components"]["confidence"], "LOW")


class CandleDataQualityTests(unittest.TestCase):
    def test_candle_conversion_rejects_empty_rows_and_unknown_interval(self):
        with self.assertRaisesRegex(ValueError, "no candles"):
            binance_rows_to_df([], interval="1h")
        with self.assertRaisesRegex(ValueError, "Unsupported Binance interval"):
            binance_rows_to_df([binance_row(0)], interval="15m")

    def test_open_candle_is_excluded_from_analysis_data(self):
        open_candle = binance_row(60 * 60 * 1000)
        open_candle[6] = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000) + 60_000

        df = binance_rows_to_df([binance_row(0), open_candle], interval="1h")

        self.assertEqual(len(df), 1)
        self.assertEqual(df.attrs["data_quality"]["raw_rows"], 2)
        self.assertEqual(df.attrs["data_quality"]["closed_candles"], 1)

    def test_timeframe_analysis_exposes_candle_quality(self):
        hour = 60 * 60 * 1000
        rows = [binance_row(i * hour) for i in range(220)]

        result = analyze_timeframe(rows, interval="1h")

        self.assertEqual(result["status"], "PROVISIONAL")
        self.assertEqual(result["data_quality"]["status"], "OK")
        self.assertEqual(result["data_quality"]["closed_candles"], 220)

    def test_four_hour_analysis_exposes_macd_inputs_and_divergence(self):
        four_hours = 4 * 60 * 60 * 1000
        rows = [binance_row(i * four_hours) for i in range(220)]

        result = analyze_timeframe(rows, interval="4h")

        self.assertIsNotNone(result["macd_divergence"])
        self.assertEqual(result["macd_divergence"]["direction"], "NONE")
        for key in ("ema20", "ema50", "ema200", "rsi14", "macd", "macd_signal", "macd_hist", "atr_pct", "bbw"):
            self.assertIn(key, result["indicators"])

    def test_insufficient_history_returns_count_and_quality(self):
        rows = [binance_row(i * 60 * 60 * 1000) for i in range(100)]

        result = analyze_timeframe(rows, interval="1h")

        self.assertEqual(result["status"], "INSUFFICIENT_DATA")
        self.assertEqual(result["valid_candles"], 100)
        self.assertEqual(result["data_quality"]["status"], "OK")

    def test_duplicate_out_of_order_and_missing_intervals_are_reported(self):
        hour = 60 * 60 * 1000
        rows = [
            binance_row(0),
            binance_row(2 * hour),
            binance_row(hour),
            binance_row(hour),
            binance_row(4 * hour),
        ]

        df = binance_rows_to_df(rows, interval="1h")
        quality = df.attrs["data_quality"]

        self.assertEqual(len(df), 4)
        self.assertEqual(quality["status"], "WARN")
        self.assertEqual(quality["duplicate_candles"], 1)
        self.assertEqual(quality["out_of_order_candles"], 1)
        self.assertEqual(quality["missing_intervals"], 1)

    def test_interval_mismatch_and_timestamp_alignment_are_reported(self):
        hour = 60 * 60 * 1000
        rows = [binance_row(0), binance_row(hour), binance_row(2 * hour)]

        df = binance_rows_to_df(rows, interval="4h")
        quality = df.attrs["data_quality"]

        self.assertEqual(quality["interval_mismatch_count"], 2)
        self.assertEqual(quality["timestamp_alignment_issues"], 2)
        self.assertEqual(quality["status"], "WARN")


if __name__ == "__main__":
    unittest.main()

import unittest

import pandas as pd

from engine.candlestick import detect_candlestick_patterns, recent_bias


def frame(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def declining(n=8, start=120.0, step=2.0):
    rows = []
    price = start
    for _ in range(n):
        rows.append([price, price + 0.5, price - step - 0.5, price - step])
        price -= step
    return rows


def rising(n=8, start=100.0, step=2.0):
    rows = []
    price = start
    for _ in range(n):
        rows.append([price, price + step + 0.5, price - 0.5, price + step])
        price += step
    return rows


def names(result, direction=None):
    return [p["name"] for p in result["patterns"] if direction in (None, p["direction"])]


class CandlestickPatternTests(unittest.TestCase):
    def test_bullish_engulfing_after_decline(self):
        rows = declining()
        last_close = rows[-1][3]
        rows.append([last_close + 0.5, last_close + 0.8, last_close - 1.5, last_close - 1.0])
        rows.append([last_close - 1.2, last_close + 2.0, last_close - 1.4, last_close + 1.5])

        result = detect_candlestick_patterns(frame(rows))

        self.assertIn("Bullish Engulfing", names(result, "BULLISH"))
        self.assertEqual(recent_bias(result, 3)["bias"], "BULLISH")

    def test_hammer_after_decline(self):
        rows = declining()
        c = rows[-1][3]
        rows.append([c, c + 0.6, c - 3.0, c + 0.5])

        result = detect_candlestick_patterns(frame(rows))

        self.assertIn("Hammer", names(result, "BULLISH"))

    def test_hammer_shape_without_downtrend_is_not_a_hammer(self):
        rows = rising()
        c = rows[-1][3]
        rows.append([c, c + 0.6, c - 3.0, c + 0.5])

        result = detect_candlestick_patterns(frame(rows))

        self.assertNotIn("Hammer", names(result))

    def test_morning_star(self):
        rows = declining()
        c = rows[-1][3]
        rows.append([c, c + 0.2, c - 4.2, c - 4.0])
        rows.append([c - 4.3, c - 4.0, c - 4.8, c - 4.5])
        rows.append([c - 4.4, c - 0.5, c - 4.6, c - 1.0])

        result = detect_candlestick_patterns(frame(rows))

        self.assertIn("Morning Star", names(result, "BULLISH"))

    def test_three_white_soldiers(self):
        rows = declining()
        c = rows[-1][3]
        rows.append([c, c + 2.1, c - 0.1, c + 2.0])
        rows.append([c + 1.0, c + 4.1, c + 0.9, c + 4.0])
        rows.append([c + 3.0, c + 6.1, c + 2.9, c + 6.0])

        result = detect_candlestick_patterns(frame(rows))

        self.assertIn("Three White Soldiers", names(result, "BULLISH"))

    def test_shooting_star_after_rise_is_bearish(self):
        rows = rising()
        c = rows[-1][3]
        rows.append([c, c + 3.0, c - 0.2, c - 0.5])

        result = detect_candlestick_patterns(frame(rows))

        self.assertIn("Shooting Star", names(result, "BEARISH"))
        self.assertEqual(recent_bias(result, 3)["bias"], "BEARISH")

    def test_last_candle_flags(self):
        rows = rising(3)

        result = detect_candlestick_patterns(frame(rows))

        self.assertTrue(result["last_candle"]["bullish"])
        self.assertTrue(result["last_candle"]["close_above_previous"])


if __name__ == "__main__":
    unittest.main()

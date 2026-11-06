import unittest

from engine.allocation import build_simulated_allocation


def candidate(symbol, strength, atr, quality=("OK", "OK", "OK"), setup="LONG_CANDIDATE"):
    return {
        "asset": {"symbol": symbol, "name": symbol},
        "technical_score": 40,
        "recommendation": {
            "status": "PROVISIONAL",
            "research_setup": setup,
            "pattern_strength_4H": strength,
            "patterns": {"4H": [{"name": "Hammer", "direction": "BULLISH"}]},
            "timeframe_data_quality": dict(zip(("1D", "4H", "1H"), quality)),
            "volatility_context_4H": {"atr_pct": atr},
        },
    }


class SimulatedAllocationTests(unittest.TestCase):
    def test_caps_exposure_and_sizes_by_pattern_strength_and_atr(self):
        result = build_simulated_allocation([
            candidate("BTC", 3, 1.0),
            candidate("ETH", 2, 2.0),
            candidate("SOL", 1, 3.0),
            candidate("XRP", 1, 4.0),
        ])

        self.assertEqual(result["status"], "PROVISIONAL_SIMULATION")
        self.assertEqual(len(result["allocations"]), 3)
        self.assertLessEqual(result["deployed_pct"], 30)
        self.assertLessEqual(max(item["weight_pct"] for item in result["allocations"]), 10)
        self.assertEqual(result["allocations"][0]["symbol"], "BTC")
        self.assertEqual(result["allocations"][0]["patterns_4h"], ["Hammer"])

    def test_single_candidate_leaves_most_capital_in_cash(self):
        result = build_simulated_allocation([candidate("ZEC", 2, 1.5)])

        self.assertEqual(result["allocations"][0]["weight_pct"], 10)
        self.assertEqual(result["cash_pct"], 90)

    def test_withholds_if_candle_quality_is_not_clean(self):
        result = build_simulated_allocation([candidate("BTC", 2, 1.0, ("OK", "WARN", "OK"))])

        self.assertEqual(result["status"], "WITHHELD")
        self.assertEqual(result["cash_pct"], 100)

    def test_ignores_non_candidates(self):
        result = build_simulated_allocation([candidate("BTC", 2, 1.0, setup="WATCH_1H_CONFIRMATION")])

        self.assertEqual(result["status"], "WITHHELD")


if __name__ == "__main__":
    unittest.main()

import unittest

from engine.allocation import build_simulated_allocation


def candidate(symbol, score, atr, quality=("OK", "OK", "OK"), setup="LONG_CANDIDATE"):
    return {
        "asset": {"symbol": symbol, "name": symbol},
        "technical_score": score,
        "recommendation": {
            "status": "PROVISIONAL",
            "research_setup": setup,
            "timeframe_data_quality": dict(zip(("1D", "4H", "1H"), quality)),
            "volatility_context_4H": {"atr_pct": atr},
        },
    }


class SimulatedAllocationTests(unittest.TestCase):
    def test_caps_crypto_exposure_and_sizes_by_score_and_atr(self):
        result = build_simulated_allocation([
            candidate("BTC", 82, 1.0),
            candidate("ETH", 75, 2.0),
            candidate("SOL", 70, 3.0),
        ])

        self.assertEqual(result["status"], "PROVISIONAL_SIMULATION")
        self.assertLessEqual(result["deployed_pct"], 50)
        self.assertLessEqual(max(item["weight_pct"] for item in result["allocations"]), 20)
        self.assertGreater(result["cash_pct"], 0)
        self.assertGreater(result["allocations"][0]["weight_pct"], result["allocations"][-1]["weight_pct"])

    def test_withholds_if_candle_quality_is_not_clean(self):
        result = build_simulated_allocation([candidate("BTC", 82, 1.0, ("OK", "WARN", "OK"))])

        self.assertEqual(result["status"], "WITHHELD")
        self.assertEqual(result["allocations"], [])
        self.assertEqual(result["cash_pct"], 100)

    def test_reduced_tier_is_capped_at_half_weight(self):
        result = build_simulated_allocation([
            candidate("ZEC", 67, 1.0, setup="LONG_CANDIDATE_REDUCED"),
        ])

        self.assertEqual(result["status"], "PROVISIONAL_SIMULATION")
        self.assertEqual(result["allocations"][0]["tier"], "REDUCED")
        self.assertLessEqual(result["allocations"][0]["weight_pct"], 10)
        self.assertEqual(result["cash_pct"], 90)

    def test_full_tier_ranks_ahead_of_reduced(self):
        result = build_simulated_allocation([
            candidate("ZEC", 80, 1.0, setup="LONG_CANDIDATE_REDUCED"),
            candidate("BTC", 70, 1.0),
        ])

        self.assertEqual(result["allocations"][0]["symbol"], "BTC")
        self.assertEqual(result["allocations"][0]["weight_pct"], 20)
        self.assertEqual(result["allocations"][1]["weight_pct"], 10)


if __name__ == "__main__":
    unittest.main()


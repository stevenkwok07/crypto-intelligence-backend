import unittest
from unittest.mock import AsyncMock, patch

import numpy as np
import pandas as pd
import httpx

from engine.scoring import (
    analyze_volume, classify, clamp, momentum_score, technical_score,
    trend_score, volatility_score, volume_score,
)
from indicators.core import add_indicators, rsi
from main import app
from services.analyzer import analyze_coin, summarize_timeframe_alignment


class IndicatorTests(unittest.TestCase):
    def test_rsi_preserves_warmup_and_handles_all_gains_and_flat_prices(self):
        rising = pd.Series(np.arange(20, dtype=float) + 100)
        flat = pd.Series([100.0] * 20)

        rising_rsi = rsi(rising, period=14)
        flat_rsi = rsi(flat, period=14)

        self.assertTrue(rising_rsi.iloc[:14].isna().all())
        self.assertEqual(rising_rsi.iloc[-1], 100.0)
        self.assertEqual(flat_rsi.iloc[-1], 50.0)

    def test_indicator_pipeline_adds_expected_columns_without_mutating_input(self):
        source = pd.DataFrame({
            "close": np.linspace(100, 120, 240),
            "high": np.linspace(101, 121, 240),
            "low": np.linspace(99, 119, 240),
            "volume": np.full(240, 1000.0),
        })
        original_columns = list(source.columns)

        result = add_indicators(source)

        self.assertEqual(list(source.columns), original_columns)
        for column in (
            "ema20", "ema50", "ema200", "rsi14", "macd", "macd_signal",
            "macd_hist", "relative_volume", "obv", "atr14", "atr_pct", "bbw",
        ):
            self.assertIn(column, result.columns)
        self.assertTrue(np.isfinite(result.iloc[-1][["ema200", "rsi14", "atr14"]]).all())


class ScoringTests(unittest.TestCase):
    def test_clamp_and_classification_boundaries(self):
        self.assertEqual(clamp(-5), 0)
        self.assertEqual(clamp(105), 100)
        self.assertEqual(
            [classify(value) for value in (29.99, 30, 44.99, 45, 64.99, 65, 79.99, 80)],
            [
                "STRONG_BEARISH", "BEARISH", "BEARISH", "NEUTRAL",
                "NEUTRAL", "BULLISH", "BULLISH", "STRONG_BULLISH",
            ],
        )

    def test_technical_score_uses_documented_component_weights(self):
        self.assertAlmostEqual(technical_score(100, 50, 0, 50), 58.3333333333)

    def test_volume_score_uses_direction_and_participation_confidence(self):
        size = 21
        frame = pd.DataFrame({
            "volume": [100.0] * size,
            "obv": [90.0 * i for i in range(size)],
            "obv_slope20": [1800.0] * size,
            "relative_volume": [0.65] * size,
        })

        result = analyze_volume(frame)

        self.assertEqual(result["directional_pressure"], "BUYING_PRESSURE")
        self.assertEqual(result["participation"], "LOW")
        self.assertAlmostEqual(result["normalized_obv_pressure"], 0.855)
        self.assertAlmostEqual(result["participation_confidence"], 0.5)
        self.assertEqual(result["score"], 58.55)

    def test_remaining_score_components_and_volume_alias(self):
        row = pd.DataFrame([{
            "close": 110.0, "ema20": 105.0, "ema50": 100.0,
            "ema200": 102.0, "rsi14": 100.0,
        }])
        with patch("engine.scoring.analyze_market_structure", return_value={"score": 85.0}):
            self.assertEqual(trend_score(row), 92.0)
        self.assertEqual(momentum_score(row), 75.0)
        self.assertEqual(volatility_score(row), 50.0)

        volume_frame = pd.DataFrame({
            "volume": [100.0] * 21,
            "obv": [90.0 * i for i in range(21)],
            "obv_slope20": [1800.0] * 21,
            "relative_volume": [1.0] * 21,
        })
        self.assertEqual(volume_score(volume_frame), analyze_volume(volume_frame)["score"])

    def test_alignment_labels_are_descriptive_for_each_state(self):
        def analysis(daily, swing, hourly):
            return {
                tf: {"market_structure": {"trend": trend, "event_bias": trend}}
                for tf, trend in (("1D", daily), ("4H", swing), ("1H", hourly))
            }

        scenarios = [
            (("BULLISH", "BULLISH", "BULLISH"), "FULL_ALIGNMENT"),
            (("BEARISH", "BEARISH", "MIXED"), "MACRO_SWING_ALIGNED_HOURLY_MIXED"),
            (("BEARISH", "BULLISH", "BULLISH"), "SWING_CONFIRMATION_WITHOUT_MACRO"),
            (("BEARISH", "BULLISH", "MIXED"), "MACRO_SWING_CONFLICT"),
            (("MIXED", "MIXED", "MIXED"), "MIXED_OR_UNCONFIRMED"),
        ]
        for trends, expected in scenarios:
            with self.subTest(trends=trends):
                self.assertEqual(summarize_timeframe_alignment(analysis(*trends))["status"], expected)
        self.assertEqual(
            summarize_timeframe_alignment({})["status"], "INCOMPLETE"
        )


class AnalyzerServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_analyze_coin_combines_timeframes_and_preserves_roles(self):
        frame_results = {
            "daily": {"status": "PROVISIONAL", "technical_score": 60, "market_structure": {"trend": "MIXED", "event_bias": "MIXED"}},
            "swing": {"status": "PROVISIONAL", "technical_score": 80, "market_structure": {"trend": "MIXED", "event_bias": "MIXED"}},
            "hourly": {"status": "PROVISIONAL", "technical_score": 50, "market_structure": {"trend": "MIXED", "event_bias": "MIXED"}},
        }
        with (
            patch("services.analyzer.get_coin", new_callable=AsyncMock, return_value={"symbol": "btc", "name": "Bitcoin"}),
            patch("services.analyzer.get_klines", new_callable=AsyncMock, side_effect=["daily", "swing", "hourly"]) as get_klines,
            patch("services.analyzer.analyze_timeframe", side_effect=frame_results.get),
        ):
            result = await analyze_coin("btc-bitcoin")

        self.assertEqual(result["technical_score"], 70.5)
        self.assertEqual(result["classification"], "BULLISH")
        self.assertEqual(result["timeframe_role"]["4H"], "primary_swing_score")
        self.assertEqual(result["timeframe_alignment"]["status"], "MIXED_OR_UNCONFIRMED")
        self.assertEqual(result["recommendation"]["status"], "WITHHELD")
        self.assertFalse(result["recommendation"]["eligible_for_automatic_allocation"])
        get_klines.assert_any_await("BTCUSDT", "1d", 500)
        get_klines.assert_any_await("BTCUSDT", "4h", 500)
        get_klines.assert_any_await("BTCUSDT", "1h", 500)

    async def test_invalid_symbol_is_rejected_before_market_data_requests(self):
        with (
            patch("services.analyzer.get_coin", new_callable=AsyncMock, return_value={"symbol": "BTC!"}),
            patch("services.analyzer.get_klines", new_callable=AsyncMock) as get_klines,
        ):
            with self.assertRaises(ValueError):
                await analyze_coin("bad-asset")

        get_klines.assert_not_awaited()

    async def test_missing_timeframe_does_not_issue_combined_score(self):
        frame_results = {
            "daily": {"status": "PROVISIONAL", "technical_score": 60},
            "swing": {"status": "DATA_UNAVAILABLE", "error": "offline"},
            "hourly": {"status": "PROVISIONAL", "technical_score": 50},
        }
        with (
            patch("services.analyzer.get_coin", new_callable=AsyncMock, return_value={"symbol": "BTC", "name": "Bitcoin"}),
            patch("services.analyzer.get_klines", new_callable=AsyncMock, side_effect=["daily", "swing", "hourly"]),
            patch("services.analyzer.analyze_timeframe", side_effect=frame_results.get),
        ):
            result = await analyze_coin("btc-bitcoin")

        self.assertEqual(result["status"], "MULTI_TIMEFRAME_INCOMPLETE")
        self.assertEqual(result["classification"], "INSUFFICIENT_DATA")
        self.assertNotIn("technical_score", result)


class ApiRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_health_route(self):
        response = await self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    async def test_market_coins_scan_and_limit_validation(self):
        with (
            patch("main.get_market_overview", new_callable=AsyncMock, return_value={"assets_sampled": 2}) as overview,
            patch("main.get_coin_universe", new_callable=AsyncMock, return_value={"count": 1, "assets": [{"id": "btc-bitcoin"}]}) as coins,
            patch("main.scan_coins", new_callable=AsyncMock, return_value={"status": "UNIVERSE_ONLY", "count": 1, "assets": []}) as scan,
        ):
            self.assertEqual((await self.client.get("/api/market/overview")).json()["assets_sampled"], 2)
            self.assertEqual((await self.client.get("/api/coins?limit=5")).json()["count"], 1)
            self.assertEqual((await self.client.get("/api/scan?limit=5")).json()["status"], "UNIVERSE_ONLY")
            self.assertEqual((await self.client.get("/api/coins?limit=0")).status_code, 422)

        overview.assert_awaited_once()
        coins.assert_awaited_once_with(limit=5)
        scan.assert_awaited_once_with(limit=5)

    async def test_analysis_route_maps_validation_and_provider_errors(self):
        with patch("main.analyze_coin", new_callable=AsyncMock, side_effect=ValueError("unknown coin")):
            response = await self.client.get("/api/coin/not-a-coin/analysis")
        self.assertEqual(response.status_code, 404)

        with patch("main.analyze_coin", new_callable=AsyncMock, side_effect=RuntimeError("provider offline")):
            response = await self.client.get("/api/coin/btc-bitcoin/analysis")
        self.assertEqual(response.status_code, 502)
        self.assertIn("provider offline", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()

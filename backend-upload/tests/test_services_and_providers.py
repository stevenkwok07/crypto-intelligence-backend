import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

from config import settings
from providers import binance, coinpaprika
from providers.http import get_json
from services import market, scanner


class MarketServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_market_overview_sums_only_available_market_caps(self):
        tickers = [
            {"quotes": {"USD": {"market_cap": 100}}},
            {"quotes": {"USD": {"market_cap": None}}},
            {"quotes": {}},
            {"quotes": {"USD": {"market_cap": 250}}},
        ]
        with patch("services.market.get_tickers", new_callable=AsyncMock, return_value=tickers):
            result = await market.get_market_overview()

        self.assertEqual(result["assets_sampled"], 2)
        self.assertEqual(result["sample_market_cap_usd"], 350)
        self.assertEqual(result["source"], "CoinPaprika")

    async def test_coin_universe_maps_quotes_and_handles_missing_fields(self):
        tickers = [{
            "id": "btc-bitcoin", "symbol": "BTC", "name": "Bitcoin", "rank": 1,
            "quotes": {"USD": {"price": 10, "volume_24h": 20, "market_cap": 30, "percent_change_24h": 4}},
        }, {"id": "unknown", "quotes": {}}]
        with patch("services.market.get_tickers", new_callable=AsyncMock, return_value=tickers) as get_tickers:
            result = await market.get_coin_universe(limit=2)

        get_tickers.assert_awaited_once_with(2)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["assets"][0]["price_usd"], 10)
        self.assertIsNone(result["assets"][1]["price_usd"])

    async def test_scanner_analyzes_and_ranks_assets_but_withholds_allocations(self):
        assets = [
            {"id": "btc-bitcoin", "symbol": "BTC"},
            {"id": "eth-ethereum", "symbol": "ETH"},
        ]
        universe = {"count": 2, "assets": assets}
        analysis = {
            "technical_score": 72,
            "classification": "BULLISH",
            "status": "PROVISIONAL_MULTI_TIMEFRAME",
            "recommendation": {
                "status": "PROVISIONAL",
                "research_setup": "LONG_CANDIDATE",
                "timeframe_data_quality": {"1D": "OK", "4H": "OK", "1H": "OK"},
                "volatility_context_4H": {"atr_pct": 1.2},
            },
        }
        with (
            patch("services.scanner.get_coin_universe", new_callable=AsyncMock, return_value=universe) as get_universe,
            patch("services.scanner.analyze_coin", new_callable=AsyncMock, return_value=analysis),
        ):
            result = await scanner.scan_coins(limit=7)

        get_universe.assert_awaited_once_with(22)
        self.assertEqual(result["status"], "RESEARCH_SCAN")
        self.assertEqual(result["assets"][0]["asset"], assets[0])
        self.assertEqual(result["research_candidates"], 2)
        self.assertEqual(result["system_recommendation"]["status"], "PROVISIONAL_SIMULATION")
        self.assertLessEqual(result["system_recommendation"]["deployed_pct"], 50)

    async def test_scanner_skips_stablecoins_and_keeps_requested_count(self):
        assets = [
            {"id": "btc-bitcoin", "symbol": "BTC"},
            {"id": "usdt-tether", "symbol": "USDT"},
            {"id": "eth-ethereum", "symbol": "ETH"},
            {"id": "usdc-usd-coin", "symbol": "USDC"},
            {"id": "sol-solana", "symbol": "SOL"},
        ]
        analysis = {"technical_score": 50, "recommendation": {"status": "NO_SETUP"}}
        with (
            patch("services.scanner.get_coin_universe", new_callable=AsyncMock, return_value={"count": 5, "assets": assets}),
            patch("services.scanner.analyze_coin", new_callable=AsyncMock, return_value=analysis),
        ):
            result = await scanner.scan_coins(limit=3)

        symbols = [item["asset"]["symbol"] for item in result["assets"]]
        self.assertEqual(sorted(symbols), ["BTC", "ETH", "SOL"])
        self.assertEqual(result["count"], 3)


class ProviderWrapperTests(unittest.IsolatedAsyncioTestCase):
    async def test_coinpaprika_tickers_applies_limit_and_coin_url(self):
        tickers = [{"id": "btc"}, {"id": "eth"}]
        with patch("providers.coinpaprika.get_json", new_callable=AsyncMock, return_value=tickers) as get_data:
            result = await coinpaprika.get_tickers(1)
            self.assertEqual(result, tickers[:1])
            get_data.assert_awaited_once_with(f"{settings.coinpaprika_base}/tickers")

        with patch("providers.coinpaprika.get_json", new_callable=AsyncMock, return_value={"id": "btc"}) as get_data:
            result = await coinpaprika.get_coin("btc-bitcoin")
            self.assertEqual(result["id"], "btc")
            get_data.assert_awaited_once_with(f"{settings.coinpaprika_base}/coins/btc-bitcoin")

    async def test_binance_wrapper_normalizes_symbol_and_caps_limit(self):
        with patch("providers.binance.get_json", new_callable=AsyncMock, return_value=[]) as get_data:
            await binance.get_klines("btcusdt", "4h", 5000)

        get_data.assert_awaited_once_with(
            f"{settings.binance_base}/api/v3/klines",
            {"symbol": "BTCUSDT", "interval": "4h", "limit": 1000},
        )

    async def test_remaining_binance_market_data_wrappers_build_expected_requests(self):
        with patch("providers.binance.get_json", new_callable=AsyncMock, return_value={}) as get_data:
            await binance.get_book_ticker("ethusdt")
            get_data.assert_awaited_with(
                f"{settings.binance_base}/api/v3/ticker/bookTicker",
                {"symbol": "ETHUSDT"},
            )
            await binance.get_depth("ethusdt", limit=50)
            get_data.assert_awaited_with(
                f"{settings.binance_base}/api/v3/depth",
                {"symbol": "ETHUSDT", "limit": 50},
            )

    async def test_coinpaprika_daily_ohlcv_builds_date_range(self):
        with patch("providers.coinpaprika.get_json", new_callable=AsyncMock, return_value=[]) as get_data:
            await coinpaprika.get_ohlcv_daily("btc-bitcoin", limit=30)

        args, kwargs = get_data.await_args
        self.assertEqual(args[0], f"{settings.coinpaprika_base}/coins/btc-bitcoin/ohlcv/historical")
        start = date.fromisoformat(args[1]["start"])
        end = date.fromisoformat(args[1]["end"])
        self.assertEqual((end - start).days, 30)
        self.assertEqual(kwargs, {})

    async def test_http_provider_sends_headers_and_returns_json(self):
        expected = {"ok": True}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return expected

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            async def get(self, url, params=None, headers=None):
                self.request = (url, params, headers)
                return FakeResponse()

        fake_client = FakeClient()
        with patch("providers.http.httpx.AsyncClient", return_value=fake_client) as client_class:
            result = await get_json("https://example.test/data", {"limit": 2})

        self.assertEqual(result, expected)
        self.assertEqual(
            fake_client.request,
            ("https://example.test/data", {"limit": 2}, {"User-Agent": "CryptoIntelligence/1.0"}),
        )
        client_class.assert_called_once_with(timeout=settings.request_timeout)

    async def test_http_provider_propagates_http_status_errors(self):
        class FakeResponse:
            def raise_for_status(self):
                raise RuntimeError("provider rejected request")

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            async def get(self, *_args, **_kwargs):
                return FakeResponse()

        with patch("providers.http.httpx.AsyncClient", return_value=FakeClient()):
            with self.assertRaisesRegex(RuntimeError, "provider rejected request"):
                await get_json("https://example.test/data")


if __name__ == "__main__":
    unittest.main()


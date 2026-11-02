# Crypto Intelligence API

FastAPI backend for closed-candle 1D / 4H / 1H crypto market analysis.

## Local run

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive API docs. Health check: `GET /api/health`.

## Endpoints

- `GET /api/health`
- `GET /api/market/overview`
- `GET /api/coins?limit=100`
- `GET /api/coin/{coin_id}/analysis`
- `GET /api/scan?limit=10` (ranked 1D / 4H / 1H screen with a provisional, capped capital simulation when clean confirmed setups exist)

## Environment

Copy `.env.example` to `.env` for local configuration. Set `CORS_ORIGINS` to comma-separated exact origins when connecting a hosted frontend, such as `https://your-site.netlify.app`. Do not commit `.env` or provider credentials.

## Deployment

Use `backend-upload` as the service root. Install dependencies from `requirements.txt`, then start with:

```sh
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
```

The service needs outbound HTTPS access to the public CoinPaprika and Kraken Spot endpoints. It has no exchange credentials and does not submit orders. Kraken's public OHLC endpoint is used because the deployed Render IP received Binance HTTP 418 responses. Candle source is Kraken Spot; quotes are USD markets.

## Current model limitations

The technical screen and weights are provisional. Scores are heuristic, not probabilities; market liquidity and out-of-sample performance with trading costs have not been validated. The scanner ranks at most 10 assets, then uses the top three clean long candidates. Weight strength is proportional to `(technical_score - 60) / ATR_4H_pct`, capped at 20% of capital per asset and 50% total; the rest stays in cash. Bad/incomplete candles or no confirmed setup yield no allocation. It does not execute orders.

Run tests from this directory with `python -m unittest discover -s tests -v`.

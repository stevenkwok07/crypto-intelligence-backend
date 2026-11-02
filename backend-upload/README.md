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
- `GET /api/scan?limit=30` (universe preview only; not a scored market scanner)

## Environment

Copy `.env.example` to `.env` for local configuration. Set `CORS_ORIGINS` to comma-separated exact origins when connecting a hosted frontend, such as `https://your-site.netlify.app`. Do not commit `.env` or provider credentials.

## Deployment

Use `backend` as the service root. Install dependencies from `requirements.txt`, then start with:

```sh
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
```

The service needs outbound HTTPS access to public CoinPaprika and Binance data endpoints. It has no exchange credentials and does not submit orders.

## Current model limitations

The technical screen is provisional. Scores are heuristic, not probabilities; candle data, market liquidity and out-of-sample performance with trading costs have not been validated. Recommendation status stays withheld until its evidence gates pass. It does not produce automatic portfolio weights or execute orders.

Run tests from this directory with `python -m unittest discover -s tests -v`.

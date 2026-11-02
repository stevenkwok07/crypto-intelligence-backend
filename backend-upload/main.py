from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from services.market import get_market_overview, get_coin_universe
from services.analyzer import analyze_coin
from services.scanner import scan_coins
from config import settings

app = FastAPI(title="Crypto Intelligence API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "project": "crypto-intelligence"}

@app.get("/api/market/overview")
async def market_overview():
    return await get_market_overview()

@app.get("/api/coins")
async def coins(limit: int = Query(100, ge=1, le=500)):
    return await get_coin_universe(limit=limit)

@app.get("/api/coin/{coin_id}/analysis")
async def coin_analysis(coin_id: str):
    try:
        return await analyze_coin(coin_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Data provider error: {exc}")

@app.get("/api/scan")
async def scan(limit: int = Query(30, ge=1, le=100)):
    return await scan_coins(limit=limit)

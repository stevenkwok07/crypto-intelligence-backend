import httpx
from config import settings

async def get_json(url: str, params: dict | None = None):
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(url, params=params, headers={"User-Agent": "CryptoIntelligence/1.0"})
        response.raise_for_status()
        return response.json()

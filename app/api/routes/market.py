import asyncio

from fastapi import APIRouter, HTTPException, Query

from app.db.database import SessionLocal
from app.db.models import UserSettings
from app.dependencies import market_service
from app.market.symbol_resolver import resolve_symbol

router = APIRouter(prefix="/stocks", tags=["Market Data"])


def get_resolved(symbol: str) -> str:
    result = resolve_symbol(symbol)
    if not result["valid"]:
        raise HTTPException(status_code=400, detail="Invalid symbol format")
    return result["resolved_symbol"]


def _request_timeout() -> int:
    with SessionLocal() as db:
        record = db.query(UserSettings).first()
        return max(1, min(int((record.settings or {}).get("request_timeout", 30)), 180)) if record else 30


async def _market_call(func, *args, **kwargs):
    timeout = await asyncio.to_thread(_request_timeout)
    try:
        return await asyncio.wait_for(asyncio.to_thread(func, *args, **kwargs), timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail=f"Market data request timed out after {timeout} seconds. Retry shortly.") from exc


@router.get("/{symbol}")
async def get_company_profile(symbol: str):
    result = await _market_call(market_service.get_company_profile, get_resolved(symbol))
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Company profile unavailable"))
    return result


@router.get("/{symbol}/quote")
async def get_quote(symbol: str, refresh: bool = Query(False)):
    result = await _market_call(market_service.get_quote, get_resolved(symbol), refresh=refresh)
    if not result.get("success"):
        raise HTTPException(status_code=503, detail=result.get("error", "Quote unavailable from configured providers"))
    return result


@router.get("/{symbol}/history")
async def get_history(symbol: str, period: str = Query("1mo", pattern="^(1mo|3mo|6mo|1y|2y|5y)$"), interval: str = Query("1d", pattern="^(1d|1wk|1mo)$"), refresh: bool = Query(False)):
    result = await _market_call(market_service.get_history, get_resolved(symbol), period, interval, refresh=refresh)
    if not result.get("success"):
        raise HTTPException(status_code=503, detail=result.get("error", "Price history unavailable from configured providers"))
    return result


@router.get("/{symbol}/fundamentals")
async def get_fundamentals(symbol: str, refresh: bool = Query(False)):
    result = await _market_call(market_service.get_financials, get_resolved(symbol), refresh=refresh)
    if not result.get("success"):
        raise HTTPException(status_code=503, detail=result.get("error", "Fundamentals unavailable from configured providers"))
    return result


@router.get("/{symbol}/news")
async def get_news(symbol: str, refresh: bool = Query(False)):
    result = await _market_call(market_service.get_news_result, get_resolved(symbol), refresh)
    return {"symbol": symbol, **result}


@router.get("/{symbol}/technical")
async def get_technical(symbol: str, period: str = Query("6mo", pattern="^(1mo|3mo|6mo|1y|2y|5y)$"), interval: str = Query("1d", pattern="^(1d|1wk|1mo)$"), refresh: bool = Query(False)):
    result = await _market_call(market_service.get_technical_analysis, get_resolved(symbol), period=period, interval=interval, refresh=refresh)
    if not result.get("success"):
        raise HTTPException(status_code=503, detail=result.get("error", "Technical analysis unavailable"))
    return result

from fastapi import APIRouter, HTTPException, Query
from app.market.service import market_service
from app.market.symbol_resolver import resolve_symbol

router = APIRouter(prefix="/stocks", tags=["Market Data"])

def get_resolved(symbol: str):
    res = resolve_symbol(symbol)
    if not res["valid"]:
        raise HTTPException(status_code=400, detail="Invalid symbol format")
    return res["resolved_symbol"]

@router.get("/{symbol}")
def get_company_profile(symbol: str):
    resolved = get_resolved(symbol)
    result = market_service.get_company_profile(resolved)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Not found"))
    return result

@router.get("/{symbol}/quote")
def get_quote(symbol: str):
    resolved = get_resolved(symbol)
    result = market_service.get_quote(resolved)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Not found"))
    return result

@router.get("/{symbol}/history")
def get_history(symbol: str, period: str = Query("1mo", pattern="^(1mo|3mo|6mo|1y|2y|5y)$"), interval: str = Query("1d", pattern="^(1d|1wk|1mo)$")):
    resolved = get_resolved(symbol)
    result = market_service.get_history(resolved, period, interval)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Error fetching history"))
    return result

@router.get("/{symbol}/fundamentals")
def get_fundamentals(symbol: str):
    resolved = get_resolved(symbol)
    result = market_service.get_financials(resolved)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Not found"))
    return result

@router.get("/{symbol}/news")
def get_news(symbol: str):
    resolved = get_resolved(symbol)
    news = market_service.get_news(resolved)
    return {"symbol": resolved, "news": news}

@router.get("/{symbol}/technical")
def get_technical(symbol: str):
    resolved = get_resolved(symbol)
    result = market_service.get_technical_analysis(resolved)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Error calculating technicals"))
    return result

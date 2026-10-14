import asyncio

from fastapi import APIRouter, Query

from app.market.news_feed import get_news_feed

router = APIRouter(prefix="/news", tags=["News"])


@router.get("")
@router.get("/feed")
async def get_feed(
    symbols: str = Query("AAPL,NVDA,MSFT,GOOGL,RELIANCE.NS,TCS.NS,HDFCBANK.NS,INFY.NS", max_length=1000),
    market: str = Query("all", pattern="^(all|us|india)$"),
    limit: int = Query(80, ge=1, le=100),
    days: int = Query(7, ge=1, le=30),
):
    requested_symbols = [symbol.strip() for symbol in symbols.split(",") if symbol.strip()][:10]
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(get_news_feed, requested_symbols, market, limit, days),
            timeout=45,
        )
    except asyncio.TimeoutError:
        return {"success": False, "news": [], "total_available": 0, "has_more": False,
                "source_count": 0, "publishers": [], "data_status": "TIMEOUT",
                "error": "The news providers did not respond in time. Try refreshing shortly."}

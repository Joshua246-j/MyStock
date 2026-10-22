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
    cache_key = f"news_feed:{market}:{symbols}:{limit}:{days}"
    try:
        from app.db.cache import get_cache, set_cache
        cached = await asyncio.to_thread(get_cache, cache_key)
        if cached and isinstance(cached, dict) and cached.get("success"):
            return cached
    except Exception:
        pass

    requested_symbols = [symbol.strip() for symbol in symbols.split(",") if symbol.strip()][:10]
    try:
        feed = await asyncio.wait_for(
            asyncio.to_thread(get_news_feed, requested_symbols, market, limit, days),
            timeout=45,
        )
        if feed and feed.get("success"):
            try:
                await asyncio.to_thread(set_cache, cache_key, feed, ttl_seconds=180, source="news_feed")
            except Exception:
                pass
        return feed
    except asyncio.TimeoutError:
        return {"success": False, "news": [], "total_available": 0, "has_more": False,
                "source_count": 0, "publishers": [], "data_status": "TIMEOUT",
                "error": "The news providers did not respond in time. Try refreshing shortly."}

from fastapi import APIRouter, HTTPException, Query
from app.market.symbol_resolver import resolve_symbol

router = APIRouter(tags=["Symbol Search"])

POPULAR_SYMBOLS = [
    {"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ"},
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "exchange": "NASDAQ"},
    {"symbol": "MSFT", "name": "Microsoft Corporation", "exchange": "NASDAQ"},
    {"symbol": "GOOGL", "name": "Alphabet Inc.", "exchange": "NASDAQ"},
    {"symbol": "AMZN", "name": "Amazon.com Inc.", "exchange": "NASDAQ"},
    {"symbol": "META", "name": "Meta Platforms Inc.", "exchange": "NASDAQ"},
    {"symbol": "TSLA", "name": "Tesla Inc.", "exchange": "NASDAQ"},
    {"symbol": "RELIANCE.NS", "name": "Reliance Industries", "exchange": "NSE"},
    {"symbol": "TCS.NS", "name": "Tata Consultancy Services", "exchange": "NSE"},
    {"symbol": "HDFCBANK.NS", "name": "HDFC Bank", "exchange": "NSE"},
    {"symbol": "INFY.NS", "name": "Infosys Ltd", "exchange": "NSE"},
]


@router.get("/symbols/popular")
def get_popular_symbols():
    return {"symbols": POPULAR_SYMBOLS}


@router.get("/symbols/resolve")
def resolve_symbol_query(symbol: str = Query(...)):
    result = resolve_symbol(symbol)
    if not result["valid"]:
        raise HTTPException(status_code=422, detail="Symbol contains unsupported characters")
    return result


@router.get("/symbols/resolve/{symbol}")
def resolve_market_symbol(symbol: str):
    result = resolve_symbol(symbol)
    if not result["valid"]:
        raise HTTPException(status_code=422, detail="Symbol contains unsupported characters")
    return result


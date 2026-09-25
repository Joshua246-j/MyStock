from fastapi import APIRouter, HTTPException
from app.market.symbol_resolver import resolve_symbol

router = APIRouter(tags=["Symbol Search"])


@router.get("/symbols/resolve/{symbol}")
def resolve_market_symbol(symbol: str):
    result = resolve_symbol(symbol)
    if not result["valid"]:
        raise HTTPException(status_code=422, detail="Symbol contains unsupported characters")
    return result

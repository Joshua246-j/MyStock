import re
from typing import Dict, Any

# Simple heuristics for Indian market and Global market tickers
def normalize_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    
    # If the user enters an Indian stock without exchange suffix, default to .NS (National Stock Exchange)
    # This is a heuristic. In a real production system, this would query a master database.
    indian_bluechips = {"TCS", "INFY", "RELIANCE", "HDFCBANK", "ICICIBANK", "SBIN", "WIPRO", "HINDUNILVR", "ITC", "BHARTIARTL"}
    
    if symbol in indian_bluechips:
        return f"{symbol}.NS"
        
    return symbol

def validate_symbol(symbol: str) -> bool:
    # A valid ticker generally only contains letters, dots, or hyphens.
    if not symbol:
        return False
    if not re.match(r"^[A-Z0-9.\-]+$", symbol.upper()):
        return False
    return True

def resolve_symbol(symbol: str) -> Dict[str, Any]:
    valid = validate_symbol(symbol)
    if not valid:
        return {
            "input": symbol,
            "resolved_symbol": None,
            "exchange": "Unknown",
            "market": "Unknown",
            "valid": False
        }

    resolved = normalize_symbol(symbol)
    
    market = "Global"
    exchange = "Various"
    
    if resolved.endswith(".NS"):
        market = "India"
        exchange = "NSE"
    elif resolved.endswith(".BO"):
        market = "India"
        exchange = "BSE"
    elif resolved.endswith(".L"):
        market = "UK"
        exchange = "LSE"
    elif resolved.endswith(".TO"):
        market = "Canada"
        exchange = "TSX"
    else:
        market = "US/Global"
        exchange = "NYSE/NASDAQ"
        
    return {
        "input": symbol,
        "resolved_symbol": resolved,
        "exchange": exchange,
        "market": market,
        "valid": True
    }

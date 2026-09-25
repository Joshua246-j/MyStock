import re
from typing import Dict, Any

INDIAN_COMPANY_ALIASES = {
    "reliance industries": "RELIANCE.NS", "reliance": "RELIANCE.NS",
    "tata consultancy services": "TCS.NS", "tcs": "TCS.NS",
    "hdfc bank": "HDFCBANK.NS", "hdfc": "HDFCBANK.NS",
    "icici bank": "ICICIBANK.NS", "state bank of india": "SBIN.NS", "sbi": "SBIN.NS",
    "infosys": "INFY.NS", "bharti airtel": "BHARTIARTL.NS", "airtel": "BHARTIARTL.NS",
    "nifty 50": "^NSEI", "nifty": "^NSEI", "sensex": "^BSESN",
}

# Simple heuristics for Indian market and Global market tickers
def normalize_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    
    # If the user enters an Indian stock without exchange suffix, default to .NS (National Stock Exchange)
    # This is a heuristic. In a real production system, this would query a master database.
    indian_bluechips = {
        "TCS", "INFY", "RELIANCE", "HDFCBANK", "ICICIBANK", "SBIN", "WIPRO",
        "HINDUNILVR", "ITC", "BHARTIARTL", "LT", "BAJFINANCE", "KOTAKBANK",
        "AXISBANK", "MARUTI", "TATAMOTORS", "TATASTEEL", "SUNPHARMA", "ADANIENT",
        "ONGC", "NTPC", "POWERGRID", "ULTRACEMCO", "ASIANPAINT", "TITAN",
        "HCLTECH", "TECHM", "TATACONSUM", "NESTLEIND", "COALINDIA", "JSWSTEEL",
        "INDUSINDBK", "BAJAJFINSV", "GRASIM", "DRREDDY", "CIPLA", "EICHERMOT",
        "APOLLOHOSP", "HEROMOTOCO", "DIVISLAB", "BPCL", "BRITANNIA", "UPL",
    }
    
    if symbol in indian_bluechips:
        return f"{symbol}.NS"
        
    return symbol

def validate_symbol(symbol: str) -> bool:
    # A valid ticker generally only contains letters, dots, or hyphens.
    if not symbol:
        return False
    # Yahoo Finance's NSE and BSE index symbols use a leading caret (for example ^NSEI).
    if not re.match(r"^\^?[A-Z0-9][A-Z0-9.\-]*$", symbol.upper()):
        return False
    return True

def resolve_symbol(symbol: str) -> Dict[str, Any]:
    alias = INDIAN_COMPANY_ALIASES.get(symbol.strip().casefold())
    if alias:
        symbol = alias
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
    
    if resolved.endswith(".NS") or resolved == "^NSEI":
        market = "India"
        exchange = "NSE"
    elif resolved.endswith(".BO") or resolved == "^BSESN":
        market = "India"
        exchange = "BSE"
    elif resolved.endswith(".L"):
        market = "UK"
        exchange = "LSE"
    elif resolved.endswith(".TO"):
        market = "Canada"
        exchange = "TSX"
    elif resolved.endswith(".AX"):
        market = "Australia"
        exchange = "ASX"
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

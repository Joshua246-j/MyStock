import pandas as pd
import numpy as np
from typing import Dict, Any

def calculate_technical_indicators(df: pd.DataFrame) -> Dict[str, Any]:
    """Calculates SMA, EMA, RSI, MACD from a DataFrame with a 'Close' column."""
    if df.empty or 'Close' not in df.columns:
        return {"success": False, "error": "Missing 'Close' column"}

    try:
        # Sort by date if Date is present
        if 'Date' in df.columns:
            df = df.sort_values(by='Date')

        close = df['Close']
        
        # SMA 20, 50
        sma_20 = close.rolling(window=20).mean().iloc[-1]
        sma_50 = close.rolling(window=50).mean().iloc[-1]
        
        # EMA 20
        ema_20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
        
        # RSI 14
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]
        
        # MACD (12, 26, 9)
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        macd = ema_12 - ema_26
        signal = macd.ewm(span=9, adjust=False).mean()
        current_macd = macd.iloc[-1]
        current_signal = signal.iloc[-1]

        # Clean NaN values
        def clean_val(val):
            return None if pd.isna(val) else float(val)

        return {
            "success": True,
            "metrics": {
                "SMA_20": clean_val(sma_20),
                "SMA_50": clean_val(sma_50),
                "EMA_20": clean_val(ema_20),
                "RSI_14": clean_val(current_rsi),
                "MACD": clean_val(current_macd),
                "MACD_Signal": clean_val(current_signal)
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

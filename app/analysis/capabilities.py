"""Maintainable application-capability registry and feature intelligence for MyStock AI."""
from __future__ import annotations

import re
from typing import Any

APPLICATION_CAPABILITIES: dict[str, dict[str, Any]] = {
    "market_data": {
        "title": "Real-time & Historical Market Data",
        "endpoints": ["/api/stocks/{symbol}", "/api/stocks/{symbol}/financials"],
        "description": "Live and historical OHLCV pricing, multi-timeframe candle data, trading session stats, volume, and fundamental metrics.",
        "supported_exchanges": ["US (NYSE, NASDAQ)", "India (NSE, BSE)", "UK (LSE)", "Canada (TSX)", "Australia (ASX)"],
        "timeframes": ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
        "intervals": ["1d", "1wk", "1mo"],
        "fundamentals": ["P/E Ratio", "EPS", "Market Cap", "Debt-to-Equity", "Return on Equity (ROE)", "Profit Margins", "Dividend Yield"],
        "input_schema": {"symbol": "Ticker string, e.g., 'AAPL', 'NVDA', 'RELIANCE.NS', 'TCS.NS'"},
    },
    "technical_analysis": {
        "title": "Quantitative Technical Indicators & Modeling",
        "endpoints": ["/api/stocks/{symbol}/technical"],
        "description": "Calculates standard technical indicators and walk-forward ridge momentum models on historical price bars.",
        "indicators": [
            "Relative Strength Index (RSI 14)",
            "Moving Average Convergence Divergence (MACD 12, 26, 9)",
            "Simple Moving Averages (SMA 20, 50, 200)",
            "Exponential Moving Averages (EMA 20, 50)",
            "Bollinger Bands (20-day, 2 std dev)",
            "Average True Range (ATR 14 volatility)",
            "Historical Volatility & Maximum Drawdown",
            "Walk-forward Ridge Momentum Regression",
        ],
    },
    "forecasting": {
        "title": "Conformal Probabilistic Price Forecasting",
        "endpoints": ["/api/stocks/{symbol}/forecast", "/api/forecast/models", "/api/forecast/validate"],
        "description": "Multi-model price trajectory projections with calibrated nominal conformal prediction intervals, directional probability, and walk-forward backtest evaluation.",
        "horizons": ["1 session (next day)", "5 sessions (1 week)", "20 sessions (1 month)"],
        "models": ["Auto-selection", "Ridge Momentum", "Mean Reversion", "Random Walk Naive Baseline", "Multi-model Ensemble"],
        "metrics": ["Expected return (%)", "Calibrated conformal confidence interval (lower/upper bound)", "Directional probability (% bullish tilt)", "Out-of-sample MAE (%)", "Directional accuracy / hit rate (%)", "Model disagreement analysis"],
        "important_disclaimer": "All forecasts are probabilistic quantitative estimates for research and informational purposes only. They are NOT guaranteed outcomes or investment advice.",
    },
    "news_intelligence": {
        "title": "Financial News Intelligence & Feed",
        "endpoints": ["/api/news/feed", "/api/news/{symbol}"],
        "description": "Real-time streaming headlines and news articles from Google News RSS feeds with ticker extraction, deduplication, and sentiment analysis.",
        "features": ["Regional business feeds (US & India)", "Publisher attribution and direct links", "Article summaries", "Ticker tag linking"],
    },
    "document_rag": {
        "title": "Document Knowledge Base & Hybrid RAG",
        "endpoints": ["/api/documents", "/api/documents/rag/search"],
        "description": "Document ingestion, text extraction, chunking, and hybrid semantic-lexical retrieval using FAISS vector store and SQLite FTS5 with Reciprocal Rank Fusion (RRF).",
        "supported_file_types": ["PDF (.pdf)", "Word Document (.docx)", "Plain Text (.txt)", "HTML (.html)", "Webpage URL (.web)"],
        "tabular_datasets": ["CSV (.csv)", "Excel (.xlsx, .xls) profiling with summary statistics, missingness, and column distributions"],
        "search_modes": ["Hybrid (vector + keyword)", "Semantic (FAISS)", "Keyword (SQLite BM25)", "Ticker metadata scoped"],
    },
    "web_research": {
        "title": "Live Web Research & Crawling",
        "endpoints": ["Integrated into /api/chat"],
        "description": "Real-time web research engine combining DuckDuckGo multi-source search and Google News RSS, with SSRF-protected webpage extraction, robots.txt compliance, and automatic source citation.",
        "capabilities": ["Multi-source search", "Publisher metadata extraction", "Clean DOM text extraction without ads/scripts", "Inline source citation and structured source cards"],
    },
    "conversation_and_memory": {
        "title": "Persistent Conversations & User Memory",
        "endpoints": ["/api/chat", "/api/chat/stream", "/api/chat/sessions", "/api/chat/sessions/{id}/branch", "/api/chat/sessions/{id}/pin", "/api/memory"],
        "description": "Full conversation persistence in SQLite, conversation branching from any message, session pinning/renaming, and persistent user memory for preferences and risk profile.",
        "features": ["Token-by-token streaming SSE", "Context-bounded turn management", "Conversation branching", "Saved user constraints & preferences"],
    },
    "settings_and_models": {
        "title": "Terminal Settings & Ollama Model Management",
        "endpoints": ["/api/settings", "/api/settings/schema", "/api/models", "/api/health"],
        "description": "Configuration management for local Ollama models, sampling parameters (temperature, top_p, top_k, repeat_penalty, seed), UI density, themes, and system health checks.",
    },
}

UNSUPPORTED_CAPABILITIES: list[str] = [
    "Live trade execution, brokerage order routing, or buy/sell placement (MyStock is an institutional research terminal, not an execution broker).",
    "Algorithmic execution of automated orders in user brokerage accounts.",
    "Handling real money, fiat/crypto deposits, withdrawals, or custody.",
    "Certified tax preparation or personal financial planner advisory sign-offs.",
    "Guaranteed price predictions or risk-free investment guarantees.",
]


def get_capability_registry() -> dict[str, Any]:
    """Return the structured capability registry."""
    return {
        "application_name": "MyStock AI Financial Terminal",
        "supported_capabilities": APPLICATION_CAPABILITIES,
        "unsupported_capabilities": UNSUPPORTED_CAPABILITIES,
    }


def is_capability_query(text: str) -> bool:
    """Detect if user query is asking about the application's features, capabilities, or usage."""
    lowered = text.casefold().strip()
    patterns = (
        r"\b(?:what (?:can|does) (?:you|this (?:app|bot|terminal|assistant|mystock)|stockrag) (?:do|support|offer|provide))\b",
        r"\b(?:what (?:are (?:your|the)|is your) (?:capabilities|features|functions|tools|endpoints))\b",
        r"\b(?:how (?:do|can) i (?:use|upload|manage|pin|branch|filter|change|configure|set|forecast))\b",
        r"\b(?:can (?:you|this (?:app|bot|terminal|assistant|system)|i) (?:automate|execute|place|buy|sell|trade|invest|withdraw|deposit))\b",
        r"\b(?:trade execution|automated trading|place orders?|execute trades?)\b",
        r"\b(?:what (?:[a-z]+ )?(?:indicators|models|exchanges|files?|formats?) (?:do you|are) (?:support|available|supported))\b",
        r"\b(?:how does (?:forecasting|rag|the crawler|search|the model) work)\b",
        r"\b(?:explain (?:the )?(?:app|terminal|mystock|features|capabilities))\b",
        r"\b(?:help|terminal help|user guide|commands)\b",
    )
    return any(re.search(p, lowered) for p in patterns)


def get_capability_context(query: str) -> str:
    """Generate high-signal capability evidence text explaining supported and unsupported features."""
    lowered = query.casefold()

    lines = [
        "TERMINAL CAPABILITIES & FUNCTIONALITY (Verified Application Specifications):",
        "MyStock AI is a local institutional-grade stock research terminal and quantitative market intelligence platform.",
    ]

    # Specific topic detection
    if any(k in lowered for k in ("trade", "buy", "sell", "order", "broker", "brokerage", "execute")):
        lines.append(
            "- CRITICAL RULE ON TRADING: MyStock AI is an informational analysis and research terminal. "
            "It DOES NOT execute real trades, route brokerage orders, or custody user funds. Users make their own investment decisions."
        )

    if any(k in lowered for k in ("indicator", "technical", "rsi", "macd", "sma", "moving average")):
        tech = APPLICATION_CAPABILITIES["technical_analysis"]
        lines.append(f"- Technical Indicators: {', '.join(tech['indicators'])}.")

    if any(k in lowered for k in ("forecast", "predict", "horizon", "model", "conformal")):
        fc = APPLICATION_CAPABILITIES["forecasting"]
        lines.append(
            f"- Probabilistic Forecasting: Supports {', '.join(fc['horizons'])} horizons. "
            f"Available models: {', '.join(fc['models'])}. Outputs: {', '.join(fc['metrics'])}. "
            f"Note: {fc['important_disclaimer']}"
        )

    if any(k in lowered for k in ("upload", "document", "pdf", "file", "rag", "dataset", "excel", "csv")):
        doc = APPLICATION_CAPABILITIES["document_rag"]
        lines.append(
            f"- Document & Dataset Management: Supports {', '.join(doc['supported_file_types'])} for hybrid RAG search "
            f"(FAISS + SQLite BM25 FTS5). Also supports tabular profiling for {', '.join(doc['tabular_datasets'])}."
        )

    if any(k in lowered for k in ("web", "crawl", "search", "news", "internet")):
        web = APPLICATION_CAPABILITIES["web_research"]
        news = APPLICATION_CAPABILITIES["news_intelligence"]
        lines.append(f"- Web & News: {web['description']}. {news['description']}.")

    if any(k in lowered for k in ("branch", "pin", "memory", "session", "history", "save")):
        mem = APPLICATION_CAPABILITIES["conversation_and_memory"]
        lines.append(f"- Conversation & Memory: {mem['description']}.")

    # General capabilities summary
    lines.append("- Core Implemented Modules:")
    for key, cap in APPLICATION_CAPABILITIES.items():
        lines.append(f"  • {cap['title']}: {cap['description']}")

    lines.append("- Explicitly Unsupported Actions:")
    for unsup in UNSUPPORTED_CAPABILITIES:
        lines.append(f"  • {unsup}")

    return "\n".join(lines)

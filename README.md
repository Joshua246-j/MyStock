# StockAI Terminal

A local-first stock-market research terminal combining market data, technical/fundamental analysis, document RAG, and local LLM chat.

## Features Implemented
1. **Market Data Provider**: Fetches real-time quotes, historical data, financials, and news via `yfinance`. Automatically falls back to `Stooq` if `yfinance` is rate-limited or unavailable.
2. **Technical Analysis**: Built-in calculation for SMA, EMA, RSI, MACD. Fully wired into the UI and AI context.
3. **Document RAG & Web Research**: PDF ingestion (PyMuPDF), web crawling (BeautifulSoup), vector storage (Chroma), and embedding generation (Ollama).
4. **Resilient AI Integration**: Local LLM connection using Ollama. System handles connection failures gracefully, falling back safely without crashing. Async Orchestrator runs tools concurrently.
5. **Premium Terminal UI**: Grid-based interface featuring system health checks, dynamic data loading, Interactive Lightweight Charts, and an Apple-inspired glass-morphic design.
6. **API Caching & Persistence**: SQLite-backed caching with TTL to optimize external data retrieval. Conversation history stored in SQLite.

## How to Run
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start local Ollama instance (ensure `gemma3:4b` or your chosen model is pulled).
3. Run the FastAPI server:
   ```bash
   uvicorn app.main:app --reload
   ```
4. Access the Terminal UI at: `http://localhost:8000`

## Architecture Overview
- `app/api/routes/`: FastAPI endpoints (`market.py`, `chat.py`, `documents.py`)
- `app/market/`: Market data service and provider abstractions
- `app/analysis/`: Technical analysis tools and async Orchestrator
- `app/rag/`: Retrieval-Augmented Generation pipeline
- `app/db/`: SQLAlchemy models and SQLite connection
- `static/`: Frontend interface

## Testing
All tests pass. Run them using:
```bash
pytest tests/
```

## Setup Packages & Environment
Make sure all required packages are present in `requirements.txt`.
You must have Python 3.9+ and pip installed.

# MyStock

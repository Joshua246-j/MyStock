# PROJECT AUDIT

## 1. Existing Architecture
- **Backend**: FastAPI
- **Database**: SQLite (SQLAlchemy models exist but are mostly unused in the actual business logic).
- **Caching**: Simple in-memory dictionary cache in `app/db/cache.py` (not using SQLite for cache persistence).
- **Market Data**: `yfinance` wrapper in `app/market/providers/yfinance_provider.py`.
- **RAG/Documents**: PyMuPDF for extraction. ChromaDB for vector storage. Ollama for embeddings and generation.
- **Frontend**: Single `index.html` with vanilla JS and Tailwind (via local CSS).

## 2. Actual Execution Flow
Browser -> `/static/index.html` -> Fetch APIs (`/api/stocks/{symbol}`, `/api/chat`).
Chat logic runs `classify_query` -> analyzes dataset OR retrieves from Chroma -> sends prompt to Ollama -> returns answer.

## 3. Existing Working Functionality
- Application starts and API endpoints exist for market data, document upload, and chat.
- yfinance wrapper is able to retrieve quotes, history, and fundamentals (when yfinance isn't rate-limited).
- PDF text extraction and chunking function works.
- Pytest unit tests for RAG mock and PDF mock pass.

## 4. Broken Functionality
- **Database**: Models are defined but never queried or populated (e.g. ChatSession, ChatMessage are empty).
- **UI**: The UI has an "Apple-like" layout but lacks actual system status wiring, settings, and polished data presentation.
- **RAG Grounding**: The prompt in `chat.py` does not strictly enforce citations or uncertainty.
- **yfinance fallback**: No fallback provider is implemented if yfinance fails.

## 5. Missing Functionality
- **Settings API & UI**: No way to change models, contexts, or user preferences.
- **Robust Orchestrator**: `chat.py` only does simple keyword matching for intent instead of a robust orchestrator.
- **Persistent Caching**: Caching is in-memory, lost on restart.
- **Technical Analysis**: `technical.py` is written but not exposed in the API or UI.
- **Web Crawler**: Basic crawler exists but isn't integrated into the chat orchestrator correctly.
- **End-to-End Tests**: Missing comprehensive integration tests.

## 6. Current Dependency Problems
- Using `yfinance` directly without retry logic or rotating headers.
- `requirements.txt` has missing test deps or conflicting versions if updated.

## 7. Recommended Architecture
- Move Cache and Settings into SQLite.
- Enhance Chat Orchestrator to detect exact intent, retrieve market data/tech analysis + RAG context simultaneously.
- Upgrade UI to a modular or highly structured Tailwind layout with Settings modal.
- Implement proper dependency injection for Market Data to allow fallbacks.

## 8. Implementation Plan
- **PHASE 1**: Audit (Complete)
- **PHASE 2**: Startup + config + dependency repair (Fix imports, ensure DB path works)
- **PHASE 3**: Market-data provider repair (Add retries/headers to yfinance)
- **PHASE 4**: SQLite database + cache (Wire up SQLAlchemy to actually store cache, messages, settings)
- **PHASE 5**: Technical/fundamental analysis (Wire up `technical.py` to API)
- **PHASE 6-7**: Document Ingestion & RAG (Enhance metadata filtering, citations)
- **PHASE 8-10**: Web Research, News, Ollama (Integrate into Orchestrator)
- **PHASE 11**: Intelligent chat orchestration (Rewrite `/chat` endpoint)
- **PHASE 12-14**: Settings, Citations, UI Redesign (Full frontend overhaul)
- **PHASE 15-19**: Testing, E2E, Polish, Docs.

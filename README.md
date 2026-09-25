# StockRAG

StockRAG is a local-first market research workspace built with FastAPI, SQLite, ChromaDB, Ollama, and a responsive browser interface. It combines market data with uploaded research and gives the assistant source material to work from.

## What is implemented

- Market quote, company profile, historical price, technical indicator, fundamental, and news endpoints. Market requests try yfinance and fall back to Stooq where that provider supports the requested data. Cached results are stored in SQLite with a configurable TTL.
- Four selectable comparison charts default to Indian large-cap equities (Reliance, TCS, HDFC Bank, and Infosys), with popular US and NSE/BSE index symbols also available; series are provider-backed historical prices rebased to a common starting value. Analysis includes SMA/EMA, RSI, MACD, Bollinger bands, ATR, annualized volatility, drawdown, and recent returns.
- A 20-session statistical scenario interval is displayed with its method, persistence-baseline error, and assumptions. It is an exploratory estimate, not a validated forecast or investment recommendation.
- Settings lists the models actually installed in the local Ollama service. It does not advertise cloud models or install model weights.
- SQLite-backed chat sessions and turns, settings, document status, and cache entries. The active chat can be restored in the same browser after a reload.
- PDF text indexing and scoped retrieval for selected PDFs. Semantic search uses ChromaDB/Ollama embeddings; a persistent SQLite FTS5 keyword index remains usable when embeddings or Chroma are unavailable. Health reports semantic versus keyword-only readiness. CSV and Excel uploads can be analyzed in chat as an uploaded dataset. Indexed-document state is shown in the Data Hub.
- Multi-source chat orchestration for quote, technical, fundamental, news, document, web, and dataset evidence. Independent work is gathered concurrently and blocking calls are moved off FastAPI's event loop. The response reports the selected model, evidence, limitations, data timestamp, and whether source formatting could be verified.
- Local Ollama generation and embeddings. Web crawling is limited to an explicit financial-domain allowlist and respects the web-research setting.
- A light-first responsive interface with saved light/dark theme, density, configurable settings, status checks, chart periods and line/candlestick views. Frontend libraries are version-pinned and served locally.
- Chat supports PDF and CSV/XLS/XLSX attachments directly from the composer. Attached documents are scoped to retrieval for that conversation; datasets are profiled from their real rows and columns. Remove a scope chip to stop including it.
- The chat composer provides a quick switch among generation models Ollama reports as installed. Switching updates the live app setting for the next reply; if Ollama or a model is unavailable, the UI reports it and does not save a fabricated assistant answer.

## Requirements

- Python 3.10 or newer
- Node.js 18 or newer and npm
- Ollama installed locally, with a generation model and the configured embedding model pulled
- Network access for yfinance/Stooq and allowlisted web research

## Setup (Windows PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
npm ci
npm run build:css
Copy-Item .env.example .env
```

Review `.env` and set `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `EMBEDDING_MODEL`, `CHROMA_PATH`, `DB_PATH`, and `UPLOAD_DIR` for the machine. Defaults are local to this project. Keep `.env` private; it is ignored by Git.

Start the Ollama service and install the default, lightweight chat model plus the embedding model used for PDF retrieval:

```powershell
ollama serve
ollama pull qwen2.5:1.5b
ollama pull nomic-embed-text
```

Settings lists all other generation models already installed in Ollama, so you can switch the chat model at any time. For another smaller local option, install `gemma3:1b` with `ollama pull gemma3:1b`. All models use the same StockRAG retrieval, calculated evidence, uncertainty policy, and answer-format rules; the model only writes the final response. Local models require memory and disk space, and model performance varies.

Run the app from the project directory:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The first startup creates the SQLite schema and removes expired cache entries. `/api/health` checks the selected Ollama model, ChromaDB, SQLite keyword retrieval, and market provider; external services can be unavailable while the app itself remains up. Keyword document search can continue without the embedding model, but semantic similarity requires the configured Ollama embedding model. Chat generation still requires an installed Ollama generation model.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server address |
| `OLLAMA_MODEL` | `qwen2.5:1.5b` | Initial generation model |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Ollama embedding model used for indexing and retrieval |
| `CHROMA_PATH` | `./data/chroma` | Persistent vector store directory |
| `DB_PATH` | `sqlite:///./data/stock_terminal.db` | SQLAlchemy database URL |
| `UPLOAD_DIR` | `./uploads` | Uploaded source files |
| `LOG_LEVEL` | `INFO` | Application log level |

Other options, including model, temperature, context length, maximum answer tokens, request timeout (120 seconds by default to accommodate local CPU models), cache TTL, chart defaults, retrieval count, automation toggles, theme, and density, can be changed in the Settings sheet and take effect without restarting the server.

## API

- `GET /api/health`
- `GET /api/settings`, `PUT /api/settings`
- `POST /api/chat`, `GET /api/chat/sessions/{session_id}`
- `GET /api/stocks/{symbol}`, `/quote`, `/history`, `/fundamentals`, `/technical`, `/news`
- `GET /api/symbols/resolve/{symbol}`
- `GET /api/models` (installed local Ollama models only)
- `GET /api/documents`, `POST /api/upload/pdf`, `POST /api/upload/dataset`, `POST /api/crawl`

The interactive API schema is available at `/docs`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q --basetemp .pytest-tmp -p no:cacheprovider
npm run build:css
```

The workspace's default Windows Temp and pytest cache locations may be access-restricted, so the test command uses a workspace-local temporary directory and disables pytest's cache plugin.

## Current limits

- Chat responses are returned after generation; Ollama token streaming is not implemented. Small local models may take tens of seconds or time out on CPU-only machines; configure the answer-token limit and request timeout for the host, or choose a faster installed model. Timeouts are shown as service errors and are not stored as assistant replies.
- The UI restores the current conversation but does not yet provide a multi-session history browser.
- Symbol resolution validates ticker syntax and applies a small set of exchange heuristics; it is not a complete exchange security master or company-name search.
- Stooq fallback coverage is limited to quote/history. It does not provide fundamentals, profile data, or news. Web research only crawls allowlisted domains and only follows direct URLs supplied to the chat or Data Hub.
- Document retrieval combines Chroma semantic results and SQLite FTS5 lexical results, applies selected-document filters, and falls back to keyword retrieval if Chroma or Ollama embeddings are unavailable. Uploaded tables are analyzed from the current browser's active dataset selection rather than embedded as vector documents.
- Quotes are never labeled real-time unless a provider and entitlement can substantiate it. The current free yfinance route has unverified freshness; Stooq fallback is marked delayed/end-of-day. Neither provides a reliable, licensed real-time consolidated feed for all exchanges. Historical chart coverage and data availability vary by symbol/provider. Yfinance is an unofficial interface and can be rate-limited; provider access was unavailable during this run, so no live quote or chart could be verified.
- Indian ticker shortcuts resolve a maintained starter set of widely traded NSE names; `^NSEI` and `^BSESN` are also offered. This is not a complete NSE/BSE security master or autocomplete by company name. Free quote/chart access and update frequency vary by provider. NSE distributes real-time data through subscription products and sets rules for its market data; the app does not claim free exchange-authorized real-time Indian quotes. See [NSE real-time data subscriptions](https://www.nseindia.com/static/market-data/real-time-data-subscription) and [NSE data policy](https://www.nseindia.com/static/market-data/nse-data-policy).
- The current provider set does not cover every exchange, and the Stooq adapter is intentionally limited to US symbols. Reliable exchange-approved real-time or 15-minute delayed US data requires a paid entitlement. Alpha Vantage's official docs state its default global quote is end-of-day and real-time/delayed US quotes require premium; its free plan is limited to 25 API calls/day. See [Alpha Vantage quote documentation](https://www.alphavantage.co/documentation/) and [official usage/data policy](https://www.alphavantage.co/support/).
- This is a research terminal, not a trading or investment execution system. Market predictions are not guarantees and should not be used as sole investment advice.

## Project layout

- `app/api/routes/` — FastAPI routes
- `app/analysis/` — technical indicators and multi-source chat orchestration
- `app/market/` — provider interface, yfinance/Stooq adapters, cache-aware service
- `app/rag/` — ChromaDB semantic storage, SQLite FTS5 fallback, indexing, retrieval
- `app/db/` — SQLAlchemy models and SQLite lifecycle
- `static/` — browser interface, locally served vendor files, and built CSS
- `tests/` — unit tests for dataset/PDF/RAG and production reliability paths

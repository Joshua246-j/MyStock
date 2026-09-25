# StockRAG: verified architecture and current limits

This document replaces the earlier stale audit. Findings were checked against the current source on 2026-09-25. Implementation and verification notes are maintained in [PROGRESS.md](PROGRESS.md).

## Stack and request flow

- FastAPI serves API routes and static assets from `static/`.
- SQLAlchemy persists user settings, chat sessions/messages, document status, and a TTL cache in SQLite by default.
- `MarketDataService` tries yfinance and uses Stooq for supported quote/history fallbacks. Technical indicators are calculated from historical data.
- PDF pages are chunked into a persistent SQLite FTS5 lexical index and, when Ollama embeddings/Chroma are usable, also into persistent ChromaDB. Retrieval merges semantic and keyword hits and filters by indexed document ID. The keyword path is verified independently; semantic retrieval remains dependent on the local embedding model.
- Chat classification uses explicit multi-label phrase matching plus a supplied or safely extracted ticker. Independent quote, indicator, fundamentals, news, retrieval, web crawl, and dataset work is gathered concurrently.
- The browser uses locally served, version-pinned Tailwind, lightweight-charts, marked, DOMPurify, and Lucide assets.

## Source-verified capabilities

- Conversation turns and cache entries are written to SQLite. Cache TTL comes from settings; startup and periodic cleanup remove expired rows.
- The selected model, temperature, context length, response detail, retrieval count, mode, request wait limits, and source visibility are read per request. Display preferences apply without restart.
- `/api/health` pings Ollama and the selected model, checks ChromaDB, and performs an uncached provider quote check; it reports failures as unavailable.
- Uploads have a size cap, generated storage names, PDF/dataset type checks, and persistent processing/completed/failed records. Dataset analysis is constrained to files under the upload directory.
- API validation and HTTP errors use a structured `error` envelope. Request IDs and latency are logged.
- Search and chart surfaces expose symbol resolution, time range, configured interval, line/candlestick rendering, and local retry states.
- Quote responses do not claim real-time freshness. yfinance is marked freshness-unverified; Stooq is marked delayed/end-of-day. Four historical comparison charts can be selected independently. Market-provider failures have an explicit unavailable state and retry action.
- Technical analysis calculates RSI, SMA/EMA, MACD, Bollinger bands, ATR, annualized volatility, drawdown, and returns. The displayed 20-session statistical interval is labeled experimental with a persistence baseline error and explicit limitations.
- Settings model selection is populated from `/api/models`, which reports only locally installed Ollama models; missing models are visibly marked.

## Known gaps that still matter for production readiness

- Ollama chat is non-streaming. There is no token-by-token UI update while generation is running.
- The UI restores its last active conversation but does not yet list or switch among saved sessions.
- Symbol handling validates ticker syntax and a few exchange heuristics; it is not a company-name resolver or complete exchange directory.
- Intent routing is deterministic phrase matching, not a language-model or trained intent classifier.
- Stooq only supplies quote and history. Fundamental, company, and news requests can still be unavailable when yfinance cannot serve them.
- This stack does not provide a verified, exchange-licensed, reliable real-time consolidated feed. Official Alpha Vantage documentation states its default global quote is end-of-day and real-time/15-minute delayed US quotes require a paid entitlement; the free allowance is 25 requests/day. See [API quote documentation](https://www.alphavantage.co/documentation/) and [official support/data policy](https://www.alphavantage.co/support/). The current provider network is unavailable in this environment, so current quotes/charts have not been verified against real payloads.
- The statistical scenario is not a validated forecast, has no walk-forward calibration, and assumes historical return behavior persists. It must not be presented as a reliable prediction.
- The outer async request deadlines keep the FastAPI loop responsive, but Python worker threads cannot be forcibly stopped after a deadline. A provider request already running in a thread can finish in the background.
- The browser’s viewport checks cover layout and horizontal overflow. Real market/chart behavior and generated answers could not be exercised in this run because market providers and Ollama were unavailable.
- Research answer headings are prompt-guided and now checked after generation; one constrained reformat attempt runs when required headings are missing. If the repair still fails, the response is marked and carries an explicit format warning. This structure check does not prove financial claims are correct; grounding still depends on the evidence supplied.
- There is no standalone user-defined custom-field/metric builder. Uploaded dataset questions receive bounded computed profiles of available columns, summary statistics, grouped averages, correlations, and sample rows. If users mean reusable custom formulas or saved fields, that capability is not implemented.
- End-to-end concurrent load testing, provider behavior under real rate limits, live PDF indexing against a running Ollama/Chroma stack, and actual device testing remain open.

## Verification record

Latest follow-up verification is recorded in [PROGRESS.md](PROGRESS.md). As of this audit, actual Ollama-generated answers, semantic embedding retrieval, and provider-backed Indian live/chart payloads remain unverified because the generation/embedding models are absent and the market providers are unreachable in this environment.

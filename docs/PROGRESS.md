# StockRAG Audit, Plan, and Delivery Log

Date: 2026-09-24

## Phase 0 — Verified audit (before implementation)

The initial project audit was stale in several places. These findings come from the current source tree, not the old audit's claims.

### Confirmed present
- FastAPI routes, SQLAlchemy models, a SQLite cache table, conversation writes, `UserSettings`, market providers, technical indicator calculation, PDF ingestion, Chroma retrieval, and a single-page browser UI are present.
- Market data uses yfinance first and Stooq fallback; yfinance operations include tenacity retries and randomized user-agent values.
- Technical analysis is exposed via `/api/stocks/{symbol}/technical` and is also called by the chat orchestrator.
- The chat route reads the configured `ai_model`, persists user/assistant content, and returns a timestamp when market quote data is fetched.
- Settings API and UI controls are present in some form; presence does not mean complete validation, safe defaults, or runtime effect.

### Verified gaps and defects
- `docs/PROJECT_AUDIT.md` and the README claim features are absent or complete without current evidence. The README claims all tests pass, which is false in this environment (see verification below).
- Chat intent detection is keyword based and only partly covers the requested intent set. Market quote, news, fundamentals, technicals, and RAG retrieval are not consistently combined. RAG retrieval is unconditional; document scoping and web-research settings are incomplete.
- Orchestration runs news and crawling before its gather; news/market retrieval is therefore sequential. Ollama generation is blocking work moved to a worker thread but does not use request settings for timeout/temperature/context. `structured_analysis` is always `{}`.
- Citation handling appends a source list rather than checking source claims; there is no `sources_unverified` flag. `retrieval.web_sources` is hardcoded to zero.
- All market API route functions are synchronous and execute yfinance/SQLite/provider work in FastAPI's threadpool by default, but request timeout is not propagated. Upload and crawl routes are async while performing blocking file, PDF/CSV, Chroma, and crawler work on the event loop.
- `/api/health` performs synchronous HTTP checks inside a synchronous route, reports configured model rather than selected settings model, and hardcodes Chroma and market availability.
- Several API failures use HTTPException's `detail` envelope rather than the required consistent `{"error":{"code":...,"message":...}}`; several service layers silently catch failures or use `print`.
- SQLite setup assumes a SQLite URL and a relative `./data` path. Startup schema creation and expired-cache cleanup run at import time, outside FastAPI lifespan.
- Stooq's coverage differs from yfinance (e.g. fundamentals/news); fallback behavior needs per-capability review. Cache TTL is read from settings, but the cleanup currently runs only once at import.
- The web crawler has an allowlist but no settings-based timeout, does not validate redirect destinations, and silently loses crawl outcomes in chat. Crawled material is not guaranteed to be available to retrieval in the same turn.
- The frontend is a single large HTML/JS document with external CDN dependencies, partially fake status indicators initialized green, incomplete API wiring/settings coverage, no chat-session history/streaming, and no upload state/scoping. CSS respects OS dark preference instead of the saved theme; mobile layout does not meet the stated navigation/safe-area requirements. No source autocomplete API exists.
- `requirements.txt` omits imported packages (`langchain_text_splitters`, `langchain_chroma`, `langchain_ollama`, `python-multipart`, and `openpyxl` for XLSX support). `package.json` contains a placeholder test command. `.env` exists locally; never include its contents in logs/docs.
- No `.git` metadata is available in this workspace, so change review must use direct file inspection.

### Verification baseline
- `pytest` is not on PATH; `.venv/Scripts/python.exe -m pytest tests/ -q` ran and reported **1 passed, 2 setup errors**. Both errors were Windows `PermissionError` creating pytest temp directories under the user Temp path; pytest cache writes were also denied. This does not establish test correctness. Re-run with a workspace-local basetemp and cache provider disabled.
- Application startup, first-request behavior, dependency connectivity, and viewport behavior have not yet been verified. These are open tasks, not claims of success.

## Detailed implementation plan and tasks

### Phase 1 — Foundation and environment
- Align requirements with all runtime imports; add pinned/compatible dependency bounds where practical and remove unusable placeholder package scripts.
- Make DB path creation SQLite-safe; move schema creation and cache cleanup into FastAPI lifespan; add request IDs, latency logging, and structured exception responses.
- Verify startup and first API request using local configuration; report external Ollama/market dependencies distinctly.

### Phase 2 — Market reliability
- Apply configurable timeout to provider operations and keep blocking operations off the event loop.
- Normalize provider output/errors and fallback by capability; label primary/fallback/cache source and expose active-provider health.
- Preserve cache TTL setting, make cache writes safe under concurrent requests, and clean expired rows periodically/on startup.

### Phase 3 — Persistence and settings
- Validate settings against a typed schema, preserve defaults, expose all settings in UI, and make model/temperature/context/timeout effective per request.
- Ensure session IDs are validated, sessions exist before writes, history ordering is stable, and failed generations do not leave misleading completed turns.
- Add cache/session/settings persistence tests.

### Phase 4 — Market analysis and data surfaces
- Validate technical indicators and fundamentals against actual provider payloads; add chart interval/period validation and search/autocomplete with explicit invalid-symbol feedback.
- Add consistent error envelopes and retryable client states for quote, chart, fundamentals, technicals, and news.

### Phase 5 — Orchestrator
- Introduce typed intents for quote, technical, fundamental, news, document QA, web research, and general chat; allow combined intents and infer symbols safely.
- Fan out independent provider/RAG tasks concurrently with bounded timeouts and graceful per-source failures.
- Pass relevant evidence to Ollama with selected model, temperature, context and timeout; return actual retrieval counts, model, timestamps, data status, and structured analysis.
- Enforce evidence/citation contract without fabricating citations; mark unverifiable source claims explicitly.

### Phase 6 — RAG and web research
- Add document metadata/status persistence and document-scoped retrieval; harden crawl allowlist/redirect handling and settings gates.
- Return crawl/indexing errors, make just-crawled evidence retrievable when indexing succeeds, and keep vector/PDF work off the event loop.
- Add live Chroma/Ollama checks and graceful unavailable states.

### Phase 7 — Frontend rebuild
- Restructure frontend into maintainable components/modules while retaining the requested vanilla stack unless an existing build system proves suitable.
- Implement modern light-first glass design, saved light/dark theme and density, responsive rail/mobile tabs, safe-area and minimum touch sizes.
- Wire chart library and configured periods, quote/fundamentals/technicals/news, real status checks, settings sheet/modal, document uploads/status/scope, and persistent sessions.
- Add loading skeletons, retry actions, empty/error states, escaped markdown/citation rendering, and accessible keyboard/touch behavior.

### Phase 8 — Verification
- Expand backend tests for orchestrator combinations/failures, fallback/timeout, persistence/settings, and error envelopes; add API smoke coverage.
- Run the full test suite and boot the app, then exercise first requests with dependencies available/unavailable where feasible.
- Check responsive behavior at 375px, tablet, desktop using browser automation if available; record any external/manual verification limits.

### Phase 9 — Documentation and release readiness
- Replace stale audit/README claims with verified setup, configuration, dependencies, feature limits, and operational steps.
- Recheck all Section 7 definition-of-done items and explicitly list remaining gaps.

## Delivery log

Implementation has not started. Each phase will be updated here only after its changes and verification have been observed.

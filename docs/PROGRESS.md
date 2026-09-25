# StockRAG Audit, Plan, and Delivery Log

Date: 2026-09-25 (Asia/Kolkata)

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

## Follow-up market-data audit (2026-09-25)

The requested deeper market audit verified quote labels against provider behavior, not just route presence.

- **Freshness claim was false:** the frontend treated any successful quote as `LIVE`. The primary yfinance adapter stamped retrieval time as though it were the market quote time, without a substantiated exchange timestamp or entitlement. Stooq stamped retrieval time even for daily bars. The interface now avoids a LIVE label, distinguishes cached/unverified/delayed-or-end-of-day states, and keeps retrieval time separate from the last bar date.
- **Provider limitations are material:** yfinance access in this environment fails with cookie/crumb network errors and no price data; Stooq also returns no history here. The server stays up and routes return structured unavailable responses, but live quotes and live charts could not be observed. Stooq fallback supports US symbols only; other exchanges now fail explicitly instead of being rewritten as `.us`.
- **No free source in this project establishes dependable live US market data:** Alpha Vantage's official documentation says the default global quote updates at end of trading day and real-time or 15-minute delayed US quotes require a premium membership. Its official support page states a free allowance of 25 API requests/day. References: [Global Quote entitlement](https://www.alphavantage.co/documentation/) and [official usage/data policy](https://www.alphavantage.co/support/). yfinance/Stooq are not represented as licensed real-time exchange feeds.
- **Analysis is broader and bounded:** indicators include SMA/EMA, RSI, MACD, Bollinger bands, ATR, annualized volatility, maximum drawdown, and returns. A 20-session log-return scenario includes an 80% model interval and a last-close persistence holdout MAE; the API/UI states assumptions and that it is not a validated forecast. It remains an exploratory estimate, not a guaranteed investment prediction.
- **Charts and models:** the dashboard offers four separately selectable, provider-backed normalized historical-price comparison panels for popular US/Indian tickers. `/api/models` and Settings list only models installed in local Ollama, with missing/unavailable models marked. It does not download weights or claim cloud/free model access.
- **Failure surfacing:** quote/history/fundamental/technical routes keep provider work off the event loop with the configured deadline. Quote, chart, comparison, technical, fundamentals, news, and service-status regions show retryable failure states or explicit unavailable status. Provider failure is not converted into a fabricated price or chart.

## Current delivery state

Implemented the foundation, SQLite persistence/cache, market fallback and status labeling, technical-analysis expansion, bounded market routes, local model discovery, light-first frontend, comparison panels, structured errors, and docs refresh.

Remaining production blockers are external or known capability gaps: a licensed market-data account/API key for dependable real-time entitlements; provider connectivity and actual data verification; installed/running Ollama generation and embedding models; true token streaming; multi-session browsing; a complete exchange-symbol security master; validated out-of-sample forecasting; end-to-end concurrency/load testing; and real-device testing. These are not marked done.

Final verification: `pytest` reports **8 passed**; Python compilation, JavaScript syntax, Tailwind CSS build, `pip check`, and `npm audit --omit=dev` all succeeded (zero npm vulnerabilities). Uvicorn started cleanly after the final backend edits. Root, settings, model discovery, and live health endpoints responded. Health reported Chroma available, Ollama disconnected, and both market providers unavailable; live quote/history were therefore exercised as visible structured failures, not successful data paths. Browser checks verified mobile bottom navigation/settings sheet, full-screen tablet chat, and no horizontal overflow at 375, 768, and 1440 CSS pixels after layout settled. There were no fresh browser console errors; live chart rendering and an AI-generated response remain unverified because their dependencies were down.

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

The phased implementation plan remains the checklist. The follow-up market audit and implementation state are recorded above; final verification remains pending.

## Follow-up chat, local model, and India-market audit (2026-09-25)

### Reverified findings
- The visible Ollama error was not merely a UI problem. The orchestrator converted `check_health` false and generation exceptions into `AI response unavailable: ...` text with HTTP 200, then chat persistence saved that text as an assistant answer. The browser could only render it as a normal answer and labeled the evidence state `NOT_REQUESTED DATA`.
- The configured local model was `gemma3:4b`, but Ollama was installed and not running, and its model registry was empty. `/api/models` correctly returned no installed models. A real `/api/chat` request reproduced `503` once error propagation was corrected; its structured response identified `ollama_model_missing` and gave installation/selection guidance. The browser displayed a service-failure badge and a retry control rather than presenting the text as generated analysis.
- The app's Indian coverage was a short list of ten `.NS` aliases with US tickers preselected. NSE/BSE index symbols and several widely traded NSE names were not available as shortcuts. The comparison cards now start with Reliance, TCS, HDFC Bank, and Infosys, and include more popular NSE/BSE index/equity symbols. This remains a maintained starter list, not an exchange security master.
- The CSV/Excel helper provided only row/column counts and numeric min/max/mean. It omitted representative records, missingness, category distributions, quartiles, and median, limiting question answering. It now profiles a bounded 100,000 rows/25 MB, reports missingness and numeric percentiles, includes categorical examples and up to 12 sample rows, and makes failed dataset reads visible as limitations.

### Changes made in this pass
- Ollama connection, missing-model, timeout, HTTP, invalid-response, and empty-response failures now remain typed service failures. Chat removes its uncompleted user turn and returns the structured error envelope; it never saves a manufactured assistant response on a generation failure.
- The assistant system prompt now explains StockRAG's real product capabilities, differentiates the language model from deterministic retrieval/calculation behavior, supports ordinary general questions, and explicitly forbids invented app features, current market values, PDF pages, and dataset facts.
- A lightweight local Qwen model is now the clean-install default in app configuration, `.env.example`, the local `.env`, and Settings. Ollama was started successfully on localhost. Pulling `qwen2.5:1.5b` and `nomic-embed-text` was started for actual inference/RAG verification; the model registry was still empty at last check, so the download and generation check remain pending. A second small local generator is still needed to verify true model switching.
- Legacy persisted Ollama-error assistant bubbles are recognized on session restore and rendered as clearly marked service failures. A restore-generation guard prevents a late history request from replacing a newly started conversation.
- Added regression coverage for Indian symbols/indexes, CSV profile statistics, the no-fabricated-answer failure path, and previously added orchestration/fallback/settings/technical cases.

### Additional tasks still open
- Finish local Ollama generation and embedding pulls; make the configured/default model match an installed model, verify `/api/health`, and run actual product-awareness and general-market prompts through the UI and API.
- Install/verify a second compatible small local model; switch between both models in Settings and confirm the same StockRAG evidence and response contract are applied.
- Upload the repository's small PDF and CSV fixtures in a controlled integration check, verify PDF chunks are retrieved with correct page/file metadata, and verify tabular facts are computed correctly. Remove only the test records and vector chunks created by that check afterward.
- Re-run the full test suite, JS syntax/build checks, fresh server startup, structured chat outage scenario, and responsive browser checks after the final UI/runtime edits.
- Real Indian/US quote and chart success paths remain dependent on reachable third-party providers; this environment previously failed yfinance/Stooq network access. The product must keep displaying source, last-bar/retrieval time, and failure status. NSE exchange-authorized live data requires an appropriate data entitlement, so the product must not promise a free real-time feed.

### Verification during the follow-up
- Actual app chat request with an uninstalled model: observed HTTP 503 and JSON `{error:{code:"ollama_model_missing", message:...}}`; no assistant answer was persisted.
- Actual browser chat query with Ollama service running but no downloaded model: displayed the user question, a clear “Service failure · no AI answer generated” badge, and “Retry question”.
- First expanded test run found the original dataset test expected the previous `Min/Max/Mean` string form; the richer profile retains that compatible summary. Latest run then reported **11 passed**.
- Fresh app boot after backend error/prompt changes succeeded. Ollama `/api/tags` responded but listed no model while downloads were still in progress. Provider-backed successful chart rendering, PDF embeddings, and actual model-generated answers remain unverified pending dependencies.
- The follow-up run reports **12 passed**, `pip check` clean, Python compilation clean, and JavaScript syntax clean. Tailwind CSS rebuilt successfully. A fresh `npm audit --omit=dev` could not reach the npm audit endpoint; the earlier audit in this workspace returned zero production vulnerabilities.
- Ollama was running and reachable, but the `qwen2.5:1.5b` download repeatedly failed after about 100 MB because the registry blob connection was forcibly closed. `/api/tags` remained empty. The model and embedding installation therefore cannot be claimed complete; no real generated answer or PDF embedding has been observed in this run.
- Health now checks the configured generation model and the configured embedding model as distinct dependencies, so a connected Ollama server with no embedding model reports document retrieval unavailable rather than implying PDF RAG is ready.
- The fresh health check exposed a Chroma client race: each retrieval and health check constructed a new persistent Rust client for the same directory, and concurrent requests triggered Chroma tenant-validation failures. The vector-store factory now lazily creates one locked, process-wide client; a regression test verifies the singleton behavior. This surfaced only after exercising concurrent chat/status paths, so health must be rechecked after restart.
- A clean app restart reports Ollama reachable but no installed generation or embedding models; market providers remain unreachable. The model pull repeatedly reached roughly 100 MB then the registry blob connection was forcibly closed. This prevents actual model/PDF integration validation in the current environment.

## RAG and answer-contract follow-up (2026-09-25)

### Audit findings and implementation
- The previous document path required Ollama embeddings and Chroma writes to succeed for PDF indexing to be considered successful. The retriever returned no useful document context if Chroma failed, even when extracted text was available locally.
- Added a persistent SQLite FTS5 lexical index with document/page/source metadata and document-ID filtering. PDF/web ingestion writes lexical chunks and attempts semantic Chroma indexing independently. Retrieval merges/deduplicates semantic and keyword results; when Chroma/embeddings fail, keyword results remain available and carry an explicit `keyword` retrieval mode. Health now reports `semantic`, `keyword`, or `unavailable`; the UI calls out keyword-only fallback instead of declaring all document retrieval broken.
- Added a one-time constrained model repair attempt for research replies missing required section headings. Required headings are checked after the repair and citation handling; any remaining structure failure is visible in the answer and returned as `format_unverified`. Ordinary product/general answers may remain conversational. No custom saved formula/metric builder exists; dataset Q&A uses computed statistics for the uploaded dataset's actual columns.
- Corrected the chat route's absent-settings model default to follow `OLLAMA_MODEL`, and reconciled README setup/configuration and the architecture audit with current fallback behavior.

### Verification observed
- Generated a PDF containing a unique financial fact, ran the real PDF extractor/indexer with semantic storage forced to fail, then retrieved the fact by question with correct PDF page citation from SQLite FTS5. This test passed.
- Full test suite: **16 passed** in 14.91 seconds on the timed run. Python compileall, `pip check` (no broken requirements), JavaScript syntax validation, and Tailwind build passed. The local pytest temporary directory was used because Windows Temp was access-restricted. An earlier run completed 16 tests in 275.55 seconds without failures; the timed repeat completed normally.
- Fresh Uvicorn startup completed without startup exceptions; `/` returned HTTP 200. `/api/health` returned real dependency state: document retrieval `keyword`, semantic retrieval unavailable, Chroma available, Ollama disconnected, selected `qwen2.5:1.5b` absent/uncheckable, and market data unavailable. `/api/models` could not connect to Ollama.
- A real `/api/chat` request while Ollama was offline returned HTTP 503 with structured `ollama_disconnected` error; it did not fabricate/persist a successful answer. Actual model-generated product-aware answers and semantic retrieval are still not verified because no generation/embedding model is available.
- Attempting to start Ollama in this sandbox failed because the executable could not access/clean its existing model cache under the user's AppData Ollama directory (`Access is denied`). The model pull had previously failed on a registry blob connection. Reliable Indian live quote/chart responses likewise remain unverified because yfinance/Stooq are unreachable in this environment. The application must continue to label this accurately.
- The new behavior is covered by regression tests; there is no claim here that paid/live exchange data, streaming, multi-session browsing, or custom formula builders were completed.
- Final rerun after those changes: **14 passed**; Python compilation, JavaScript syntax, `pip check`, and Tailwind CSS build succeeded. Fresh `/` returned 200. `/api/health` now reports Ollama connected, generation model missing, embedding model missing, Chroma available, and market data unavailable. A real RELIANCE.NS quote request returned a clear structured 503 naming Yahoo Finance connectivity/rate limits and Stooq's US-only coverage. The symbol resolver maps SENSEX to `^BSESN` on BSE.

## Chat composer and local inference verification (2026-09-25)

- Reconciled the earlier Ollama-installation notes: local Ollama was started successfully and now reports `gemma3:1b`, `qwen2.5:1.5b`, and `nomic-embed-text:latest`; `/api/models` returns the two generation models and excludes the embedding model. `/api/health` observed Ollama/model/embedding/Chroma available with semantic and keyword retrieval available. Market providers remain unavailable in this environment.
- The browser displayed both installed chat models. Exercised quick switching Gemma → Qwen and checked `/api/settings`; the change applied immediately to the stored setting. The attach button and file input are exposed in the chat composer. Uploading a PDF or CSV/XLS/XLSX from chat automatically scopes it for subsequent chat; document chips use the actual stored filename and can remove scope. Dataset scope is singular; PDF scope supports multiple IDs.
- Added model/time/retrieval metadata and visible warnings for unverified citation formatting, required answer sections, or numeric checks. Replaced the misleading “100% Local Privacy” claim because the app contacts external market/web providers.
- Replaced the chat typing dots alone with an explicit “Checking relevant sources and preparing the analysis…” state, and the README documents direct chat attachments/model switching plus CPU-generation latency limits.
- Fresh app boot succeeded. `GET /`, settings, models, and health returned responses. Health accurately showed `market_data.status=unavailable` while local model/RAG dependencies were ready. Full test suite: **21 passed**. `compileall`, `pip check`, and `node --check static/app.js` completed cleanly.
- Real chat generation is not fully verified in this final host run: a short direct Ollama Gemma prompt completed in 27.8 seconds, but full StockRAG chat requests with both installed models ended in structured `ollama_timeout` errors on this machine, including a UI product-help query. The UI showed a clear service failure rather than an invented answer. Prior integration checks recorded above did produce real Qwen/Gemma PDF answers and semantic+lexical citations; current latency behavior remains a deployment limitation requiring faster hardware/model or additional inference optimization.
- This run did not verify successful live Indian stock quotes/charts: both yfinance and Stooq remained unreachable. Do not describe the feed as live in production until a provider responds and its exchange entitlement/freshness is substantiated. No paid exchange entitlement exists in the workspace.

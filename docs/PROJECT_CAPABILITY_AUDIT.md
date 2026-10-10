# MyStock AI project capability audit

**Audit date:** 2026-10-10 (Asia/Kolkata)
**Scope:** Stock market data and news, chat/LLM, web research, RAG/search, database/storage, charting, technical indicators, ML, modularity, security, and operational readiness.
**Method:** Read-only source review, review of the existing test/audit records, and SQLite schema/table-count inspection without reading saved conversation contents. No tests were rerun for this report.

## Executive assessment

The repository is a working local research-terminal prototype with meaningful engineering: FastAPI routes, provider adapters, price validation, SQLite persistence, FTS5 + FAISS retrieval, document metadata filters, local Ollama generation, chat history/branching, web crawling controls, and several chart/technical views. It is more than a mock UI.

It is **not yet a dependable trading, investment-advice, or production multi-user research system**. The main reasons are not missing screens: quote freshness and source terms are not guaranteed; India/provider coverage is partial; generated answers are not verified claim by claim; current ML is an experimental one-stock price-only ridge model with no evidence of durable predictive advantage; retrieval has no quality benchmark; large crawling and local inference are slow; and the application lacks authentication, versioned database migrations, tested backup/restore, and multi-worker operational guarantees.

### Readiness by area

| Area | Assessment | What the evidence supports |
|---|---|---|
| Local app and navigation | Working prototype | Routes, browser shell, responsive flows, and core screens were exercised in prior checks. |
| Market prices and candles | Partial | Validated OHLCV, multiple provider adapters, local history persistence, candlesticks, and period/interval controls exist. Freshness and provider equivalence are not guaranteed. |
| News feed | Partial | Fresh RSS/search plus configured company feeds, publisher filtering, source links, date filters, and attribution work. It is not exhaustive; images and India coverage are inconsistent. |
| Chat and Ollama | Working with material limits | Installed models are discovered and used; streaming and persisted history/branches exist. Recorded local generation took roughly 67–103 seconds, and broad faithfulness is unproven. |
| RAG and document search | Implemented, quality unmeasured | PDF/DOCX/TXT/HTML, metadata, FTS5 + FAISS fusion, selected-document scope, and keyword fallback are implemented. The current saved database has no indexed documents/chunks. |
| Chart analytics | Useful exploratory views | Candlesticks, volume, trend, Bollinger, RSI, MACD, ATR, performance, and Python metrics exist. Several professional chart use cases are absent and some warm-up semantics need consistency. |
| ML | Experimental only | A small expanding-window ridge regression predicts a next-bar return and compares holdout MAE with a historical-mean baseline. It is not a validated forecast service. |
| Production readiness | Not ready for public exposure | No application authentication/authorization, versioned migrations, tested recovery plan, or production-scale/soak evidence. |

## 1. System architecture and modularity

The broad module boundaries are sensible: `app/api/routes` handles HTTP, `app/market` handles providers/storage/normalization, `app/rag` handles lexical/vector retrieval, `app/documents` handles extraction, `app/analysis` assembles market analysis and prompts, and `app/services/chat.py` persists conversations. The browser is a single static application served by FastAPI.

There are still concentration points and incomplete seams:

- `app/analysis/orchestrator.py` is about 754 lines and owns heuristic intent routing, evidence collection, timeouts, prompt assembly, numeric-document fallbacks, output checks, and response provenance. Changes to one area can affect the others; split routing, evidence/tool adapters, validation, and response assembly behind explicit interfaces.
- `static/app.js` is about 1,966 lines and contains navigation, news, settings, chat, market views, chart rendering, and event handlers. Split by feature and define a small shared API/state layer; this will reduce accidental coupling and make UI behavior independently testable.
- Market provider classes share a broad interface that includes operations some providers do not support. The active default chain is yfinance followed by Finnhub, Yahoo API, Stooq, and Finviz. Upstox is configured in code but is not in that active chain. Provider selection is largely ordered fallback on failure, not field-level reconciliation or a capability registry.
- Database initialization and compatibility migrations are handwritten in `app/main.py`; they are not versioned migrations. RAG's FTS and FAISS mapping schemas are created separately with raw SQL. This works for the present local database but makes upgrades and rollback difficult to reason about.
- Some older data directories remain (`data/chroma`, alongside current FAISS/SQLite storage), which can confuse operators about which index is authoritative. Current architecture documentation names SQLite + FTS5 + FAISS as authoritative; remove or document obsolete artifacts only after confirming they contain no needed data.

## 2. Stock news, web search, and attribution

### Implemented

- `/api/news/feed` merges broad US/India searches, tracked-symbol searches, and configured company-news provider results. RSS and provider results are normalized, de-duplicated, date-filtered, sorted, and restricted to approved publisher domains/names.
- The UI fetches on opening News and on refresh/filter changes, supports 24-hour/7-day/30-day ranges, publisher/headline search, ticker labels, source links, and an empty/error retry state.
- Publisher labels, publication times, available excerpts, and source-provided images are carried through. Missing images use a publisher-initial fallback; the application does not invent article imagery.
- Google News RSS is used as a discovery transport. RSS results are excerpts and link through Google's redirect to the publisher. A bounded, allowlisted direct crawler is available for on-demand pages and checks public addresses, robots rules, redirects, payload limits, and per-domain rate limits.

### Gaps and risks

- **Coverage is opportunistic, not comprehensive.** Each RSS query returns at most eight items and the feed is capped at 100. Provider availability, geography, language, query ranking, and rate limits determine what appears. The October 10 sample returned 14 combined stories from 8 publishers and 3 India stories; this is a point-in-time sample, not a service-level guarantee.
- The RSS request currently uses `hl=en-US`, `gl=US`, and `ceid=US:en` for all queries. India is included in query text, but the transport locale remains US-English; India-specific coverage and language should be measured and configured deliberately.
- Publication dates that cannot be parsed may remain in the feed without a trustworthy event time. The UI should distinguish “date unavailable” from a known timestamp and avoid implying full freshness solely from retrieval time.
- Provider `sentiment` and `sentiment_score` fields exist in the database model, but stored records set them to `None`; there is no validated sentiment pipeline or evaluation. Do not present sentiment/market mood as implemented analysis.
- A direct company-provider path and broad RSS path have different source semantics. The UI/audit should retain whether an item is a live search result, cached record, or stale local copy at every point, including AI citations.
- Full articles are not fetched for every story. Paywalls, publisher terms, robots policies, source image licensing, and provider quotas are not exhaustively cataloged. Wikipedia is useful for background knowledge, not breaking news.
- The feed requests fresh data when opened/refreshed, but there is no scheduler or background refresh worker. A slow upstream request can block a manual refresh until the endpoint timeout.

### Recommended next steps

1. Maintain a source registry with publisher domain, geography/language, attribution/link behavior, refresh limits, licensing/terms review, and image policy.
2. Parameterize locale/market per region and add per-publisher counts, unknown-date handling, and stale/fresh provenance tests.
3. Add a robust canonical article URL resolver where permitted, while retaining the publisher title and the redirect as fallback.
4. Add a bounded background refresh job with per-source timeout, retry/backoff, freshness status, cancellation, and a last-success timestamp. Do not claim a guaranteed update cadence until it exists.
5. Build a labeled relevance/duplicate/coverage sample for US and India before expanding publishers or adding sentiment.

## 3. AI chatbot and application integration

### Implemented

- Ollama generation models are enumerated from the local Ollama catalog; embedding models are listed separately. Chat can use market quotes, technical/fundamental data, news, selected documents, crawled web evidence, and uploaded dataset profiles according to deterministic intent routing and settings.
- The chat API supports normal and server-sent-event streaming. Conversation sessions/messages persist locally; history listing, deletion, and branching from a prior message are implemented. Replies persist model, source, retrieval, and validation metadata.
- The prompt includes an application-specific answer structure and source constraints. Numeric document questions can use a direct source extract, and some unsupported document answers are withheld. Tool/provider errors are surfaced as errors rather than silently fabricating a result.
- A short-follow-up heuristic carries the previous user topic into retrieval/routing. Chart period, interval, display mode, and chart pane can be passed into chat context.

### Gaps and risks

- Intent routing is regex/keyword based, not a trained classifier or a model-driven tool planner. It can miss paraphrases, over-trigger on ambiguous terms, or call several data sources for one request. Add a documented intent/skill matrix and an evaluation set covering paraphrase, follow-up, conflicting symbols, and tool failure.
- Model availability is not model quality. Prior checks proved replies from `gemma3:1b` and `qwen2.5:1.5b`, but the recorded response latencies were around 67s and 103s on this machine. One small-model answer mixed product-line details. The interface should keep the distinction between connected, installed, generated, and evidence-verified states.
- Numeric checks and lexical/entity checks are useful guards, not claim-level entailment. Citations can be present without proving every claim next to them. There is no citation precision/recall or answer-faithfulness benchmark across all installed models.
- Chat history is bounded to recent records/messages for prompt construction. Older history is not summarized into a durable memory, so long conversations may lose context. The endpoint returns at most 50 sessions; server-side search/pagination is not implemented.
- Streaming disconnect/cancellation and concurrent generation behavior need explicit lifecycle tests. A request timeout does not necessarily stop work already running inside a thread or Ollama.
- The app is local/single-user in its data model. There is no user identity, tenant boundary, or authorization guard around sessions, documents, settings, and data APIs. It must not be exposed to an untrusted network as-is.

### Recommended next steps

- Keep prompt/tool routing explicit and auditable, but move it into modular tool contracts with per-tool input/output schemas and cancellation.
- Build a small golden test set: factual general chat, quote timestamp/source, chart-pane interpretation, multi-turn references, document answers, missing evidence, web findings, and provider/model failures. Score exactness, citation correctness, latency, and refusal quality per model.
- Add context-window-aware token budgeting (not only character caps), optional conversation summaries with source links, and history pagination/search.
- Show model ID, retrieval mode, data timestamp/status, citations, and any failed providers in each response's details. Avoid marketing “fast” unless measured on the target hardware.

## 4. RAG, crawling, and search quality

### Implemented

- PDF, DOCX, TXT, and HTML documents are extracted, chunked, and stored in SQLite FTS5 with metadata. CSV/XLSX are profiled by pandas and their computed statistics/samples can be supplied to chat.
- FAISS CPU stores dense embeddings; SQLite remains the chunk/metadata source of truth and maps vector IDs to chunk row IDs. Retrieval fuses semantic and FTS rankings using reciprocal-rank-style weights, applies metadata/document scope, includes a small recency/official-filing boost, and degrades to keyword search if embeddings are unavailable.
- Metadata fields include ticker/company/exchange/country/sector/industry, document type, filing dates, source, and URL. Selected-document IDs constrain retrieval. Web search can index RSS result excerpts, while direct crawls index permitted page text.
- The crawler has useful safeguards: exact host allowlisting, standard ports, public-IP check, robots check, redirect rejection, byte limits, and per-host throttling. Scanned-PDF OCR is optional and requires external Tesseract.

### Gaps and risks

- **Current saved database has zero `documents`, zero `rag_chunks`, zero RAG metadata rows, and zero FAISS mappings.** This confirms the RAG code path exists, but this database currently has no indexed document corpus to answer user-file or crawled-page questions from. The existing upload directory contains two small files while the document table is empty; determine whether these are test/orphan files before cleaning them.
- Retrieval quality is unmeasured. There is no curated query/relevant-passage dataset, Recall@k/MRR/nDCG score, citation page/section accuracy score, or regression gate for chunking and embedding changes.
- Dense retrieval uses `IndexFlatIP` (exact search) rather than an approximate index. With metadata filtering it loads eligible rows and reconstructs/scans vectors in batches. This is reasonable at small local scale but becomes linear in the number of filtered chunks and can make broad document corpora slow.
- FTS and vector indexes have custom reconciliation/migration logic. Database rows, FTS virtual-table data, JSON metadata, mapping rows, and persisted FAISS files require tested rebuild/recovery procedures. There is no maintenance command/report for orphaned or missing mappings.
- The query filter normalizes some exchange-suffixed tickers to a bare ticker in `build_metadata_filter`, while uploaded/crawled metadata may retain `.NS` or `.BO`. Add tests for `AAPL`, `RELIANCE.NS`, `RELIANCE.BO`, and ambiguous symbols across both the lexical and semantic filters; otherwise exact-match metadata can exclude a correctly tagged Indian document.
- Long crawls run synchronously in a worker thread inside the request. An SEC filing indexed to hundreds of chunks exceeded a 240-second client wait in prior recorded checks. There is no job state, progress UI, cancellation, resumability, or deduplicated concurrency key for canonical URLs.
- Query-time search merges sparse lexical/semantic ranks and lightweight recency boosts; it does not use a cross-encoder reranker, structured table retrieval, section hierarchy, or field-aware financial fact retrieval. PDF page boundaries and DOCX sections/tables are retained, but table question answering has no specialized validation.
- Legacy `.doc` is unsupported; OCR was not installed/verified. Large spreadsheet profiling is bounded but samples the first rows and columns, so it can miss late-file anomalies or rare categories.

### Recommended next steps

1. Add a read-only RAG health/admin report: source counts, chunk counts, document statuses, orphan rows, vector-map/index counts, embedding model/version, and rebuild status.
2. Add corpus-based retrieval evaluations and exact metadata-filter tests, especially exchange suffix, multi-ticker, filing type/date, and selected-document scope.
3. Move crawl/extraction/embedding to persistent background jobs; add dedupe keys, progress, retries, cancellation, and recovery after restart.
4. Benchmark SQLite/FTS/FAISS at 10k/100k/1M chunks; introduce a vector index chosen for measured scale and maintain incremental consistency.
5. Add OCR setup checks and table/financial-statement extraction evaluation before describing scanned reports or complex tables as fully supported.

## 5. Database and persistence audit

The configured primary database is SQLite at `data/stock_terminal.db`; a read-only schema/count inspection on 2026-10-10 found:

| Table | Rows | Notes |
|---|---:|---|
| `chat_sessions` | 7 | Session/parent/branch IDs and selected document/dataset IDs are stored. |
| `chat_messages` | 25 | Message body, role, timestamp, citations, and metadata JSON. Conversation text was not inspected for this audit. |
| `documents` | 0 | No registered uploaded/crawled documents in this database snapshot. |
| `rag_chunks` / `rag_chunk_metadata` / `rag_vector_map` | 0 / 0 / 0 | No retrievable source chunks/vectors in this snapshot. |
| `price_bars` | 366 | Validated OHLCV rows with source, retrieval time, status, and interval. |
| `fundamental_metrics` | 12 | Numeric value, metric, source, retrieval time, status; the schema uses `period='latest'` for current provider metrics. |
| `news_articles` | 119 | Publisher/ticker/source metadata and optional summary/image/sentiment columns. |
| `cache_entries` | 18 | JSON cache values with source and expiry. |
| `user_settings` | 1 | One global settings row, not per-user settings. |

### Database strengths

- Unique constraints protect price-bar identity by symbol/timeframe/source and fundamentals by symbol/metric/period/source. The cache uses atomic SQLite upsert after a previous same-key race.
- Price bars are validated for finite positive OHLC values, OHLC consistency, nonnegative volume, valid timestamps, and conflicting duplicates before persistence.
- News links/titles/timestamps/media are normalized before storage; session history and answer provenance are kept in structured columns/JSON.

### Database gaps

- No Alembic or other ordered migration history; startup includes inline `ALTER TABLE` checks. Add versioned migrations and test upgrades from a copy of each supported schema.
- SQLAlchemy models do not declare foreign-key relationships for chat messages/sessions, document chunks, or branch parents. Deletion and consistency are mostly application-managed. Add constraints where SQLite behavior permits, plus explicit cleanup/reconciliation jobs.
- `NewsArticle.url` is globally unique but the row also has one scalar `symbol`/`ticker`. Upserting the same article for another symbol can overwrite that association; model article identity separately from article-to-symbol associations (many-to-many or normalized relation).
- `FundamentalMetric` stores values as floats and `period='latest'`; it lacks normalized units/currency/scale, fiscal period, statement date, GAAP definition, and provider-specific raw values. Cross-provider comparisons can silently mix semantics.
- There is no tested backup/restore, retention/compaction policy, encryption-at-rest policy, document-delete workflow audit, or storage capacity alert. Uploaded files and SQLite records can become orphaned.
- SQLite and the process-local FAISS lock are appropriate for one local process but not a multi-worker deployment. Multiple app processes can race over the same FAISS sidecar/index metadata. Define single-writer behavior or move to a shared vector/database service before scaling workers.
- Existing persisted table counts are a local snapshot, not guaranteed production data. The application has one shared settings row and no user/tenant ownership columns.

## 6. Stock data and provider reliability

The primary quote/history provider is yfinance, with Finnhub, Yahoo API, Stooq, and Finviz in the configured fallback sequence. Upstox has a provider implementation and access-token configuration but is not wired into `app/dependencies.py`'s active fallback list. Finnhub requires an API key; Stooq is US-only and primarily quote/history; some adapters do not support the broad abstract interface.

Strengths include symbol normalization, per-operation fallback, status/source metadata, provider response validation for OHLCV, SQLite history persistence, cache TTL, stale local history fallback, and chart retrieval timestamps/last-bar labels.

Key limitations:

- yfinance is unofficial and the app correctly labels quote freshness as unverified. A request timestamp is not an exchange timestamp. No consolidated real-time entitlement/feed is present.
- Fallbacks are not reconciled field-by-field. Providers may disagree on ticker mapping, currency, adjustment policy, market session, corporate actions, volume, and timestamp. A single successful fallback is treated as the result.
- The validation checks prices and OHLC consistency but not currency, exchange calendar/session alignment, bar interval completeness, plausible price jumps, stale quote age, corporate-action adjustment equivalence, or provider revisions.
- Fundamentals are mostly a selected set of provider fields, not a complete normalized financial-statement model. Data is labeled unverified/stale, and cross-provider periods/units are not harmonized.
- Indian exchange coverage/history was only partially exercised in the existing report. The mere presence of an Upstox adapter does not mean it is active or verified.

Before using for decisions, add a provider/capability matrix and a per-field source/freshness contract; compare known instruments and periods across providers; test holidays, splits/dividends, currencies, missing bars, and stale fallback. For a real-time claim, use a properly entitled, timestamped source.

## 7. Charts and indicator use cases

### Current chart menu and appropriate interpretation

| View | Implemented use | What it does not establish |
|---|---|---|
| Line price | Closing-price path for a quick trend overview. | Intraday movement, execution price, or adjusted total return unless provider data is explicitly adjusted. |
| Candlesticks | Open/high/low/close direction and range per bar. | Candlestick-pattern signals or a tested trading strategy. |
| Volume | Per-bar traded-volume histogram, direction-colored. | Order-book liquidity, venue-wide volume completeness, or volume-profile distribution. |
| Trend (SMA 20 / EMA 20) | Smooth recent close series against price. | A statistically validated entry/exit signal. |
| Bollinger | Rolling close center and ±2 standard deviations. | Probability bounds or guaranteed support/resistance. |
| RSI 14 | Momentum oscillator with 30/70 guide levels. | A standalone overbought/oversold trade recommendation. |
| MACD | EMA12−EMA26, signal EMA9, and histogram. | A backtested strategy or predictive edge. |
| ATR 14 | Absolute true-range volatility estimate. | Direction; ATR is a range/volatility measure. |
| Performance | Indexed close series with first close = 100. | Benchmark-relative excess return; it currently compares the chosen series only. |

The chart supports 1mo/3mo/6mo/1y visible periods in the UI, and daily/weekly/monthly intervals in settings/API; available history supports up to 5y. Responsive resizing, crosshair values, line/candle mode, and chat context are implemented. Prior browser verification exercised line/candlestick, RSI and chart tabs, but not every zoom/pan/range/empty-provider state.

### Chart correctness gaps

- Price charts use provider OHLC and close values. The user interface does not clearly offer adjusted-close vs raw-close/total-return selection, dividend/split markers, or a corporate-action explanation.
- The chart-ready indicator path uses rolling Bollinger/SMA/ATR windows with `min_periods=1`, whereas the summary technical path has different warm-up behavior (for example ATR requires 14 bars there). This can show partial-window indicators as if they were full-period metrics. Align formulas, warm-up thresholds, and tooltips.
- Monthly bars are date-only, which is fine for the current daily/weekly/monthly chart intervals; adding intraday data would require timestamp-safe normalization rather than truncating timestamps to the date.
- The volume bar color compares to a prior row by filtered-array index; if an invalid-volume row is skipped, comparison can be against the wrong preceding session. Color against the previous valid close explicitly.
- No benchmark overlay, relative-strength ratio, drawdown-underwater panel, realized volatility history, volume profile, event/earnings calendar overlay, split/dividend markers, or multi-symbol OHLC overlay exists as a distinct chart view.
- Crosshair and fit-to-content are present; accessibility descriptions exist, but keyboard data-point navigation and a tabular chart-data fallback are not established.

### Useful additions, sequenced by investor workflow

1. **Decision context:** raw vs adjusted close selector; benchmark overlay (SPY/Nifty/Sensex selected by market); return and drawdown comparison; latest-bar/source/freshness panel.
2. **Risk:** drawdown chart, rolling 20/60/252-bar volatility, ATR percent-of-price, gap returns, and volume-relative-to-20-bar-average.
3. **Fundamental/event context:** earnings/dividend/split markers, financial-period shading, and source-linked disclosures. Avoid asserting events until verified against dated sources.
4. **Diagnostics:** dividend-adjusted total-return view, data-gap/session warnings, corporate-action checks, and an accessible table export.
5. **Strategy research:** only after historical point-in-time data and survivorship/corporate-action handling exist, offer backtests with fees, slippage, out-of-sample dates, and benchmark comparison.

## 8. Technical calculations and ML

### What currently exists

- Python calculates SMA20/SMA50, EMA20, RSI14, MACD/signal/histogram, Bollinger bands, ATR14, annualized volatility, period drawdown, and recent returns from price history.
- A separate statistical scenario uses historical log-return mean/volatility to produce a central value and an 80% lognormal interval. It is explicitly described as illustrative, not validated.
- `walk_forward_return_model` is a hand-built ridge regression using four price-derived features (one-bar return, 5-bar momentum, 20-bar momentum, and 20-bar volatility). It uses an expanding time-ordered training window, up to 20 holdout bars, and compares MAE to the training historical-mean return baseline. It emits a next-bar estimate plus limitations.
- For insufficient visible history, the service retries ML using a longer same-interval period: 1y daily, 2y weekly, 5y monthly. The visible chart indicators remain tied to the displayed period.

### What is not implemented or not demonstrated

- This is not a collection of trained financial ML models. There is no news NLP/sentiment classifier, fundamental model, event model, portfolio optimizer, company ranking model, anomaly detector, options model, or user-specific learning. Dataset profiling is deterministic descriptive analytics, not an ML training pipeline.
- The holdout is small (at most 20 bars), one symbol/run at a time, and no evidence shows it beats baseline over a broad universe or repeated rolling periods. Prior recorded evaluation found daily/weekly estimates did not beat the historical-mean baseline; monthly lacked the minimum 65 closes.
- The 5-year monthly provider range is typically about 60 bars, below the model's 65-close minimum; monthly ML may therefore remain unavailable for normal 5-year requests. Either revise the minimum using honest validation or return a clear unavailable status.
- No reproducible training/evaluation dataset snapshots, model artifact/version, feature version, benchmark suite, confidence calibration, directional accuracy, trading-cost evaluation, multiple-testing correction, or drift monitoring exists.
- The input is only closing-price returns/volatility. It omits adjusted corporate actions, fundamentals, news, macro conditions, sector/benchmark context, liquidity, and market regime. No model output should be represented as an investment forecast.
- Statistical scenario estimates assume historical distribution persistence and do not model jumps, regime shifts, fees, liquidity, or corporate actions. The UI must keep the model estimate and scenario band distinct from actual price history and clearly expose the window/source.

### Minimum credible ML roadmap

1. Define task and target (forecast horizon, target return, use, and non-use) before optimizing a model.
2. Freeze point-in-time data and corporate-action rules. Add chronological train/validation/test periods across many symbols and multiple regimes.
3. Compare against persistence, historical mean, and simple momentum baselines; report MAE/RMSE, directional accuracy, calibration, turnover, and net-of-cost backtest metrics where relevant.
4. Persist data/model/feature versions and exact evaluation results. Reject models that fail predeclared baselines; show “not useful” where appropriate.
5. Keep the current output labeled experimental and non-predictive until that evidence exists.

## 9. Security, privacy, and operations

- There is no authentication or authorization layer. Anyone able to reach the service can potentially use its chat/document/settings/data endpoints. This is acceptable only for a trusted local development environment; bind to localhost/firewall before any broader access.
- SQLite stores conversation text, uploaded/crawled content metadata, market history, and settings in local files. No user/tenant partition, at-rest encryption, explicit retention controls, or tested backup/restore is documented.
- Upload sizes are capped at 25 MB and several formats are signature/type checked; extension-based type selection and extraction still need malicious/polyglot/archive-bomb testing and operational quotas. No antivirus/content-disarm workflow is present.
- The crawler blocks redirects, checks DNS results, exact allowlisted hosts, and robots. It does not pin the resolved public address to the subsequent connection; keep outbound network policy restricted and add DNS/egress defenses before broad exposure.
- Logs include request IDs, route, status, latency, and provider failure categories. There is no metrics/tracing dashboard, provider budget/quota monitor, alerting, job queue, or tested multi-process deployment plan.
- Prior tests included a small 20-request concurrency smoke test for cache/API health, not an actual load, soak, or database recovery test.

## 10. Existing verification evidence and its limits

Existing `docs/TEST_REPORT.md` documents tests for market validation/storage, technical calculations, RAG metadata/hybrid behavior, PDF/DOCX/TXT/HTML, crawling guards, chat history/branching/streaming, and provider paths. The report in the repository is stale at **72 passed**. The last run recorded in the active work before this audit was **74 passed** after news-feed changes, with Python compilation, JavaScript syntax, and diff checks passing. These are test-pass counts, not proof of broad model faithfulness or market-data accuracy.

Prior end-to-end records say: US AAPL history and quote, one Indian quote, several chart views, two installed Ollama generation models, selected SEC filing crawl-to-index-to-chat, and browser workflows were exercised. The same records call out slow large-document crawl, slow local responses, stale/unverified quote freshness, limited India coverage, and unverified general citation entailment. Do not interpret those spot checks as a current uptime guarantee.

## 11. Prioritized gap register

| Priority | Gap | Why it matters | Completion evidence |
|---|---|---|---|
| P0 | Add authentication/authorization or enforce a strictly local-only boundary | Chats, settings, uploads, and market endpoints are otherwise exposed to anyone who can connect. | Security test proves unauthenticated requests are denied, or deployment enforces localhost/network restrictions. |
| P1 | Market data provenance and freshness contract | Retrieved-at time is not exchange time; fallback sources can have different semantics. | Per-field source/as-of/status, adjusted-price policy, stale-age rules, and provider matrix tested for US/India. |
| P1 | RAG corpus integrity and evaluation | Current DB has no indexed docs; retrieval correctness is not measured. | RAG health/rebuild report, metadata suffix tests, benchmark Recall@k/MRR/citation accuracy. |
| P1 | News coverage and publisher registry | Regional/feed completeness, image rights, and provider behavior vary. | Region-aware locale tests, source/terms registry, stale/unknown date coverage metrics. |
| P1 | Claim-level chat evidence quality and latency | Citations do not prove every statement; local responses are slow. | Per-model faithfulness/citation/latency evaluation with a target hardware profile. |
| P1 | Versioned migrations and recoverable database/index | Startup migrations and sidecar indexes are fragile during upgrades or crashes. | Migration upgrade tests, backup/restore drill, FTS/FAISS reconcile/rebuild command. |
| P2 | Chart/data correctness parity | Warm-up semantics, adjusted prices, market calendars, and visible chart cases can mislead. | Shared indicator formulas; reference fixtures; split/dividend/missing-bar tests. |
| P2 | ML evaluation and honest scope | A small price-only model can look predictive without durable edge. | Frozen multi-symbol walk-forward benchmark; baseline and net-cost evaluation; versioned results. |
| P2 | Background jobs and cancellation | Large crawl and provider refresh can tie up requests and survive client disconnects. | Durable job state, progress, retry/backoff, cancellation, recovery, concurrency tests. |
| P2 | Normalize financials/news relationships | Unitless metrics and global-unique article URLs can overwrite/blur entity associations. | Normalized units/periods and article-to-ticker relation tests. |
| P3 | Modularize orchestrator and frontend | Large files increase change risk and impede isolated tests. | Feature modules with stable interfaces and behavior tests. |
| P3 | Accessibility, broad UI/browser coverage, and scale benchmarks | Existing manual checks cover representative flows only. | Keyboard/screen-reader, zoom, mobile, browser matrix, load/soak and recovery reports. |

## Bottom line

The project has a substantive local prototype with real provider calls, persistence, charts, Ollama, RAG, and web research. The strongest next investment is evidence and reliability work: secure the deployment boundary, formalize market provenance, populate and benchmark the RAG corpus, evaluate every model's answers, normalize financial/news storage, and add recoverable background work. More chart types or more model names alone will not close these correctness gaps.

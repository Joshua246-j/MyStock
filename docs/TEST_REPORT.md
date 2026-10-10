# Test report

Date: 2026-10-10 (Asia/Kolkata)

## Automated checks

- `python -m pytest tests/ -q --basetemp .pytest-tmp-final4 -p no:cacheprovider` — **72 passed, 0 failed** (latest run on 2026-10-10, 3.63 seconds).
- Python `compileall` for `app` and `tests` — passed.
- `node --check static/app.js` — passed.
- `python -m pip check` — passed.
- `npm run build:css` — passed.

Coverage includes routing, technical calculations, market fallback/storage, OHLCV validation, metadata extraction/filtering, FTS5/FAISS hybrid retrieval and degradation, PDF page/OCR handling, DOCX section/table extraction, TXT/HTML extraction, deterministic numeric evidence checks, robots exclusion, and untrusted-evidence prompt boundaries.

## Runtime and browser checks

- 2026-10-09 web research: Google News RSS returned current Reuters headlines for a live query. The result parser filters publisher URLs against the configured allowlist; each result is recorded and keyword-indexed as a headline/feed excerpt, then retrieval is restricted to the result IDs for that search. A no-database-write crawl probe fetched and parsed `https://www.sec.gov` successfully with indexing stubbed. Automated tests cover publisher allowlisting, excerpt indexing, per-search RAG scoping, and safe direct crawling.
- 2026-10-09 Ollama: every locally installed generation model (`gemma3:1b`, `qwen2.5:1.5b`) returned a real local response. The UI presents installed generation models separately from the embedding model.
- 2026-10-09 chat history: assistant replies now persist exact model, retrieval mode, timestamp, evidence checks, and answer method; migration adds the field to existing databases. A stream/history test confirms provenance survives session restoration.
- Current automated suite: `72 passed` (includes chart-to-chat context, same-interval ML lookback, conversation-aware follow-up retrieval, explicit ticker precedence, filing routing, normalized news ordering, web-result deduplication, unsupported document-answer withholding, and concurrent cache upsert coverage, alongside prior RAG, model-routing, and provenance tests).
- Python `compileall` for `app` and `tests` — passed; `node --check static/app.js` — passed after chart/chat integration changes.
- Live `/api/health` check — API, Ollama (`gemma3:1b`), embedding model, FAISS, keyword retrieval, and configured market provider reported available. Market quote freshness remains unverified.
- 2026-10-10 live free-source check: Google News RSS returned three Reuters results for a test market query. The SEC homepage passed the allowlist/robots/public-host crawl path and text extraction; indexing was stubbed for this network smoke check to avoid writing a test document to the saved database. Isolated automated tests verify indexing and scoped RAG retrieval.
- 2026-10-10 conversation/RAG fixes: short follow-up questions now reuse the previous user topic for intent routing and retrieval; explicitly typed tickers override the open chart symbol. A document follow-up no longer gets market-quote intent from the word “about.” Prompt history has a context-size-based character bound. Web search reuses existing indexed URLs rather than loading every web-document metadata row and duplicating search-result chunks.
- 2026-10-10 news fixes: parseable RFC 822/RSS dates are normalized for local persistence, publisher items are URL/image-validated, deduplicated, and sorted by publication time, and headline citations include source URLs.
- 2026-10-10 audit fix: removed “about” as a standalone market-quote intent. Added a regression assertion that a document follow-up does not call the quote provider. Targeted test passed; full suite passed 60/60.
- 2026-10-10 fresh runtime check: Ollama was installed but stopped at first check. Started the local Ollama service; the health endpoint then reported the configured `gemma3:1b`, `nomic-embed-text`, FAISS, and semantic retrieval available. Direct generation requests to both installed chat models (`gemma3:1b`, `qwen2.5:1.5b`) returned `READY`.

- Fresh Uvicorn startup; `/`, `/api/health`, `/api/documents`, and symbol resolution returned successfully.
- Health reported yfinance, Ollama generation, the local embedding model, FAISS CPU, and keyword retrieval available.
- AAPL quote and 1-month history returned from yfinance; 23 daily bars through 2026-10-08 persisted in SQLite. Quote was explicitly marked `UNVERIFIED_FRESHNESS`.
- Reliance Industries resolved to NSE and returned a provider quote. AAPL financial metrics and eight recent news results also returned from yfinance and were persisted through the configured local storage path.
- Browser search with India selected as default loaded AAPL as the US listing after fixing default-exchange suffixing for built-in US symbols. Quote, history, volume, chart, candlestick mode, and RSI pane rendered; no browser console errors were observed.
- Real PDF workflow: uploaded/indexed a temporary fixture with ticker and filing metadata, asked a numeric filing question through local Ollama-backed application flow, and received an extractive answer with page citation. A second fixture lacking the requested value produced deterministic insufficient-evidence response. Temporary fixtures, vector records, and chat sessions were removed afterward.
- API workflow: uploaded TXT and HTML research documents, verified script removal and ticker-filtered hybrid retrieval, then re-uploaded identical content and received the existing document ID without duplicate indexing. A DOCX upload was also indexed and retrieved through the FAISS/FTS5 hybrid path. Temporary files, metadata rows, FTS records, and FAISS mappings were removed. DOCX section/table extraction is covered by a generated-file test.
- Final FAISS-backed chat workflow: uploaded a temporary PDF through the API, queried its FY2026 revenue, and received the supported value with a page citation and hybrid retrieval. Asking for net income when only revenue was present returned deterministic insufficient evidence. Temporary document, vector/FTS rows, and chat sessions were removed.
- Fresh Uvicorn startup and browser check: health reported Ollama, embeddings, FTS5, FAISS CPU, and market provider available. The AAPL terminal then rendered provider quote, history, volume, and recent news without browser console errors.
- Local Ollama Qwen generation and nomic embedding service were available during the run.

### Final deep audit and end-to-end verification (2026-10-10)

- All ingestion, chat history, and live crawl writes below used the isolated `.audit-run/audit-v2.db` scratch database; the saved application database was not used for those tests.
- Downloaded Apple's official FY2025 10-K from SEC.gov through the app crawler. Robots/public-host checks passed, the document completed indexing with 340 passages and SEC/ticker metadata, and selected-document hybrid retrieval returned the SEC filing source. The request exceeded the 240-second client wait before the isolated record completed, so large crawls remain too slow for a comfortable interactive flow on this machine.
- Both installed generation models, `gemma3:1b` and `qwen2.5:1.5b`, generated replies through the application using the selected SEC filing and local `nomic-embed-text` embeddings. Observed generation times were about 67s (Gemma) and 103s (Qwen). A Qwen request with the earlier longer response format hit the output-token limit; concise-mode instructions produced a complete reply within the configured 256-token limit. One Gemma answer mixed product-line details, so universal claim-level entailment is still not verified.
- Uploaded the local 45-byte `test_doc.txt` fixture through the chatbot attachment button. Selected-document RAG quoted the exact source sentence and `$125 million` value, cited `test_doc.txt`, labeled the answer “Source extract · no LLM,” and persisted the two-message conversation in the scratch database.
- AAPL live market checks returned a yfinance quote (explicitly marked freshness-unverified), fundamentals, four ticker-associated headlines, 251 daily bars and 53 weekly bars for one year, and 60 monthly bars over five years. Technical calculations populated daily/weekly/monthly indicators. The daily and weekly experimental walk-forward estimates did not beat the historical-mean baseline; monthly ML correctly declined due to fewer than 65 bars.
- Browser checks at 390×844 and 1280×720 covered chatbot layout, history/new-chat, model picker/settings, attachment flow, exit/page navigation, market detail, chart views including candlesticks and RSI, watchlist/compare, project-status details, and US/India news filters. The US feed showed nine headlines; the India feed correctly showed an empty state with zero headlines. No browser console errors were observed in these workflows.
- A first cold-cache concurrent quote smoke test produced one HTTP 500 from same-key cache writes. Cache writes were changed to an atomic SQLite upsert; the retest with 10 concurrent health checks and 10 cold ORCL quote requests returned 20/20 HTTP 200 (about 1.15s p50 / 1.51s p95). This is a small concurrency smoke test, not a capacity benchmark.
- Final automated checks: **72 passed**; Python compile, JS syntax, CSS build, dependency check, and `git diff --check` passed.

## Not verified / known limits

- Full Indian historical coverage, full chart zoom/pan/range interaction, exhaustive fundamental periods, and provider-to-provider data equivalence were not independently verified. A Reliance quote was verified separately. A live allowlisted Investopedia page returned HTTP 403; SEC crawling/indexing did work, but other sites may refuse access.
- Scanned-PDF OCR requires a separately installed Tesseract executable; it was absent in this environment, so OCR extraction itself was not verified. Legacy binary `.doc` is unsupported (modern `.docx` is supported).
- News/web search supplies headlines and excerpts, not full-text access for every publisher. The live India news filter returned no headlines. Scheduled ingestion, dedicated sentiment validation, universal claim-to-source entailment, true high-load/soak testing, and reliable large-crawl latency remain incomplete. External availability, source freshness, robots rules, and rate limits vary.

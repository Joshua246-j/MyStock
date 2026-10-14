# StockAI Terminal — Feature Tracker

**Last Updated:** 2026-10-14  
**Audit Baseline:** 74/74 tests passed → 86/86 tests passed post-fixes  
**Status Legend:**
- `Working` — Feature is fully implemented, verified with automated tests, and tested end-to-end.
- `Partial` — Core functionality works; edge cases or non-critical enhancements remain.
- `Broken` — Feature is defective, fails tests, or prevents proper application operation.
- `Not Tested` — Code exists in repository but has not been verified in the current test suite.
- `Not Implemented` — Feature is planned or requested but not yet built.

---

## 1. LLM & Inference Integration

| Feature | Status | Verification & Notes |
|---------|--------|----------------------|
| Local Ollama Client | `Working` | Async HTTP communication, graceful degradation on connection failure, non-blocking model catalog caching. |
| Model Switching | `Working` | User can switch between installed models (e.g. Gemma, Qwen) via settings or per-request chat payload without losing chat history. |
| Model Availability Check | `Working` | Early health checking prevents wasteful retrieval runs when Ollama is offline. |
| Adaptive Greetings Fast-Path | `Working` | Pure greetings ("Hi", "Hello", "Good morning") bypass market retrieval, RAG, and crawler; responds warmly in 1-2 sentences. |
| Simple Q&A Routing | `Working` | Routes conceptual and general questions to direct answers without injecting irrelevant ticker data. |
| Deterministic Numeric Extraction | `Working` | Numeric facts from retrieved documents are answered deterministically from verified source passages without hallucination. |
| Grounding Entailment Validation | `Working` | Detects unsupported terms and mismatched entity relations; withholds fabricated claims and reports limitations. |
| Streaming Inference (SSE) | `Working` | Token-by-token streaming via `/api/chat/stream` with real-time UI updates. |
| Custom System Persona | `Working` | Supports custom persona in settings/chat with 2000 character validation guardrail. |

---

## 2. User-Controllable LLM Settings

| Feature | Status | Verification & Notes |
|---------|--------|----------------------|
| Model Selection (`ai_model`) | `Working` | Persisted in SQLite `user_settings`, validated against installed models. |
| Temperature Control (`temperature`) | `Working` | Range [0.0, 2.0], validated on update, passed to Ollama options. Includes factual accuracy caution. |
| Nucleus Sampling (`top_p`) | `Working` | Range [0.0, 1.0], validated, passed to Ollama options. |
| Top-K Sampling (`top_k`) | `Working` | Range [0, 1000], supported in settings and per-request `ChatRequest`. |
| Repeat Penalty (`repeat_penalty`) | `Working` | Range [0.0, 5.0], supported in settings and per-request `ChatRequest`. |
| Random Seed (`seed`) | `Working` | Range [0, 2147483647], supported for reproducible outputs. |
| Max Output Tokens (`max_output_tokens`) | `Working` | Range [64, 16384], aligned across settings route, chat route, and Ollama client. |
| Context Window Size (`context_size`) | `Working` | Range [256, 131072], bounds prompt history length dynamically. |
| Response Detail Level (`response_detail`) | `Working` | Options: `concise`, `balanced`, `detailed`. Adjusts system prompt directives. |
| Request Timeout (`request_timeout`) | `Working` | Range [1, 180] seconds, applies to retrieval and model calls. |
| Settings Reset (`DELETE /api/settings`) | `Working` | Resets all user settings to default values atomically. |
| Settings Metadata Schema (`GET /api/settings/schema`) | `Working` | Exposes metadata (labels, ranges, groups, descriptions) for UI tooltips and dynamic forms. |
| Unsupported Parameter Warnings | `Working` | Unknown settings keys rejected with HTTP 422 and descriptive error message. |

---

## 3. Market Data Pipeline

| Feature | Status | Verification & Notes |
|---------|--------|----------------------|
| YFinance Primary Provider | `Working` | Real-time and delayed quotes, historical OHLCV bars, financial metrics, company news. |
| Multi-Provider Fallback Chain | `Working` | Fallback chain: YFinance → Finnhub → YahooApi → Stooq → Finviz. |
| Indian Equity Ticker Resolution | `Working` | Normalizes NSE bluechips (e.g., RELIANCE → RELIANCE.NS, TCS → TCS.NS) and aliases. |
| Data Provenance & Freshness Labels | `Working` | Displays provider, timestamp, currency, and freshness status (`LIVE`, `CACHED`, `STALE`, `UNVERIFIED_FRESHNESS`). |
| Database Caching & Concurrency | `Working` | SQLite cache with configurable TTL and atomic upsert for concurrent request safety. |
| Technical Indicator Calculation | `Working` | SMA, EMA, RSI, MACD, Bollinger Bands, ATR calculated from validated historical data. |
| Walk-Forward Price Model | `Working` | Time-series projection model evaluated against historical baselines; declines gracefully when data is insufficient (<65 bars). |
| Invalid Ticker Handling | `Working` | Rejects malformed symbols cleanly without crashing API or leaking stack traces. |
| Stale Data Transparency | `Working` | When provider data is cached or delayed, the response clearly labels the timestamp and status. |

---

## 4. RAG & Document Intelligence

| Feature | Status | Verification & Notes |
|---------|--------|----------------------|
| Multi-Format Document Ingestion | `Working` | Ingests PDF, DOCX, TXT, HTML with text extraction, deduplication, and hashing. |
| Semantic Search (FAISS) | `Working` | Vector embedding search using local `nomic-embed-text` with CPU FAISS singleton. |
| Lexical Keyword Search (FTS5) | `Working` | SQLite FTS5 lexical index for fast keyword matching. |
| Hybrid Retrieval (RRF Fusion) | `Working` | Reciprocal Rank Fusion combining semantic and lexical scores. |
| Graceful Degradation | `Working` | Falls back to pure keyword search when vector store or embedding model is offline. |
| Scoped Document Retrieval | `Working` | `document_ids` scoping restricts RAG to selected files; prevents unrelated document leaks. |
| OCR Handling for Scanned PDFs | `Partial` | Detected via page text density; delegates to Tesseract when binary is installed. |
| Document Ingestion Error Handling | `Working` | Empty documents, corrupt files, and unsupported formats are rejected with HTTP 422. |

---

## 5. Web Research & Crawler

| Feature | Status | Verification & Notes |
|---------|--------|----------------------|
| Google News RSS Search | `Working` | Queries financial news feed, parses RSS XML, normalizes RFC 822 publication dates. |
| Publisher Domain Allowlist | `Working` | Restricts crawling to approved reputable financial domains (Reuters, Bloomberg, WSJ, CNBC, etc.). |
| SSRF & Private Network Protection | `Working` | Blocks private/loopback IP addresses (RFC 1918, 127.0.0.0/8, 169.254.0.0/16, IPv6 loopback). |
| Robots.txt Compliance | `Working` | Fetches and parses `robots.txt` per host; respects `Disallow` rules. |
| Prompt Injection Protection | `Working` | Encapsulates crawled web content within `<untrusted_evidence_json>` boundary tags. |
| Search Result Deduplication | `Working` | Checks existing URL hashes before re-crawling; avoids duplicate database records. |

---

## 6. Chat Sessions, History & Branching

| Feature | Status | Verification & Notes |
|---------|--------|----------------------|
| Session Management | `Working` | Create, retrieve, rename, pin, and delete conversation sessions. |
| Conversation Branching | `Working` | Branches from any past message ID, copying prior turns into a new independent session. |
| Context-Bounded History | `Working` | History trimmed to bounded character budget proportional to `context_size`. |
| Follow-Up Topic Tracking | `Working` | Carries prior user topic into genuine follow-up queries ("why", "what about", "how does it work"). |
| Context Isolation | `Working` | Unrelated prompts and greetings do not inherit prior stock or document context. |
| Failed Turn Cleanup | `Working` | Failed generation requests automatically remove the orphaned user message to keep history clean. |

---

## 7. Frontend, UI & Diagnostics

| Feature | Status | Verification & Notes |
|---------|--------|----------------------|
| Dark / Light Theme | `Working` | Persisted theme selection with CSS custom property variables and glassmorphism styling. |
| Responsive Layout | `Working` | Mobile-friendly and desktop responsive layout with flexible sidebar and collapsible panels. |
| Market Chart Rendering | `Working` | Line and candlestick chart views with volume bar overlay and technical indicators. |
| Chat Markdown & Citations | `Working` | Clean Markdown rendering with copyable code blocks, table formatting, and collapsible source cards. |
| Document Attachment Flow | `Working` | File picker for document upload and scoping directly from the chat interface. |
| System Health Panel | `Working` | Displays status of API, Ollama, Embeddings, FAISS, Keyword Index, and Market Provider. |
| Model Selector Dropdown | `Working` | Dynamically populates with locally installed Ollama generation models. |

---

## 8. Database & Schema

| Feature | Status | Verification & Notes |
|---------|--------|----------------------|
| SQLite Primary Storage | `Working` | Single file SQLite database (`data/stock_terminal.db`) with WAL mode. |
| Alembic Migration System | `Working` | Initialized configuration (`alembic.ini`, `alembic/`) with versioned migration support. |
| Orphaned Chunk Cleanup | `Working` | Automated reconciliation clears orphaned FTS5/FAISS rows when documents are deleted. |
| Startup Migration Runner | `Working` | Automatic schema validation on application lifespan startup. |

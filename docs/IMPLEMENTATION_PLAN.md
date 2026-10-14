# Stock-RAG Implementation & Remediation Plan

This document outlines a prioritized, step-by-step implementation plan to address the architectural, security, and functional gaps identified in the project audits, bringing the prototype to a fully capable, reliable, and production-ready state without expanding the current scope.

## Phase 1: Security, Persistence, and Schema Integrity (P0 - P1)
**Goal:** Secure the application, introduce versioned database migrations, and fix critical schema flaws.

### 1.1 Secure the Application Boundary (P0)
- **Action:** Bind the FastAPI `uvicorn` server strictly to `127.0.0.1` by default to prevent exposure on untrusted networks.
- **Action:** Introduce a simple authentication middleware (e.g., Basic Auth or token-based) to protect the API endpoints and the static frontend, ensuring only authorized users can access the system.

### 1.2 Implement Alembic Migrations (P1)
- **Action:** Install and initialize `alembic`.
- **Action:** Remove the inline manual `ALTER TABLE` checks in `app/main.py` (`_initialize_database`).
- **Action:** Generate an initial baseline Alembic migration based on the current `app/db/models.py`.
- **Action:** Create a startup script that automatically runs `alembic upgrade head` on boot.

### 1.3 Fix Database Normalization (P2)
- **Action:** Refactor the `NewsArticle` model. Currently, the `url` is globally unique, but it stores a single `symbol` and `ticker`. Create an association table (Many-to-Many) so a single news article can be linked to multiple tickers.
- **Action:** Update `FundamentalMetric` to include necessary columns for reliable comparison: `units`, `currency`, and `fiscal_period`.

## Phase 2: RAG Pipeline & Background Processing (P1 - P2)
**Goal:** Fix data retrieval bugs, stabilize long-running tasks, and ensure the RAG index stays healthy.

### 2.1 Unify RAG Ticker Suffix Handling (P1)
- **Action:** Modify `app/rag/ingest.py` and `app/analysis/orchestrator.py` (`build_metadata_filter`).
- **Action:** Establish a standard for Indian equities (e.g., `.NS`, `.BO`). Either strip them uniformly at both ingestion and query time, or preserve them uniformly. Ensure `RELIANCE.NS` documents are found when asking about "Reliance".

### 2.2 Migrate Crawling and RAG to Background Jobs (P2)
- **Action:** Remove synchronous waiting for web crawling and document extraction inside the API request cycle.
- **Action:** Introduce a lightweight background task queue (e.g., `asyncio` queues or `arq`) to process heavy documents. 
- **Action:** Update the UI and API to support polling or SSE (Server-Sent Events) to check the processing status (`processing`, `completed`, `failed`) of `DocumentMetadata` records.

### 2.3 RAG Health and Rebuild CLI (P2)
- **Action:** Build a CLI command or an admin endpoint to reconcile the `rag_chunks` FTS5 table with the FAISS `rag_vector_map`.
- **Action:** Add a background job to clear orphaned FTS/FAISS rows when a `DocumentMetadata` is deleted.

## Phase 3: AI Orchestration & Tool Calling (P1 - P3)
**Goal:** Replace brittle keyword routing with deterministic LLM capability and modularize the backend.

### 3.1 Migrate to LLM Tool Calling (P1)
- **Action:** Deprecate the regex-based `classify_intents` function in `orchestrator.py`.
- **Action:** Define explicit JSON schemas (OpenAI/Ollama tool format) for `get_market_quote`, `get_technical_analysis`, `get_news`, and `search_documents`.
- **Action:** Update the local Ollama interaction to use these native tools, allowing the LLM to decide which data source it needs based on semantic understanding of the user's prompt.

### 3.2 Refactor Grounding Validation (P2)
- **Action:** Replace `_unsupported_answer_terms` with an LLM-based Entailment Check or a more lenient semantic similarity check to stop penalizing valid paraphrasing.

### 3.3 Modularize Orchestrator (P3)
- **Action:** Break down the 755-line `app/analysis/orchestrator.py` into distinct services:
  - `intent_router.py` (Handling LLM tool invocation)
  - `evidence_collector.py` (Handling concurrent data fetching)
  - `response_assembler.py` (Handling prompt formatting and validation)

## Phase 4: Frontend Modularity & Diagnostics (P2 - P3)
**Goal:** Improve frontend maintainability and expose critical diagnostics to the user.

### 4.1 Modularize `app.js` (P3)
- **Action:** Break the 1,966-line `static/app.js` into smaller ES modules (e.g., `api.js`, `chat.js`, `chart.js`, `news.js`).
- **Action:** Implement a lightweight state management pattern to prevent DOM manipulation bugs when data updates.

### 4.2 Data Provenance & Diagnostics UI (P2)
- **Action:** Expose data source and freshness tags visually on the Chart and News tabs (e.g., "Quote: 10 mins ago via yfinance", "Stale fallback used").
- **Action:** Provide a toggle to explicitly switch between adjusted and unadjusted closes for the charts.
- **Action:** Surface FAISS and SQLite chunk counts in an "Admin" or "Settings" diagnostic panel.

## Execution Workflow
1. **Setup:** Ensure Husky pre-commits (`pytest`) are active to prevent regressions.
2. **Branching:** Tackle Phase 1 on a `feat/persistence-security` branch.
3. **Testing:** Write corresponding `pytest` cases for RAG filtering and the new Database Migrations before moving to Phase 2.
4. **Validation:** Manually QA the LLM tool calling in Phase 3 against previous ambiguous queries.

---

## Current Status (2026-10-14 Audit)

| Task Item | Priority | Status | Verification Evidence |
|-----------|----------|--------|----------------------|
| Missing requirements (`pydantic-settings`, `alembic`) | P0 | ✅ Completed | Added to `requirements.txt` |
| Max token cap alignment (16384) | P0 | ✅ Completed | Aligned in settings, chat, and service |
| Health route ORM crash fix | P0 | ✅ Completed | Replaced with direct FTS5/metadata counts |
| Per-request LLM sampling parameters | P1 | ✅ Completed | `top_k`, `repeat_penalty`, `seed` in `ChatRequest` & `ChatService` |
| Settings Reset endpoint (`DELETE /api/settings`) | P1 | ✅ Completed | Atomically restores defaults |
| Settings Schema endpoint (`GET /api/settings/schema`) | P1 | ✅ Completed | Exposes metadata & tooltips |
| Greetings fast-path | P1 | ✅ Completed | Bypasses market/RAG retrieval for simple greetings |
| Custom persona length guardrail | P1 | ✅ Completed | Capped at 2000 characters |
| Finnhub timezone-aware datetime | P1 | ✅ Completed | Switched to `timezone.utc` |
| Duplicate `urlparse` cleanup | P2 | ✅ Completed | Removed redundant import |
| Reflection optimization (`inspect.signature`) | P2 | ✅ Completed | Replaced with try-except fallback |
| Regression test suite expansion | P0 | ✅ Completed | **86/86 passed in 10.18s** (zero failures) |

# StockAI Terminal — Changelog

All notable changes to the StockAI Terminal repository are documented in this file.

---

## [Unreleased] - 2026-10-14 — Comprehensive Audit & Production Hardening

### Summary
Comprehensive architectural, reliability, and security improvements following repository-wide audit. Baseline expanded from 74 passing tests to 86 passing tests with zero regressions.

---

### Added

1. **User-Controllable LLM Parameters:**
   - Added `top_k` (range 0–1000), `repeat_penalty` (range 0.0–5.0), and `seed` (reproducibility) to `ChatRequest` schema in `app/api/routes/chat.py` and `ChatService.chat()` in `app/services/chat.py`.
   - Extended `app/api/routes/settings.py` with validation rules for all supported sampling parameters.

2. **Settings Reset & Schema Metadata Endpoints:**
   - Added `DELETE /api/settings` to reset all user settings to default values atomically.
   - Added `GET /api/settings/schema` returning parameter types, labels, min/max ranges, UI groupings (`basic`, `advanced`, `ui`), and descriptive tooltips.

3. **Adaptive Greetings Fast-Path:**
   - Added `GREETING_PATTERN` and `_is_greeting()` in `app/analysis/orchestrator.py`.
   - Pure greetings ("Hi", "Hello", "Hey", "Good morning") bypass market retrieval, RAG, and crawler; responds warmly in 1-2 short sentences without token or latency waste.

4. **Audit Improvement Test Suite (`tests/test_audit_improvements.py`):**
   - 12 comprehensive unit and regression tests covering:
     - Greetings pattern matching and intent classification.
     - Greeting retrieval bypass (asserting exploding mocks are never called).
     - Invalid ticker resolution safety (`resolve_symbol`).
     - Missing document IDs raising clear `ValueError`.
     - Settings schema verification and default reset functionality.
     - Numeric range validation and unknown key rejection in settings.
     - Chat sampling parameters and `custom_persona` 2000-character guardrail.
     - Context boundary isolation for follow-up questions vs. unrelated topics.

---

### Fixed

1. **Health Route Model Import Crash (`app/api/routes/health.py`):**
   - **Root Cause:** Imported non-existent ORM models `RagDocument` and `RagChunk` from `app.db.models`, which caused silent exception handling on health checks.
   - **Fix:** Switched to direct count queries on `DocumentMetadata` and `rag_chunks` FTS5 table with proper `engine` import.

2. **Max Output Tokens Limit Inconsistency:**
   - **Root Cause:** `settings.py` capped `max_output_tokens` at 4096 / 2048, while `chat.py` allowed up to 8192, creating conflicting limits and preventing larger models from utilizing their full context.
   - **Fix:** Aligned upper bound to 16384 across `settings.py`, `chat.py`, and `ChatService.chat()`.

3. **Missing Project Dependencies (`requirements.txt`):**
   - **Root Cause:** `pydantic-settings` (imported by `app/config.py`) and `alembic` (used for database migrations) were omitted from `requirements.txt`.
   - **Fix:** Added `pydantic-settings>=2.2,<3` and `alembic>=1.13,<2`.

4. **Finnhub Naive Datetime Bug (`app/market/providers/finnhub_provider.py`):**
   - **Root Cause:** `get_history()` used naive `datetime.now()` for UNIX epoch calculation, leading to potential timestamp shift across timezones.
   - **Fix:** Replaced with timezone-aware `datetime.now(timezone.utc)`.

5. **Duplicate URLParse Import (`app/web/crawler.py`):**
   - **Root Cause:** Duplicate line `from urllib.parse import urlparse`.
   - **Fix:** Removed redundant import.

6. **Runtime Reflection Overhead (`app/analysis/orchestrator.py`):**
   - **Root Cause:** `inspect.signature(prompt_builder.build)` was executed on every chat request.
   - **Fix:** Replaced reflection with lightweight `try...except TypeError` fallback handling.

7. **Custom Persona Unbounded Length:**
   - **Root Cause:** Chat endpoint accepted arbitrary length for `custom_persona`, opening potential for memory bloat and prompt injection.
   - **Fix:** Added `max_length=2000` validation in Pydantic schema and string slice clamping in `ChatService`.

---

### Verified

- Automated test suite: **86 passed in 10.18s** (all 74 baseline tests + 12 new audit improvement tests).
- Python syntax and imports validated across all modified modules.
- Ollama offline graceful degradation verified (`list_models` returns error payload safely without crashing).
- Settings schema and reset verified with unit tests.
- Context isolation verified (greetings and new queries do not bleed prior stock context).

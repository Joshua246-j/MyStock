# Deep audit: current limitations and gaps

Audit date: 2026-10-10 (Asia/Kolkata)

This audit separates verified capabilities from gaps that remain. The attached acceptance checklist describes desired coverage; it is not evidence that those items are implemented. Verification is based on the code paths, the existing tests, recorded local runtime checks, and the test run listed in `TEST_REPORT.md`.

## Prioritized gaps

| Priority | Area | Current limitation / evidence | Next work needed |
|---|---|---|---|
| High | Market data freshness | The primary quote path uses yfinance, which the app correctly labels unofficial and freshness-unverified. One US quote/history flow and one Indian quote were exercised; broad India history, full provider fallback equivalence, and all fundamentals/periods were not. | Add a provider capability/freshness matrix, validate fallbacks field-by-field, and show retrieval/market timestamps consistently. Use a licensed timestamped provider for any real-time claim. |
| High | Answer grounding | Document numeric fact checks and source lists exist, but arbitrary generated claims are not verified against citations claim by claim. A citation can be listed without proving that every nearby claim follows from it. | Add claim-level citation checks and adversarial/insufficient-evidence evaluation before presenting broad answers as verified. |
| High | ML validity | The only verified ML feature is experimental price-only ridge regression over lagged returns/volatility with a small walk-forward holdout and historical-mean baseline. No repeatable evidence of predictive advantage is established. News sentiment, model versioning, portfolio or broader ML evaluations are absent. | Keep estimates explicitly exploratory; build reproducible out-of-sample evaluation and baselines before adding stronger forecast claims. |
| Medium | Web research coverage and latency | Search uses Google News RSS with an allowlisted publisher filter; results are headline/feed excerpts, not full articles. Direct crawl is restricted to an allowlist, respects robots, blocks redirects, and applies byte/time/rate bounds. A live SEC 10-K was downloaded, indexed to 340 passages, and retrieved by scoped RAG. In this environment the crawl outlasted a 240-second client wait before the isolated record completed. | Move long indexing to a tracked background job with progress/cancellation and benchmark representative sources. Publisher access and robots rules still apply. |
| Medium | News diversity and imagery | Company headlines now require explicit ticker association and old untagged rows are hidden. A live US feed returned nine items; the India filter returned zero. Provider images are optional. Image rights/hotlink availability are not comprehensively audited, and there is no validated sentiment pipeline. | Expand free-source coverage only after verifying terms and ticker association; preserve clear empty states and avoid unvalidated sentiment claims. |
| Medium | RAG formats and quality | PDF/DOCX/TXT/HTML ingestion and hybrid FAISS/FTS retrieval are covered. Scanned PDF OCR requires optional Tesseract, absent in this environment; legacy `.doc` is unsupported. Retrieval quality/recall and general citation precision have no benchmark. | Add OCR setup/verification and retrieval/faithfulness evaluation on a curated dataset. |
| Medium | Chat context | History is persisted and branching is implemented. The service supplies at most 15 recent messages, then prompt construction applies a character budget; older context is dropped rather than summarized. Follow-up topic carryover handles common short forms, not every ambiguous continuation. | Add explicit context controls or safe conversation summaries, with branch-isolation regression coverage. |
| Medium | Web-indexing concurrency | Search reuses already-indexed URLs, but canonical URLs are not protected by a database uniqueness constraint during concurrent crawls. The crawl endpoint waits synchronously for extraction and embedding. | Add a canonical URL key/upsert and move indexing into a tracked job. |
| Medium | Operations and recovery | Market cache and core chat/document/index data persist locally. Concurrent cold quote requests exposed a cache insert race that could return HTTP 500; cache writes now use SQLite upsert, and a 20-request concurrent smoke test returned 20/20 HTTP 200. This was not a load or soak test. Scheduled refresh, full job recovery, and tested backup/restore are still absent. | Add provider single-flight/rate limiting, background-job recovery, and tested backup/restore procedures before unattended use. |
| Medium | UI acceptance | Browser checks covered stock detail/chart views, news filters, compare/watchlist, status details, chat history/new chat, model settings, file attachment, and exit navigation at 390×844 and 1280×720. Not every control, keyboard/accessibility behavior, browser zoom, or all pan/range/error states has been audited. | Continue control-by-control accessibility and responsive checks across supported browsers and devices. |
| High | Model quality and latency | `gemma3:1b` and `qwen2.5:1.5b` both generated answers using the selected SEC filing. Live replies took about 67 seconds (Gemma) and 103 seconds (Qwen) on this machine. The app adds citations and flags when the model does not cite its source, but general claim-to-source entailment is not proven; one Gemma answer mixed product-line details. | Keep answers explicitly unverified unless checked; add per-model faithfulness/latency evaluations and improve local inference throughput. Do not market current generation as fast on this hardware. |
| Low | Provider/legal documentation | The implementation identifies sources and some freshness limits, but the repository does not contain a complete source matrix for licensing, attribution, quota, coverage, image rights, or permitted refresh rates. | Confirm provider terms and document credentials/limits before expanding integrations. |

## Verified working paths

- Local FastAPI app, SQLite persistence, chat history/branching, settings, and document records.
- Installed Ollama generation-model discovery and local generation checks; embedding availability is reported separately.
- PDF/DOCX/TXT/HTML parsing, document-scoped retrieval, metadata filters, and hybrid FTS5/FAISS retrieval, with keyword fallback when embeddings are unavailable.
- Validated OHLCV storage, chart indicators, daily/weekly/monthly technical analysis, and chart context passed to chat.
- Symbol news normalization, date sorting/deduplication, publisher attribution, source links, and HTTPS provider images when supplied.
- Google News RSS search and bounded allowlisted direct crawling, with unit coverage for publisher filtering, robots/security handling, indexing paths, and scoped retrieval.
- Saved conversations, deletion, branching, model/provenance metadata, and short follow-up context.

These verified paths do not remove the limits in the table. In particular, passing unit tests does not prove provider availability, quote freshness, legal entitlement, broad-model quality, or claim-level answer truth.

## Audit defect fixed in this pass

The intent router treated the standalone word “about” as a market-quote request. A document follow-up such as “What about the prior year?” could therefore invoke market data unnecessarily. That trigger was removed, and a regression assertion now checks that the document follow-up uses RAG without requesting a quote.

## Additional fixes verified in this pass

- Corrected Yahoo timestamp handling, required explicit ticker associations for company news, rejected future timestamps, and invalidated old loose-news cache entries.
- Updated chat status wording to distinguish “Ollama connected/model installed” from a tested successful reply.
- Fixed concise response validation and added conservative withholding for unsupported document terms, unsupported entity relationships, and self-contradictory evidence statements.
- Increased chunk size/overlap for new documents to reduce embedding round trips on long filings.
- Changed cache writes to atomic SQLite upsert after the concurrent quote smoke test exposed a same-key write race.

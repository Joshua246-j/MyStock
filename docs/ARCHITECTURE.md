# Architecture

MyStock AI is a local FastAPI application that serves its browser terminal and JSON API from one process. SQLite stores settings, conversations, cache entries, document records, lexical document chunks, and validated historical price bars. External price providers remain upstream sources; market freshness is carried through the API.

```text
Browser terminal
      ↓
FastAPI routes ──→ provider adapters ──→ validation ──→ SQLite/cache
      │
      ├──→ PDF/DOCX/TXT/HTML extraction ──→ chunking ──→ SQLite FTS5 + FAISS vectors
      ├──→ allowlisted web fetch ──→ robots/rate checks ──→ FTS5 + FAISS
      └──→ evidence assembly ──→ Ollama ──→ answer + retrieved citations
```

SQLite stores chunk text/metadata and maps persistent identifiers to the FAISS CPU index. FTS5 and FAISS results are combined; metadata and selected-document constraints are applied before vector scoring. When Ollama embeddings are unavailable, keyword retrieval remains available. The language model generates explanations, while Python and provider/database results supply market values and technical calculations.

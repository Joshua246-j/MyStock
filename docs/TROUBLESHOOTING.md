# Troubleshooting

- **Ollama disconnected or model missing:** start the local Ollama service, then install the configured chat and embedding models. Check `/api/health` and choose an installed generation model in Settings. Slow CPU inference can exceed the configured request timeout.
- **Market data unavailable:** provider coverage and access depend on symbol, network, and rate limits. Retry later; cached historical data may remain available. Quote freshness is not guaranteed by the free yfinance path.
- **Document search only shows keyword mode:** FTS5 remains usable without embeddings. Start Ollama and install the configured embedding model to enable FAISS retrieval; `/api/health` reports the active retrieval mode. The first semantic request may rebuild vectors for older FTS5 chunks.
- **Scanned PDF is rejected:** install Tesseract OCR and its English language data, then retry. PDFs without extractable text are not marked indexed unless OCR produces readable content.

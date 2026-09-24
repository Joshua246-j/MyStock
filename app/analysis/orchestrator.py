"""Concurrent evidence collection and grounded chat generation."""
import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.analysis.data_analysis import analyze_dataset
from app.market.service import market_service
from app.ollama_client import OllamaClient
from app.prompts.system_prompt import RAG_SYSTEM_PROMPT
from app.rag.retriever import retrieve_context

logger = logging.getLogger("stockrag.orchestrator")
ollama_client = OllamaClient()
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)


def classify_intents(message: str, symbol: str | None, settings: dict[str, Any]) -> set[str]:
    """Small, explicit multi-label classifier; no model call needed to route tools."""
    text = message.casefold()
    intents: set[str] = set()
    if symbol and any(term in text for term in ("quote", "price", "stock", "share", "market", "how much", "trading")):
        intents.add("market_quote")
    if symbol and settings.get("automatic_technical_analysis", True) and any(term in text for term in ("technical", "rsi", "macd", "sma", "ema", "moving average", "indicator")):
        intents.add("technical")
    if symbol and settings.get("automatic_fundamental_analysis", True) and any(term in text for term in ("fundamental", "pe ratio", "eps", "revenue", "debt", "cash flow", "margin", "financial")):
        intents.add("fundamental")
    if symbol and settings.get("automatic_news_retrieval", True) and any(term in text for term in ("news", "recent", "today", "happened", "latest")):
        intents.add("news")
    if settings.get("web_research_enabled", True) and URL_RE.search(message):
        intents.add("web_research")
    if any(term in text for term in ("document", "pdf", "uploaded", "report", "according to", "file")):
        intents.add("document_qa")
    # Keep document retrieval available for analytical questions; general chat can still use it.
    if not intents:
        intents.add("general_chat")
    return intents


async def _thread_call(function, *args, timeout: float, **kwargs):
    return await asyncio.wait_for(asyncio.to_thread(function, *args, **kwargs), timeout=timeout)


async def orchestrate_chat(
    message: str,
    symbol: str | None = None,
    dataset_path: str | None = None,
    history: list | None = None,
    model: str | None = None,
    settings: dict[str, Any] | None = None,
):
    from app.db.database import SessionLocal
    from app.db.models import UserSettings

    if settings is None:
        def load_settings():
            with SessionLocal() as db:
                row = db.query(UserSettings).first()
                return row.settings if row and row.settings else {}
        settings = await asyncio.to_thread(load_settings)

    timeout = max(1, min(float(settings.get("request_timeout", 30)), 180))
    selected_model = model or settings.get("ai_model") or ollama_client.model
    intents = classify_intents(message, symbol, settings)
    started = datetime.now(timezone.utc)
    evidence: list[tuple[str, Any]] = []
    failures: list[str] = []

    async def quote_task():
        data = await _thread_call(market_service.get_quote, symbol, timeout=timeout)
        if data.get("success"):
            return "quote", data
        raise RuntimeError(data.get("error", "Quote unavailable"))

    async def technical_task():
        data = await _thread_call(market_service.get_technical_analysis, symbol, timeout=timeout)
        if data.get("success"):
            return "technical", data
        raise RuntimeError(data.get("error", "Technical analysis unavailable"))

    async def fundamental_task():
        data = await _thread_call(market_service.get_financials, symbol, timeout=timeout)
        if data.get("success"):
            return "fundamental", data
        raise RuntimeError(data.get("error", "Fundamentals unavailable"))

    async def news_task():
        news = await _thread_call(market_service.get_news, symbol, timeout=timeout)
        return "news", news

    async def rag_task():
        result = await _thread_call(retrieve_context, message, k=int(settings.get("max_retrieved_documents", 5)), timeout=timeout)
        return "documents", result

    async def web_task():
        urls = URL_RE.findall(message)
        if not urls:
            return "web", {"crawled": 0, "errors": []}
        from app.web.crawler import crawl_url
        results = await asyncio.gather(*(_thread_call(crawl_url, url.rstrip(".,)"), timeout=timeout) for url in urls[:3]), return_exceptions=True)
        ok = sum(1 for item in results if isinstance(item, dict) and item.get("success"))
        errors = [str(item) if isinstance(item, Exception) else item.get("error") for item in results if isinstance(item, Exception) or not item.get("success")]
        return "web", {"crawled": ok, "errors": errors}

    tasks = []
    if "market_quote" in intents:
        tasks.append(quote_task())
    if "technical" in intents:
        tasks.append(technical_task())
    if "fundamental" in intents:
        tasks.append(fundamental_task())
    if "news" in intents:
        tasks.append(news_task())
    # Retrieval is included for every user query, so mixed questions can combine evidence.
    tasks.append(rag_task())
    if "web_research" in intents:
        tasks.append(web_task())
    if dataset_path:
        tasks.append(_thread_call(analyze_dataset, dataset_path, message, timeout=timeout))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for item in results:
        if isinstance(item, Exception):
            failures.append(str(item))
            logger.warning("evidence_source_failed", extra={"reason": str(item)})
            continue
        if isinstance(item, tuple) and len(item) == 2:
            evidence.append(item)
        elif isinstance(item, dict):
            evidence.append(("dataset", item))

    context_sections: list[str] = []
    citations: list[str] = []
    quote_timestamp = None
    market_sources = 0
    web_sources = 0
    data_status = "UNAVAILABLE" if failures else "LIVE"
    for kind, data in evidence:
        if kind == "quote":
            quote_timestamp = data.get("timestamp") or data.get("retrieved_at")
            data_status = data.get("status", "LIVE")
            context_sections.append(f"MARKET QUOTE ({symbol}; provider={data.get('source')}): price={data.get('price')}, change={data.get('change')} ({data.get('change_percent')}%), timestamp={quote_timestamp}.")
            citations.append(f"Market quote — {data.get('source')} ({quote_timestamp})")
            market_sources += 1
        elif kind == "technical":
            context_sections.append(f"TECHNICAL INDICATORS ({symbol}): {data.get('metrics')}")
            citations.append(f"Technical analysis — {symbol} historical prices")
            market_sources += 1
        elif kind == "fundamental":
            context_sections.append(f"FUNDAMENTALS ({symbol}; provider={data.get('source')}): {data.get('metrics')}")
            citations.append(f"Fundamentals — {data.get('source')}")
            market_sources += 1
        elif kind == "news":
            news = data[:5] if isinstance(data, list) else []
            if news:
                context_sections.append("RECENT NEWS:\n" + "\n".join(f"- {n.get('title')} — {n.get('publisher')} ({n.get('published_at')}) {n.get('url')}" for n in news))
                citations.extend(f"News — {n.get('publisher')}: {n.get('title')}" for n in news)
                market_sources += len(news)
        elif kind == "documents":
            if data.get("context"):
                context_sections.append("RETRIEVED DOCUMENT EVIDENCE:\n" + data["context"])
                citations.extend(data.get("sources", []))
        elif kind == "web":
            web_sources += data.get("crawled", 0)
            if data.get("errors"):
                failures.extend(data["errors"])
        elif kind == "dataset" and data.get("success"):
            context_sections.append("UPLOADED DATASET ANALYSIS:\n" + data.get("analysis_text", ""))
            citations.append(f"Uploaded dataset — {dataset_path}")

    unique_citations = list(dict.fromkeys(citations))
    evidence_retrieved = bool(context_sections)
    if not evidence_retrieved:
        context_sections.append("No relevant evidence was retrieved. State clearly that evidence is insufficient and do not invent facts or citations.")
    user_prompt = f"User question: {message}\n\nEvidence:\n" + "\n\n".join(context_sections)
    messages = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]
    messages.extend((history or [])[-12:])
    messages.append({"role": "user", "content": user_prompt})

    try:
        await _thread_call(ollama_client.check_health, min(timeout, 5), timeout=timeout)
        response = await _thread_call(
            ollama_client.chat,
            messages,
            selected_model,
            timeout=timeout,
            temperature=float(settings.get("temperature", 0.2)),
            context_size=int(settings.get("context_size", 4096)),
        )
    except Exception as exc:
        logger.warning("generation_failed", extra={"reason": str(exc), "model": selected_model})
        response = f"AI response unavailable: {exc}. Retrieved evidence is available for retry."

    if response.startswith("Error:"):
        failures.append(response)
    citation_unverified = evidence_retrieved and "## Sources" not in response
    if citation_unverified:
        if unique_citations:
            response += "\n\n## Sources\n" + "\n".join(f"- {source}" for source in unique_citations)
        response += "\n\n*Source verification: the model did not provide a verifiable Sources section; citations above list retrieved evidence, not verified claim-to-source links.*"
    if not unique_citations and "## Sources" in response:
        response += "\n\n*Source verification: no external source was retrieved for this response; verify claims independently.*"

    finished = datetime.now(timezone.utc)
    return {
        "answer": response,
        "structured_analysis": {"intents": sorted(intents), "evidence_types": [kind for kind, _ in evidence], "limitations": failures},
        "citations": unique_citations,
        "sources_unverified": citation_unverified or ("## Sources" in response and not unique_citations),
        "data_status": data_status,
        "data_timestamp": quote_timestamp or finished.isoformat(),
        "model": selected_model,
        "retrieval": {"sources": len(unique_citations), "documents": sum(1 for c in unique_citations if "Page" in c), "web_sources": web_sources, "market_sources": market_sources},
        "request_started_at": started.isoformat(),
    }

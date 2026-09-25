"""Concurrent evidence collection and grounded chat generation."""
import asyncio
import logging
import re
import unicodedata
from pathlib import Path
from functools import partial
from datetime import datetime, timezone
from typing import Any

from app.analysis.data_analysis import analyze_dataset
from app.ollama_client import OllamaClient, OllamaError
from app.market.symbol_resolver import resolve_symbol, INDIAN_COMPANY_ALIASES
from app.analysis.interfaces import IMarketData, IRetriever
from app.analysis.prompt_builder import PromptBuilder

logger = logging.getLogger("stockrag.orchestrator")
ollama_client = OllamaClient()
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
_FACT_STOPWORDS = {"what", "which", "when", "where", "does", "did", "was", "were", "the", "for", "from", "this", "that", "with", "about", "according", "uploaded", "document", "pdf", "tell", "show", "give", "report", "reported"}
_FACT_VALUE_RE = re.compile(r"(?<![A-Za-z0-9])(?:[$₹€£]\s*)?\d[\d,]*(?:\.\d+)?(?:\s*(?:million|billion|crore|lakh|thousand|percent|rupees|INR|USD|%))?", re.IGNORECASE)


def _missing_research_sections(response: str, *, require_sources: bool) -> list[str]:
    required = ["Answer", "Key Facts", "Analysis", "Limitations"]
    if require_sources:
        required.append("Sources")
    return [section for section in required if not re.search(rf"(?im)^##\s+{re.escape(section)}\s*$", response)]


def _citation_matches(source: str, source_section: str) -> bool:
    def normalized(value: str) -> str:
        value = unicodedata.normalize("NFKC", value).casefold().replace("—", "-").replace("–", "-")
        return re.sub(r"[^a-z0-9]+", " ", value).strip()
    expected = normalized(source)
    supplied = normalized(source_section)
    return bool(expected and expected in supplied)


def _document_numeric_fact(query: str, passages: list[dict[str, str]]) -> dict[str, str] | None:
    """Find the best matching source sentence containing a precise numeric fact."""
    query_terms = {term for term in re.findall(r"[a-z0-9]+", query.casefold()) if len(term) > 2 and term not in _FACT_STOPWORDS}
    candidates = []
    for passage in passages:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", passage.get("content", "")):
            values = [match.group(0).strip() for match in _FACT_VALUE_RE.finditer(sentence)]
            if not values:
                continue
            sentence_terms = set(re.findall(r"[a-z0-9]+", sentence.casefold()))
            overlap = query_terms & sentence_terms
            if overlap:
                candidates.append((len(overlap), len(values), {"text": sentence.strip(), "source": passage.get("source", "Source not identified")}))
    return max(candidates, key=lambda item: (item[0], item[1]))[2] if candidates else None


def _missing_fact_values(fact: dict[str, str] | None, response: str) -> list[str]:
    if not fact:
        return []
    missing = []
    for match in _FACT_VALUE_RE.finditer(fact["text"]):
        value = match.group(0).strip()
        number_match = re.search(r"\d[\d,]*(?:\.\d+)?", value)
        if not number_match:
            continue
        number = number_match.group(0).replace(",", "")
        if not re.search(rf"(?<!\d){re.escape(number)}(?!\d)", response.replace(",", "")):
            missing.append(value)
            continue
        unit = value[number_match.end():].strip().casefold()
        if unit and unit not in response.casefold():
            missing.append(value)
            continue
        if value.startswith(("$", "₹", "€", "£")) and not value[0] in response:
            missing.append(value)
    return missing


def _direct_source_answer(fact: dict[str, str]) -> str:
    return (
        "## Answer\n\nThe source passage states: “" + fact["text"] + "”\n\n"
        "## Key Facts\n\n- " + fact["text"] + "\n\n"
        "## Calculations\n\nNo calculation was performed; this is a direct source extract.\n\n"
        "## Analysis\n\nThe retrieved passage contains the requested numeric fact. StockRAG is quoting the source because the language model did not preserve the number reliably.\n\n"
        "## Limitations\n\n- The statement is quoted from the indexed document and has not been independently verified.\n\n"
        "## Sources\n\n- " + fact["source"]
    )


def classify_intents(message: str, symbol: str | None, settings: dict[str, Any]) -> set[str]:
    """Small, explicit multi-label classifier; no model call needed to route tools."""
    text = message.casefold()
    intents: set[str] = set()
    if symbol and any(term in text for term in ("quote", "price", "stock", "share", "market", "how much", "trading", "chart", "return", "performance", "compare", "trend", "today", "latest", "current", "about")):
        intents.add("market_quote")
    if symbol and settings.get("automatic_technical_analysis", True) and any(term in text for term in ("technical", "rsi", "macd", "sma", "ema", "moving average", "indicator", "chart", "return", "performance", "compare", "trend", "volatility", "drawdown")):
        intents.add("technical")
    if symbol and settings.get("automatic_fundamental_analysis", True) and any(term in text for term in ("fundamental", "pe ratio", "eps", "revenue", "debt", "cash flow", "margin", "financial", "about", "company", "valuation", "balance sheet", "earnings")):
        intents.add("fundamental")
    if symbol and settings.get("automatic_news_retrieval", True) and any(term in text for term in ("news", "recent", "today", "happened", "latest")):
        intents.add("news")
    if settings.get("web_research_enabled", True) and URL_RE.search(message):
        intents.add("web_research")
    product_help = bool(re.search(
        r"\b(?:what is stockrag|what does stockrag|how (?:do|can) i (?:use|upload|manage|select|change)|"
        r"how to (?:use|upload|manage|select|change)|how does (?:the )?(?:app|stockrag)|"
        r"where (?:do|can) i (?:upload|select)|how can (?:the )?chat)\b",
        text,
    ))
    if not product_help and any(term in text for term in ("document", "pdf", "uploaded", "report", "according to", "file")):
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
    mode: str | None = None,
    document_ids: list[int] | None = None,
    market_data: IMarketData | None = None,
    retriever: IRetriever | None = None,
    prompt_builder: PromptBuilder | None = None,
):
    from app.db.database import SessionLocal
    from app.db.models import UserSettings
    
    if market_data is None:
        from app.dependencies import market_service
        market_data = market_service
    if retriever is None:
        from app.dependencies import default_retriever
        retriever = default_retriever
    if prompt_builder is None:
        from app.dependencies import prompt_builder as default_pb
        prompt_builder = default_pb

    if settings is None:
        def load_settings():
            with SessionLocal() as db:
                row = db.query(UserSettings).first()
                return row.settings if row and row.settings else {}
        settings = await asyncio.to_thread(load_settings)

    timeout = max(1, min(float(settings.get("request_timeout", 30)), 180))
    if symbol:
        resolution = resolve_symbol(symbol)
        if resolution["valid"]:
            symbol = resolution["resolved_symbol"]
    if not symbol:
        for alias, resolved in sorted(INDIAN_COMPANY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
            if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", message, re.IGNORECASE):
                symbol = resolved
                break
    if not symbol:
        excluded = {"A", "I", "AI", "PDF", "RAG", "RSI", "MACD", "SMA", "EMA", "PE", "EPS", "CEO", "CFO", "GDP", "USA", "UK", "IN"}
        candidates = re.findall(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9.-]{0,9}(?![A-Za-z0-9])", message)
        for candidate in candidates:
            if candidate not in excluded and resolve_symbol(candidate)["valid"]:
                symbol = candidate
                suffix = {"IN": ".NS", "UK": ".L", "CA": ".TO", "AU": ".AX"}.get(settings.get("default_market_exchange"))
                if suffix and "." not in symbol:
                    symbol = f"{symbol}{suffix}"
                break
    selected_model = model or settings.get("ai_model") or ollama_client.model
    intents = classify_intents(message, symbol, settings)
    mode = mode or settings.get("default_chat_mode", "auto")
    if mode == "market" and symbol and not (intents & {"market_quote", "technical", "fundamental", "news"}):
        intents.add("market_quote")
    elif mode == "documents":
        intents.difference_update({"market_quote", "technical", "fundamental", "news"})
    elif mode == "general":
        intents.difference_update({"market_quote", "technical", "fundamental", "news", "web_research"})
    started = datetime.now(timezone.utc)
    evidence: list[tuple[str, Any]] = []
    failures: list[str] = []
    document_passages: list[dict[str, str]] = []

    async def quote_task():
        data = await _thread_call(market_data.get_quote, symbol, timeout=timeout)
        if data.get("success"):
            return "quote", data
        raise RuntimeError(data.get("error", "Quote unavailable"))

    async def technical_task():
        data = await _thread_call(market_data.get_technical_analysis, symbol, timeout=timeout)
        if data.get("success"):
            return "technical", data
        raise RuntimeError(data.get("error", "Technical analysis unavailable"))

    async def fundamental_task():
        data = await _thread_call(market_data.get_financials, symbol, timeout=timeout)
        if data.get("success"):
            return "fundamental", data
        raise RuntimeError(data.get("error", "Fundamentals unavailable"))

    async def news_task():
        news = await _thread_call(market_data.get_news, symbol, timeout=timeout)
        return "news", news

    async def rag_task():
        result = await _thread_call(retriever.retrieve_context, message, k=int(settings.get("max_retrieved_documents", 5)), document_ids=document_ids, timeout=timeout)
        return "documents", result

    async def web_task():
        urls = URL_RE.findall(message)
        if not urls:
            return "web", {"crawled": 0, "errors": []}
        from app.web.crawler import crawl_url
        results = await asyncio.gather(*(_thread_call(partial(crawl_url, url.rstrip(".,)"), timeout=timeout), timeout=timeout) for url in urls[:3]), return_exceptions=True)
        ok = sum(1 for item in results if isinstance(item, dict) and item.get("success"))
        errors = [str(item) if isinstance(item, Exception) else item.get("error") for item in results if isinstance(item, Exception) or not item.get("success")]
        retrieved = await _thread_call(retriever.retrieve_context, message, k=int(settings.get("max_retrieved_documents", 5)), timeout=timeout) if ok else {"context": "", "sources": []}
        return "web", {"crawled": ok, "errors": errors, "context": retrieved.get("context", ""), "sources": retrieved.get("sources", [])}

    tasks = []
    if "market_quote" in intents:
        tasks.append(quote_task())
    if "technical" in intents:
        tasks.append(technical_task())
    if "fundamental" in intents:
        tasks.append(fundamental_task())
    if "news" in intents:
        tasks.append(news_task())
    # Search documents only when asked, or when the user explicitly scoped the
    # conversation to selected documents. Prevent unrelated uploaded files from
    # leaking facts/citations into product help and general questions.
    if "document_qa" in intents or document_ids:
        tasks.append(rag_task())
    if "web_research" in intents:
        tasks.append(web_task())
    if dataset_path:
        tasks.append(_thread_call(analyze_dataset, dataset_path, message, timeout=timeout))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for item in results:
        if isinstance(item, Exception):
            reason = f"Request timed out after {timeout:g} seconds" if isinstance(item, asyncio.TimeoutError) else str(item)
            failures.append(reason)
            logger.warning("evidence_source_failed", extra={"reason": reason})
            continue
        if isinstance(item, tuple) and len(item) == 2:
            evidence.append(item)
        elif isinstance(item, dict):
            evidence.append(("dataset", item))

    context_sections: list[str] = []
    citations: list[str] = []
    retrieval_modes: list[str] = []
    quote_timestamp = None
    market_sources = 0
    web_sources = 0
    data_status = "UNAVAILABLE" if failures else "NOT_REQUESTED"
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
            if data.get("error"):
                failures.append(f"Document retrieval failed: {data['error']}")
            if data.get("retrieval_mode"):
                retrieval_modes.append(data["retrieval_mode"])
            if data.get("degraded"):
                failures.append("Semantic document search is unavailable; keyword search was used instead.")
            if data.get("context"):
                context_sections.append("RETRIEVED DOCUMENT EVIDENCE:\n" + data["context"])
                citations.extend(data.get("sources", []))
                document_passages.extend(data.get("passages", []))
        elif kind == "web":
            web_sources += data.get("crawled", 0)
            if data.get("context"):
                context_sections.append("NEWLY CRAWLED WEB EVIDENCE:\n" + data["context"])
                citations.extend(data.get("sources", []))
            if data.get("errors"):
                failures.extend(data["errors"])
        elif kind == "dataset" and data.get("success"):
            context_sections.append("UPLOADED DATASET ANALYSIS:\n" + data.get("analysis_text", ""))
            citations.append(f"Uploaded dataset — {Path(dataset_path).name}")
        elif kind == "dataset":
            failures.append(f"Dataset analysis failed: {data.get('error', 'unknown dataset error')}")

    unique_citations = list(dict.fromkeys(citations))
    evidence_retrieved = bool(context_sections)

    detail_instruction = {"concise": "Keep the response concise.", "balanced": "Use a balanced level of detail.", "detailed": "Explain reasoning and evidence in detail."}.get(settings.get("response_detail", "balanced"), "Use a balanced level of detail.")
    messages = prompt_builder.build(message, history, context_sections, detail_instruction)

    try:
        healthy = await asyncio.wait_for(ollama_client.check_health(min(timeout, 5)), timeout=timeout)
        if not healthy:
            raise OllamaError("Local AI is unavailable. Start Ollama, then retry your message.", code="ollama_disconnected")
        response = await asyncio.wait_for(
            ollama_client.chat(
                messages,
                selected_model,
                timeout=timeout,
                temperature=float(settings.get("temperature", 0.2)),
                context_size=int(settings.get("context_size", 4096)),
                max_output_tokens=int(settings.get("max_output_tokens", 256)),
            ),
            timeout=timeout
        )
    except asyncio.TimeoutError as exc:
        logger.warning("generation_failed", extra={"reason": "request timeout", "model": selected_model})
        raise OllamaError(f"Local AI did not respond within {timeout:g} seconds. Retry or choose a smaller model.", code="ollama_timeout", status_code=504) from exc
    except OllamaError as exc:
        logger.warning("generation_failed", extra={"reason": str(exc), "model": selected_model, "error_code": exc.code})
        raise

    numeric_validation = "not_applicable"
    numeric_fallback = False

    format_required = bool(evidence_retrieved or intents & {"market_quote", "technical", "fundamental", "news", "document_qa", "web_research"} or dataset_path)
    missing_sections = _missing_research_sections(response, require_sources=bool(unique_citations)) if format_required else []
    format_repair_error = None

    if response.startswith("Error:"):
        failures.append(response)
    response_sources = response.split("## Sources", 1)[1] if "## Sources" in response else ""
    model_cited_retrieved_source = any(_citation_matches(source, response_sources) for source in unique_citations)
    citation_unverified = evidence_retrieved and (not response_sources or bool(unique_citations) and not model_cited_retrieved_source)
    if citation_unverified:
        if "## Sources" in response:
            response = response.split("## Sources", 1)[0].rstrip()
        if unique_citations:
            response += "\n\n## Sources\n" + "\n".join(f"- {source}" for source in unique_citations)
        response += "\n\n*Source verification: the model did not provide a verifiable Sources section; citations above list retrieved evidence, not verified claim-to-source links.*"
    if not unique_citations and "## Sources" in response:
        response += "\n\n*Source verification: no external source was retrieved for this response; verify claims independently.*"

    missing_sections = _missing_research_sections(response, require_sources=bool(unique_citations)) if format_required else []
    format_unverified = bool(missing_sections)
    if format_unverified:
        response += "\n\n*Format check: this answer did not satisfy the required research sections after one repair attempt. Review it as an unstructured response.*"

    finished = datetime.now(timezone.utc)
    return {
        "answer": response,
        "structured_analysis": {"intents": sorted(intents), "evidence_types": [kind for kind, _ in evidence], "limitations": failures},
        "citations": unique_citations,
        "sources_unverified": citation_unverified or ("## Sources" in response and not unique_citations),
        "format_unverified": format_unverified,
        "numeric_validation": numeric_validation,
        "answer_method": "extractive_source_fallback" if numeric_fallback else "model_generated",
        "data_status": data_status,
        "data_timestamp": quote_timestamp or finished.isoformat(),
        "model": selected_model,
        "retrieval": {"sources": len(unique_citations), "documents": sum(1 for c in unique_citations if "Page" in c), "web_sources": web_sources, "market_sources": market_sources, "document_modes": list(dict.fromkeys(retrieval_modes))},
        "request_started_at": started.isoformat(),
    }

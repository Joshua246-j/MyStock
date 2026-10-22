"""Concurrent evidence collection and grounded chat generation."""
import asyncio
import logging
import re
import unicodedata
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from app.analysis.data_analysis import analyze_dataset
from app.analysis.capabilities import is_capability_query, get_capability_context
from app.ollama_client import OllamaClient, OllamaError
from app.market.symbol_resolver import resolve_symbol, INDIAN_COMPANY_ALIASES
from app.analysis.interfaces import IMarketData, IRetriever
from app.analysis.prompt_builder import PromptBuilder

logger = logging.getLogger("stockrag.orchestrator")
ollama_client = OllamaClient()
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
_FACT_STOPWORDS = {"what", "which", "when", "where", "does", "did", "was", "were", "the", "for", "from", "this", "that", "with", "about", "according", "uploaded", "document", "pdf", "tell", "show", "give", "report", "reported"}
_FACT_VALUE_RE = re.compile(r"(?<![A-Za-z0-9])(?:[$₹€£]\s*)?\d[\d,]*(?:\.\d+)?(?:\s*(?:million|billion|crore|lakh|thousand|percent|rupees|INR|USD|%))?", re.IGNORECASE)
_NUMERIC_METRIC_GROUPS = (
    {"revenue", "sales", "turnover"},
    {"income", "profit", "earnings"},
    {"eps"},
    {"debt", "borrowings"},
    {"cash"},
    {"assets"},
    {"liabilities"},
    {"margin", "margins"},
    {"dividend", "dividends"},
    {"price"},
    {"pe"},
    {"roa"},
    {"roe"},
    {"growth"},
)


def _missing_research_sections(response: str, *, require_sources: bool, detail: str = "balanced") -> list[str]:
    required = []
    if detail == "concise":
        if require_sources and not re.search(r"(?im)^##\s*Sources", response):
            required.append("Sources")
        return required
    if not re.search(r"(?im)^##\s*Key Facts", response):
        required.append("Key Facts")
    if not re.search(r"(?im)^##\s*Analysis", response):
        required.append("Analysis")
    if not re.search(r"(?im)^##\s*Limitations", response):
        required.append("Limitations")
    if require_sources and not re.search(r"(?im)^##\s*Sources", response):
        required.append("Sources")
    return required


_GROUNDING_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "to", "of", "in", "on", "at", "by", "for", "from", "with", "as", "is", "are", "was", "were", "be", "been", "being", "it", "its", "this", "that", "these", "those", "they", "their", "we", "you", "your", "i", "he", "she", "who", "what", "which", "when", "where", "why", "how", "can", "could", "would", "should", "may", "might", "will", "do", "does", "did", "has", "have", "had", "not", "no", "yes", "also", "only", "both", "each", "more", "most", "some", "many", "few", "two", "three", "one", "first", "second", "last", "new", "old", "key", "fact", "facts", "answer", "analysis", "limitation", "limitations", "source", "sources", "according", "retrieved", "evidence", "document", "filing", "report", "reported", "states", "state", "says", "said", "shows", "show", "indicates", "mentioned", "mention", "identify", "identified", "provide", "provides", "provided", "include", "includes", "including", "listed", "named", "category", "categories", "risk", "risks", "company", "companies", "fiscal", "year", "years", "form", "brief", "cite", "cited", "passage", "passages", "selected", "explicitly", "specifically", "specific", "relevant", "available", "present", "contained", "contains", "contain", "described", "describes", "discussed", "noted", "notes", "financial", "information", "data", "value", "values", "as", "an", "such", "into", "about", "over", "under", "after", "before", "because", "while", "however", "there", "here", "are", "were", "been", "being", "based", "on", "retrieval", "untrusted", "summary", "summaries", "product", "products", "services", "offering", "offers", "focus"
}


def _unsupported_answer_terms(response: str, query: str, passages: list[dict[str, str]]) -> list[str]:
    """Return novel factual terms in the answer's first section absent from its sources.

    This intentionally errs on the side of withholding a questionable answer.
    It is a lexical safety check, not a claim-entailment model.
    """
    answer_match = re.search(r"(?ims)^##\s+Answer(?:\s+|\s*$)(.*?)(?=^##\s+|\Z)", response)
    answer = answer_match.group(1) if answer_match else re.split(r"(?im)^##\s+", response, maxsplit=1)[0]
    query_terms = set(re.findall(r"[a-z0-9]+", query.casefold()))
    source_text = " ".join(passage.get("content", "") for passage in passages)
    source_terms = set(re.findall(r"[a-z0-9]+", source_text.casefold()))
    unmatched: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", answer):
        terms = {
            term for term in re.findall(r"[a-z0-9]+", sentence.casefold())
            if len(term) > 2 and term not in _GROUNDING_STOPWORDS and term not in query_terms
        }
        novel = terms - source_terms
        # A single paraphrase may be harmless; multiple unsupported content
        # words in the short direct answer indicate it may be guessing.
        if len(novel) >= 1 and len(novel) / max(1, len(terms)) >= 0.1:
            unmatched.extend(sorted(novel))
    return list(dict.fromkeys(unmatched))


def _answer_claims_evidence_is_missing(response: str) -> bool:
    """Catch self-contradictory answers that assert a fact, then deny its evidence."""
    patterns = (
        r"\b(?:the\s+)?(?:retrieved\s+)?(?:evidence|passages?|excerpt|source|document|text)\s+(?:does not|doesn't|do not|don't|did not|didn't|is not|isn't|was not|wasn't)\s+(?:explicitly\s+)?(?:provide|contain|mention|support|state|include|show|identify)",
        r"\bno\s+(?:relevant\s+)?evidence\s+(?:was|is)\s+(?:found|provided|available|retrieved)",
        r"\b(?:insufficient|not enough)\s+evidence\b",
        r"\bunable to verify\b",
    )
    return any(re.search(pattern, response, re.IGNORECASE) for pattern in patterns)


def _unsupported_entity_relations(response: str, query: str, passages: list[dict[str, str]]) -> list[str]:
    """Avoid joining named entities that occur only in separate source passages."""
    body = re.search(r"(?ims)^##\s+Answer(?:\s+|\s*$)(.*?)(?=^##\s+|\Z)", response)
    answer = body.group(1) if body else re.split(r"(?im)^##\s+", response, maxsplit=1)[0]

    def named_tokens(text: str):
        for match in re.finditer(r"\b[A-Za-z][A-Za-z0-9.-]*\b", text):
            token = match.group(0)
            is_name = token[0].isupper() or any(char.isupper() for char in token[1:])
            if is_name and token.casefold() not in _GROUNDING_STOPWORDS and not re.search(r"\d", token):
                yield match.start(), token.casefold()

    query_names = {name for _, name in named_tokens(query)}
    query_names -= {"sec", "form", "pdf", "fy", "usd", "inr", "llm", "rag"}
    source_passages = [set(re.findall(r"[a-z0-9]+", passage.get("content", "").casefold())) for passage in passages]
    unsupported = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", answer):
        answer_names = list(named_tokens(sentence))
        for position, name in answer_names:
            if name in query_names or name not in set().union(*source_passages):
                continue
            preceding_entities = [entity for entity_pos, entity in answer_names if entity_pos < position and entity in query_names]
            if not preceding_entities:
                continue
            nearest_entity = preceding_entities[-1]
            if not any(nearest_entity in passage and name in passage for passage in source_passages):
                unsupported.append(name)
    return list(dict.fromkeys(unsupported))


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
    requested_metrics = [group for group in _NUMERIC_METRIC_GROUPS if query_terms & group]
    candidates = []
    for passage in passages:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", passage.get("content", "")):
            values = [match.group(0).strip() for match in _FACT_VALUE_RE.finditer(sentence)]
            if not values:
                continue
            sentence_terms = set(re.findall(r"[a-z0-9]+", sentence.casefold()))
            if requested_metrics and not all(sentence_terms & group for group in requested_metrics):
                continue
            overlap = query_terms & sentence_terms
            if overlap:
                candidates.append((len(overlap), len(values), {"text": sentence.strip(), "source": passage.get("source", "Source not identified")}))
    return max(candidates, key=lambda item: (item[0], item[1]))[2] if candidates else None


def _is_numeric_document_question(query: str) -> bool:
    asks_for_value = bool(re.search(r"\b(?:what|how much|how many|state|give|report(?:ed)?)\b", query.casefold()))
    metric = bool(re.search(r"\b(?:revenue|sales|income|profit|eps|earnings|debt|cash|assets|liabilities|margin|dividend|price|p/?e|roa|roe|growth)\b", query.casefold()))
    return asks_for_value and metric


def _is_model_identity_question(query: str) -> bool:
    asks_model = bool(re.search(r"\b(?:model|ollama|llm)\b", query, re.I))
    asks_identity = bool(re.search(r"\b(?:name|id|active|configured|selected|running|using|used|available)\b", query, re.I))
    asks_about_assistant = bool(re.search(r"\b(?:you|your|this reply|this chat|configured for)\b", query, re.I))
    return asks_model and (asks_identity or asks_about_assistant)


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


def _contains_any_phrase(text: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) for term in terms)


GREETING_PATTERN = re.compile(
    r"^(?:hi|hello|hey|hiya|howdy|good\s+(?:morning|afternoon|evening|day)|greetings|what'?s\s+up|sup|hola|namaste)(?:\s+(?:there|all|everyone|bot|assistant|mystock|stockrag|ai))?[!?. ]*$",
    re.IGNORECASE,
)


def _is_greeting(text: str) -> bool:
    return bool(GREETING_PATTERN.match(text.strip()))


def classify_intents(message: str, symbol: str | None, settings: dict[str, Any]) -> set[str]:
    """Small, explicit multi-label classifier; no model call needed to route tools."""
    text = message.casefold().strip()
    if _is_greeting(text):
        return {"general_chat"}
    intents: set[str] = set()
    if symbol and _contains_any_phrase(text, ("quote", "price", "stock", "share", "market", "how much", "trading", "chart", "return", "performance", "compare", "trend", "today", "latest", "current")):
        intents.add("market_quote")
    if symbol and _contains_any_phrase(text, ("forecast", "predict", "prediction", "price target", "projection", "future price", "price outlook", "next week", "next month", "expected return", "will it rise", "will it drop", "will it go up", "will it go down")):
        intents.add("forecast")
    if symbol and settings.get("automatic_technical_analysis", True) and _contains_any_phrase(text, ("technical", "rsi", "macd", "sma", "ema", "moving average", "bollinger", "atr", "indicator", "chart", "candlestick", "candle", "return", "performance", "compare", "trend", "volatility", "drawdown")):
        intents.add("technical")
    document_context = bool(re.search(r"\b(?:according to|in (?:the |this |my )?(?:uploaded )?(?:document|pdf|report|filing|10\s*[- ]?k|10\s*[- ]?q)|uploaded (?:document|pdf|report)|filings?|10\s*[- ]?k|10\s*[- ]?q|annual report|quarterly report|prospectus)\b", text))
    explicit_structured_request = any(term in text for term in ("fundamental analysis", "pe ratio", "p/e", "price to book", "market cap", "valuation", "current financials"))
    if symbol and settings.get("automatic_fundamental_analysis", True) and _contains_any_phrase(text, ("fundamental", "pe ratio", "eps", "revenue", "debt", "cash flow", "margin", "financial", "about", "company", "valuation", "balance sheet", "earnings")) and (not document_context or explicit_structured_request):
        intents.add("fundamental")
    if symbol and settings.get("automatic_news_retrieval", True) and _contains_any_phrase(text, ("news", "recent", "today", "happened", "latest")):
        intents.add("news")
    explicit_web_request = bool(URL_RE.search(message)) or bool(re.search(
        r"\b(?:web|internet|online|search|look\s*up|browse|crawl|crawler|site|sites|website|websites|source|sources|reddit|google|research|find\s*out|articles?|blogs?|reviews?|discussions?)\b", text,
    ))
    news_research_request = bool(re.search(
        r"\b(?:news|what happened|recent events|latest events|company announcement|press release)\b", text,
    ))
    web_lookup = explicit_web_request or (news_research_request and not document_context)
    if (settings.get("web_research_enabled", True) and web_lookup) or "reddit" in text or "sources" in text or "sites" in text:
        intents.add("web_research")
    product_help = bool(re.search(
        r"\b(?:what is stockrag|what does stockrag|what is mystock|what does mystock|how (?:do|can) i (?:use|upload|manage|select|change)|"
        r"how to (?:use|upload|manage|select|change)|how does (?:the )?(?:app|stockrag|mystock)|"
        r"where (?:do|can) i (?:upload|select)|how can (?:the )?chat)\b",
        text,
    )) or is_capability_query(text)
    if product_help:
        intents.add("general_chat")
    if not product_help and (document_context or any(term in text for term in ("document", "pdf", "uploaded", "report", "according to", "file"))):
        intents.add("document_qa")
    # Keep document retrieval available for analytical questions; general chat can still use it.
    if not intents:
        intents.add("general_chat")
    return intents


def build_metadata_filter(message: str, symbol: str | None) -> dict[str, Any]:
    """Extract only explicit, supportable document constraints from a query."""
    text = message.casefold()
    filters: dict[str, Any] = {}
    if symbol:
        ticker = symbol
        if ticker.endswith((".NS", ".BO")):
            ticker = ticker.rsplit(".", 1)[0]
        filters["ticker"] = ticker
    if re.search(r"\b10\s*[- ]?k\b", text):
        filters["document_type"] = "10-K"
    elif re.search(r"\b10\s*[- ]?q\b", text):
        filters["document_type"] = "10-Q"
    elif "annual report" in text:
        filters["document_type"] = "annual report"
    elif any(term in text for term in ("earnings release", "quarterly report")):
        filters["document_type"] = "quarterly report"
    if re.search(r"\bsec(?:\s+filing)?\b|\bsec\.gov\b", text):
        filters["source_type"] = {"$in": ["sec", "sec_filing", "official_filing"]}
    return filters


def _followup_context(message: str, history: list[dict[str, Any]] | None) -> str:
    """Carry the prior user topic into short follow-ups for tool routing and RAG."""
    if not history:
        return ""
    text = " ".join(message.casefold().split())
    followup = bool(re.match(
        r"^(?:and\b|what about\b|how about\b|why\b|tell me more\b|more\b|"
        r"what does (?:it|that|this)\b|how does (?:it|that|this)\b|"
        r"does (?:it|that|this)\b|is (?:it|that|this)\b|are (?:they|those|these)\b|"
        r"explain (?:it|that|this)\b|can you explain (?:it|that|this)\b)",
        text,
    ))
    if not followup or len(text.split()) > 24:
        return ""
    prior = next((
        str(item.get("content", "")).strip()
        for item in reversed(history)
        if item.get("role") == "user" and str(item.get("content", "")).strip()
    ), "")
    return prior[:1200]


def _trim_prompt_history(history: list[dict[str, Any]] | None, context_size: int) -> list[dict[str, str]]:
    """Keep the newest complete turns within a bounded character budget."""
    if not history:
        return []
    remaining = max(2000, min(10000, int(context_size) * 2))
    kept = []
    for item in reversed(history):
        role = item.get("role")
        content = str(item.get("content", ""))
        if role not in {"user", "assistant"} or not content:
            continue
        if len(content) > remaining:
            if kept:
                break
            content = content[-remaining:]
        kept.append({"role": role, "content": content})
        remaining -= len(content)
        if remaining <= 0:
            break
    return list(reversed(kept))


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
    on_token=None,
    chart_period: str | None = None,
    chart_interval: str | None = None,
    chart_mode: str | None = None,
    chart_view: str | None = None,
    market_data: IMarketData | None = None,
    retriever: IRetriever | None = None,
    prompt_builder: PromptBuilder | None = None,
    web_crawl: bool | None = None,
    user_memories: list[dict[str, Any]] | None = None,
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

    timeout = max(1, min(float(settings.get("request_timeout", 60)), 180))
    chart_period = chart_period if chart_period in {"1mo", "3mo", "6mo", "1y", "2y", "5y"} else "6mo"
    chart_interval = chart_interval if chart_interval in {"1d", "1wk", "1mo"} else "1d"
    chart_mode = chart_mode if chart_mode in {"line", "candlestick"} else "line"
    chart_view = chart_view if chart_view in {"price", "volume", "trend", "bollinger", "rsi", "macd", "atr", "performance"} else "price"
    excluded = {
        "A", "I", "K", "Q", "AI", "PDF", "RAG", "RSI", "MACD", "SMA", "EMA", "PE", "EPS",
        "CEO", "CFO", "CTO", "COO", "CIO", "GDP", "CAGR", "ROI", "DCA", "ROE", "ROA", "EBIT",
        "EBITDA", "ESG", "SEC", "GAAP", "ETF", "IPO", "NYSE", "NASDAQ", "USD", "EUR", "INR",
        "USA", "UK", "IN", "QWEN", "GEMMA", "LLAMA", "NOMIC", "MISTRAL", "DEEPSEEK",
        "NAV", "WACC", "DCF", "LBO", "YTD", "QOQ", "YOY", "IRR", "NPV", "APR", "APY",
        "ATH", "ATL", "VWAP", "OBV", "ADX", "CCI", "MFI", "BETA", "ALPHA", "SHARPE",
        "CALL", "PUT", "FED", "FOMC", "CPI", "PPI", "PCE", "DJIA", "SPX", "NDX", "RUT",
        "VIX", "CBOE", "CME", "OTC", "FINRA", "SIP", "FPO", "OFS", "NFO", "SENSEX",
        "NIFTY", "BANKNIFTY", "MIDCAP", "WHAT", "HOW", "WHY", "WHEN", "WHERE", "WHO",
        "WHICH", "CAN", "COULD", "WOULD", "SHOULD", "WILL", "DO", "DOES", "DID", "DONE",
        "IS", "ARE", "WAS", "WERE", "BE", "BEEN", "HAVE", "HAS", "HAD", "THE", "THIS",
        "THAT", "THESE", "THOSE", "FOR", "FROM", "WITH", "ABOUT", "AND", "BUT", "NOT",
        "ALL", "ANY", "NEW", "TOP", "RUN", "GET", "SET", "USE", "TELL", "GIVE", "SHOW",
        "WRITE", "EXPLAIN", "LIST", "HELP", "CODE", "CHAT", "BOT", "MODEL", "USER",
        "STOCK", "SHARE", "PRICE", "MARKET", "TRADE", "BUY", "SELL", "HOLD"
    }
    candidates = re.findall(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9.-]{0,9}(?![A-Za-z0-9])", message)
    explicit_symbols = []
    for candidate in candidates:
        if candidate in excluded or re.fullmatch(r"(?:FY)?\d{2,4}", candidate) or re.match(r"^(?:QWEN|GEMMA|LLAMA|NOMIC|MISTRAL|DEEPSEEK)\d", candidate):
            continue
        resolution = resolve_symbol(candidate)
        if resolution["valid"]:
            explicit_symbols.append(resolution["resolved_symbol"])
    explicit_symbols = list(dict.fromkeys(explicit_symbols))
    if explicit_symbols:
        # An explicit ticker in the prompt takes precedence over the chart's
        # current ticker; otherwise chat can silently answer for the wrong stock.
        symbol = explicit_symbols[0]
    elif symbol:
        resolution = resolve_symbol(symbol)
        if resolution["valid"]:
            symbol = resolution["resolved_symbol"]
    if not symbol:
        for alias, resolved in sorted(INDIAN_COMPANY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
            if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", message, re.IGNORECASE):
                symbol = resolved
                break
    if not symbol and history:
        for item in reversed(history[-6:]):
            hist_content = str(item.get("content", ""))
            for cand in re.findall(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9.-]{0,9}(?![A-Za-z0-9])", hist_content):
                if cand not in excluded and not re.fullmatch(r"(?:FY)?\d{2,4}", cand) and not re.match(r"^(?:QWEN|GEMMA|LLAMA|NOMIC|MISTRAL|DEEPSEEK)\d", cand):
                    res = resolve_symbol(cand)
                    if res["valid"]:
                        symbol = res["resolved_symbol"]
                        break
            if symbol:
                break
            for alias, res_sym in sorted(INDIAN_COMPANY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
                if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", hist_content, re.IGNORECASE):
                    symbol = res_sym
                    break
            if symbol:
                break
    previous_user_message = _followup_context(message, history)
    retrieval_query = f"{previous_user_message}\nFollow-up: {message}" if previous_user_message else message
    selected_model = model or settings.get("ai_model") or ollama_client.model
    is_greeting = _is_greeting(message)
    intents = {"general_chat"} if is_greeting else classify_intents(retrieval_query, symbol, settings)
    if not is_greeting and (symbol and settings.get("automatic_technical_analysis", True)
            and chart_view in {"trend", "bollinger", "rsi", "macd", "atr", "performance"}
            and re.search(r"\b(?:this|that|these|it|explain|analy[sz]e|show|mean)\b", message.casefold())):
        intents.add("technical")
    if document_ids and not is_greeting:
        # An explicit document selection is a retrieval instruction even when
        # the prompt does not repeat words such as “PDF” or “report”.
        intents.add("document_qa")
    metadata_filter = build_metadata_filter(retrieval_query, symbol) if not is_greeting else {}
    mode = mode or settings.get("default_chat_mode", "auto")
    if not is_greeting:
        if mode == "market" and symbol and not (intents & {"market_quote", "technical", "fundamental", "news"}):
            intents.add("market_quote")
        elif mode == "documents":
            intents.difference_update({"market_quote", "technical", "fundamental", "news"})
        elif mode == "general":
            has_url = bool(URL_RE.findall(message))
            if has_url or web_crawl:
                intents.add("web_research")
            if document_ids:
                intents.add("document_qa")
            intents.difference_update({"market_quote", "technical", "fundamental", "news"})
            if not document_ids and not has_url and not web_crawl and "web_research" not in intents and "document_qa" not in intents:
                intents.clear()
        else:
            if web_crawl:
                intents.add("web_research")
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
        data = await _thread_call(market_data.get_technical_analysis, symbol, period=chart_period, interval=chart_interval, timeout=timeout)
        if data.get("success"):
            return "technical", data
        raise RuntimeError(data.get("error", "Technical analysis unavailable"))

    async def fundamental_task():
        data = await _thread_call(market_data.get_financials, symbol, timeout=timeout)
        if data.get("success"):
            return "fundamental", data
        raise RuntimeError(data.get("error", "Fundamentals unavailable"))

    async def forecast_task():
        from app.forecasting.service import ForecastingService
        h = 5
        if re.search(r"\b(?:tomorrow|1\s*[- ]?day|next\s+session|next\s+day)\b", message, re.IGNORECASE):
            h = 1
        elif re.search(r"\b(?:month|20\s*[- ]?days?|4\s*weeks?)\b", message, re.IGNORECASE):
            h = 20
        svc = ForecastingService()
        data = await _thread_call(svc.forecast, symbol, horizon=h, model_name="auto", confidence=0.80)
        if data.get("success"):
            return "forecast", data
        raise RuntimeError(data.get("error", "Forecast unavailable"))

    async def news_task():
        news = await _thread_call(market_data.get_news, symbol, timeout=timeout)
        return "news", news

    async def rag_task():
        result = await _thread_call(retriever.retrieve_context, retrieval_query, k=int(settings.get("max_retrieved_documents", 5)), document_ids=document_ids, metadata_filter=metadata_filter or None, timeout=timeout)
        return "documents", result

    async def web_task():
        from app.web.crawler import crawl_url, search_web
        from app.db.models import DocumentMetadata
        explicit_urls = URL_RE.findall(message) or (URL_RE.findall(previous_user_message) if previous_user_message else [])
        urls = list(dict.fromkeys(url.rstrip(".,)\"'") for url in explicit_urls))
        search_errors = []
        search_results = []
        if not urls:
            try:
                search_results = await _thread_call(search_web, retrieval_query, 5, min(timeout, 10), timeout=min(timeout, 12))
                if not urls:
                    if not search_results:
                        search_errors.append("Web search returned no results from the configured financial publisher allowlist.")
            except Exception as exc:
                search_errors.append(f"Web search unavailable: {exc}")
        hints = {"ticker": symbol.rsplit(".", 1)[0] if symbol and symbol.endswith((".NS", ".BO")) else symbol} if symbol else {}

        def existing_web_document(db, url: str):
            return (db.query(DocumentMetadata)
                    .filter(
                        DocumentMetadata.document_type == "web",
                        DocumentMetadata.status == "completed",
                        DocumentMetadata.metadata_json["source_url"].as_string() == url,
                    )
                    .order_by(DocumentMetadata.id.desc())
                    .first())

        def index_search_result(result: dict) -> dict:
            from app.db.database import SessionLocal
            from app.rag.lexical_store import index_chunks_batch_with_ids
            title = result["title"]
            publisher = result["publisher"]
            evidence_text = (
                f"Search result title: {title}\nPublisher: {publisher}\n"
                f"Published: {result.get('published_at') or 'date not provided'}\n"
                f"Search result excerpt: {result.get('snippet') or 'No excerpt was provided; only the title and publication metadata were returned.'}\n"
                "This record is search-feed metadata, not the full article text."
            )
            metadata = {
                **hints, "source": f"{publisher} — Google News search excerpt", "title": title,
                "filename": title, "url": result["url"], "source_url": result["url"],
                "publisher_url": result["publisher_url"], "publisher": publisher,
                "document_type": "web", "source_type": "web", "excerpt_scope": "search_result_excerpt",
                "index_backend": "keyword_search", "published_at": result.get("published_at"),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }
            with SessionLocal() as db:
                existing = existing_web_document(db, result["url"])
                if existing:
                    return {"success": True, "document_id": existing.id, "title": title, "url": result["url"], "reused": True}
                record = DocumentMetadata(filename=title, document_type="web", status="processing", metadata_json=metadata)
                db.add(record)
                db.commit()
                db.refresh(record)
                document_id = record.id
            metadata["document_id"] = document_id
            try:
                stored = bool(index_chunks_batch_with_ids([evidence_text], [metadata]))
            except Exception:
                stored = False
                logger.exception("web_search_result_index_failed", extra={"document_id": document_id})
            with SessionLocal() as db:
                record = db.query(DocumentMetadata).filter(DocumentMetadata.id == document_id).first()
                if record:
                    record.status = "completed" if stored else "failed"
                    record.metadata_json = metadata | ({"index_status": "indexed search-result excerpt"} if stored else {"index_error": "Indexing failed"})
                    db.commit()
            return {"success": bool(stored), "document_id": document_id, "title": title, "url": result["url"], "error": None if stored else "Search result could not be added to retrieval."}

        def crawl_and_register(url: str) -> dict:
            from app.db.database import SessionLocal
            with SessionLocal() as db:
                existing = existing_web_document(db, url)
                if existing:
                    return {"success": True, "document_id": existing.id, "title": existing.filename or url, "url": url, "reused": True}
                record = DocumentMetadata(filename=url, document_type="web", status="processing", metadata_json={"source_type": "web", "source_url": url, "title": url, **hints})
                db.add(record)
                db.commit()
                db.refresh(record)
                document_id = record.id
            result = crawl_url(url, timeout=timeout, document_id=document_id, metadata_hints=hints)
            with SessionLocal() as db:
                record = db.query(DocumentMetadata).filter(DocumentMetadata.id == document_id).first()
                if record:
                    record.status = "completed" if result.get("success") else "failed"
                    if result.get("success"):
                        record.filename = result.get("title") or url
                        record.metadata_json = result.get("metadata") or {}
                    else:
                        record.metadata_json = {"source_type": "web", "source_url": url, "title": url, "error": result.get("error")}
                    db.commit()
            return {**result, "document_id": document_id}

        if search_results:
            results = await asyncio.gather(*(_thread_call(index_search_result, result, timeout=timeout) for result in search_results), return_exceptions=True)
            direct_lines = []
            direct_sources = []
            for item in search_results:
                t = item.get("title", "")
                pub = item.get("publisher", "")
                dt = item.get("published_at", "")
                snip = item.get("snippet", "")
                direct_sources.append(f"{pub}: {t}" if pub else t)
                desc = f"• **{t}** — {pub}" + (f" ({dt})" if dt else "")
                if snip and snip != t:
                    desc += f"\n  Excerpt: {snip}"
                direct_lines.append(desc)
            direct_context = "\n".join(direct_lines)
        else:
            results = await asyncio.gather(*(_thread_call(crawl_and_register, url, timeout=timeout) for url in urls[:3]), return_exceptions=True)
            direct_context = ""
        successful = [item for item in results if isinstance(item, dict) and item.get("success")]
        errors = search_errors + [str(item) if isinstance(item, Exception) else item.get("error") for item in results if isinstance(item, Exception) or not item.get("success")]
        crawled_ids = [item["document_id"] for item in successful]
        retrieved = await _thread_call(retriever.retrieve_context, retrieval_query, k=int(settings.get("max_retrieved_documents", 5)), document_ids=crawled_ids, timeout=timeout) if crawled_ids else {"context": "", "sources": []}
        final_context = retrieved.get("context", "")
        if direct_context:
            final_context = direct_context if not final_context else f"{direct_context}\n\n{final_context}"

        from urllib.parse import urlparse
        url_structured = [
            {
                "title": (item.get("title") or u),
                "url": u,
                "publisher": (urlparse(u).hostname or "").removeprefix("www.").capitalize(),
                "domain": (urlparse(u).hostname or "").removeprefix("www."),
                "snippet": "",
                "published_at": None,
                "icon": "globe",
            }
            for item, u in zip(results, urls[:3])
            if isinstance(item, dict) and item.get("success")
        ]
        all_web_sources = list(search_results) if search_results else url_structured
        final_sources = list(dict.fromkeys(retrieved.get("sources", []) + direct_sources))
        return "web", {
            "crawled": len(successful) or len(search_results),
            "errors": errors,
            "context": final_context,
            "sources": final_sources,
            "retrieval_mode": retrieved.get("retrieval_mode") or "web_feed",
            "structured_sources": all_web_sources,
        }

    tasks = []
    if "market_quote" in intents:
        tasks.append(quote_task())
    if "technical" in intents:
        tasks.append(technical_task())
    if "fundamental" in intents:
        tasks.append(fundamental_task())
    if "news" in intents:
        tasks.append(news_task())
    if "forecast" in intents:
        tasks.append(forecast_task())
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
    structured_sources_list: list[dict[str, Any]] = []
    retrieved_document_citations: list[str] = []
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
            data_status = data.get("data_status") or data_status
            quote_timestamp = quote_timestamp or data.get("last_bar_at")
            context_sections.append(f"TECHNICAL INDICATORS AND PRICE-ONLY MODEL ANALYSIS ({symbol}; visible chart window={chart_period}; bar interval={chart_interval}; displayed chart type={chart_mode}; selected chart view={chart_view}; source={data.get('source')}; data status={data.get('data_status')}; last bar={data.get('last_bar_at')}): metrics={data.get('metrics')}; walk-forward model evaluation={data.get('ml_analysis')}; statistical scenario={data.get('scenario_estimate')}")
            citations.append(f"Technical analysis — {symbol} ({chart_period}, {chart_interval}; last bar {data.get('last_bar_at') or 'date unavailable'}; {data.get('source') or 'provider unavailable'})")
            market_sources += 1
        elif kind == "forecast":
            data_status = data.get("data_status") or data.get("freshness") or data_status
            quote_timestamp = quote_timestamp or data.get("last_bar_at")
            llm_p = data.get("llm_payload", {})
            int_data = data.get("interval", {})
            disag = data.get("disagreement", {})
            opt_m = data.get("optimal_model", {})
            sig_list = [f"{s.get('feature')} ({s.get('direction', '')})" for s in data.get("signals", [])[:4]]
            sig_str = ", ".join(sig_list) if sig_list else "Momentum, Volatility"
            emp_cov = int_data.get("empirical_coverage_percent")
            emp_cov_str = f" (Empirical holdout coverage: {emp_cov}%)" if emp_cov is not None else ""
            
            disag_summary = (
                f"- Multi-model disagreement & dispersion: {disag.get('label', 'Normal')} "
                f"(Forecast spread: {disag.get('spread_percent', 0.0)}%, Vote: {disag.get('directional_consensus', 'Consensus')}). "
                f"{disag.get('explanation', '')}"
            ) if disag else ""

            opt_str = (
                f"- Optimal model by Min OOS MAE: {opt_m.get('name', 'N/A')} "
                f"({'Currently Active' if opt_m.get('is_active') else 'Alternative Model: ' + str(opt_m.get('reason'))})"
            ) if opt_m else ""

            context_sections.append(
                f"VALIDATED PROBABILISTIC FORECAST ({symbol}; horizon={data.get('horizon')} sessions; "
                f"current price={data.get('current_price')} {data.get('currency')}; as-of={data.get('last_bar_at')}; "
                f"selected model={data.get('selected_model')} [{llm_p.get('model_name')}]; "
                f"data provider={data.get('data_source', 'yfinance')} [{data_status}]):\n"
                f"- Expected return: {int_data.get('expected_return_percent')}%\n"
                f"- Price estimate: {int_data.get('expected_price')} {data.get('currency')} "
                f"(Calibrated {int_data.get('confidence_percent')}% nominal conformal interval: "
                f"[{int_data.get('lower_bound_price')} – {int_data.get('upper_bound_price')}]{emp_cov_str})\n"
                f"- Directional tilt: {llm_p.get('directional_probability_bullish_percent')}% Bullish tilt "
                f"(Directional label: {data.get('directional_label')})\n"
                f"- Active model out-of-sample metrics: OOS MAE = {llm_p.get('walk_forward_metrics', {}).get('mae_percent')}%, "
                f"Directional hit rate = {llm_p.get('walk_forward_metrics', {}).get('directional_accuracy_percent')}%, "
                f"Outperforms naive baseline = {llm_p.get('walk_forward_metrics', {}).get('beats_naive_baseline')} "
                f"({llm_p.get('walk_forward_metrics', {}).get('improvement_vs_naive_percent'):+.1f}% edge)\n"
                f"{opt_str}\n"
                f"{disag_summary}\n"
                f"- Top driving signals: {sig_str}\n"
                f"- Limitations & Disclaimer: {data.get('disclaimer')}\n"
                "INSTRUCTION: Preserve numerical values exactly. Explicitly acknowledge uncertainty, model disagreement, and empirical coverage. Do not represent the forecast as a guaranteed outcome."
            )
            citations.append(f"Probabilistic Forecast — {symbol} ({data.get('selected_model')}, {data.get('horizon')}-session horizon; as of {data.get('last_bar_at')})")
            market_sources += 1
        elif kind == "fundamental":
            context_sections.append(f"FUNDAMENTALS ({symbol}; provider={data.get('source')}): {data.get('metrics')}")
            citations.append(f"Fundamentals — {data.get('source')}")
            market_sources += 1
        elif kind == "news":
            news = data[:5] if isinstance(data, list) else []
            if news:
                context_sections.append("RECENT PUBLISHER HEADLINES (summaries are included only when the provider supplied them; these are not independently crawled full articles):\n" + "\n".join(f"- {n.get('title')} — {n.get('publisher')} (published {n.get('published_at') or 'date unavailable'}; retrieved {n.get('retrieved_at') or 'time unavailable'}). Provider summary: {n.get('summary') or 'not supplied'}. Source URL: {n.get('url') or 'unavailable'}" for n in news))
                citations.extend(f"News — {n.get('publisher')}: {n.get('title')} (published {n.get('published_at') or 'date unavailable'}) — {n.get('url')}" for n in news)
                market_sources += len(news)
                from urllib.parse import urlparse
                for n in news:
                    if n.get("title"):
                        u = n.get("url") or ""
                        d = (urlparse(u).hostname or "").removeprefix("www.")
                        structured_sources_list.append({
                            "title": n.get("title"),
                            "url": u,
                            "publisher": n.get("publisher") or d.capitalize() or "News",
                            "domain": d,
                            "snippet": n.get("summary") or "",
                            "published_at": n.get("published_at"),
                            "icon": "newspaper"
                        })
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
                retrieved_document_citations.extend(data.get("sources", []))
                document_passages.extend(data.get("passages", []))
        elif kind == "web":
            web_sources += data.get("crawled", 0)
            if data.get("retrieval_mode"):
                retrieval_modes.append(data["retrieval_mode"])
            if data.get("context"):
                context_sections.append("NEWLY CRAWLED WEB EVIDENCE:\n" + data["context"])
            citations.extend(data.get("sources", []))
            if data.get("structured_sources"):
                structured_sources_list.extend(data.get("structured_sources", []))
            if data.get("errors"):
                failures.extend(data["errors"])
        elif kind == "dataset" and data.get("success"):
            context_sections.append("UPLOADED DATASET ANALYSIS:\n" + data.get("analysis_text", ""))
            citations.append(f"Uploaded dataset — {Path(dataset_path).name}")
        elif kind == "dataset":
            failures.append(f"Dataset analysis failed: {data.get('error', 'unknown dataset error')}")

    unique_citations = list(dict.fromkeys(citations))
    evidence_retrieved = bool(context_sections)

    response_detail = settings.get("response_detail", "balanced")
    if is_greeting:
        detail_instruction = "Reply warmly, helpfully, and briefly in 1-2 short sentences. Do not include markdown headers, bullet lists, or unsolicited disclaimers."
    elif mode == "general" or not context_sections or intents == {"general_chat"}:
        detail_instruction = "Give a valid, direct, short, proper answer in clean Markdown. Answer directly and concisely without unnecessary filler, disclaimers, or echoing raw URLs."
    else:
        detail_instruction = {
            "concise": "Give a valid, direct, short, proper answer containing only the necessary facts. Keep it concise. Cite sources simply by name without raw URLs.",
            "balanced": "Give a valid, direct, short, proper answer in clean Markdown containing only the proper, needed facts and analysis. Avoid filler, conversational padding, or raw URLs. Cite supplied sources cleanly.",
            "detailed": "Provide a thorough, accurate, evidence-based answer explaining reasoning clearly. Keep claims tied to evidence without boilerplate disclaimers or raw URLs.",
        }.get(response_detail, "Give a valid, direct, short, proper answer containing only the proper, needed facts and analysis. Avoid filler.")
    custom_persona = (settings.get("custom_persona") or "").strip()
    if custom_persona:
        detail_instruction = f"{detail_instruction}\n\nCustom Persona & Instructions:\n{custom_persona}"
    if is_capability_query(message) or is_capability_query(retrieval_query):
        cap_info = get_capability_context(message)
        detail_instruction = f"{detail_instruction}\n\nApplication Capabilities & Boundaries Reference:\n{cap_info}"
    prompt_history = _trim_prompt_history(history, int(settings.get("context_size", 4096)))
    try:
        messages = prompt_builder.build(message, prompt_history, context_sections, detail_instruction, local_model=selected_model, mode=mode, user_memories=user_memories)
    except TypeError:
        try:
            messages = prompt_builder.build(message, prompt_history, context_sections, detail_instruction, local_model=selected_model, mode=mode)
        except TypeError:
            try:
                messages = prompt_builder.build(message, prompt_history, context_sections, detail_instruction, local_model=selected_model)
            except TypeError:
                messages = prompt_builder.build(message, prompt_history, context_sections, detail_instruction)

    numeric_validation = "not_applicable"
    numeric_fallback = False
    response = None
    model_identity_answer = False
    model_identity_unavailable = False
    rag_grounding_fallback = False
    if _is_model_identity_question(message):
        try:
            model_is_installed = await ollama_client.has_model(selected_model, min(timeout, 5))
        except Exception:
            model_is_installed = False
        response = (
            f"The configured local Ollama model for this reply is **{selected_model}**."
            if model_is_installed
            else "I could not verify a connected local Ollama model, so I can’t identify an active model for this reply."
        )
        model_identity_answer = True
        model_identity_unavailable = not model_is_installed
    if "document_qa" in intents and _is_numeric_document_question(message) and (document_passages or document_ids):
        fact = _document_numeric_fact(message, document_passages)
        if fact:
            response = _direct_source_answer(fact)
            unique_citations = [fact["source"]]
            numeric_validation = "passed"
            numeric_fallback = True
        else:
            source_lines = "\n".join(f"- {source}" for source in unique_citations) or "- No matching source passage was retrieved."
            response = (
                "## Answer\n\nThe requested numerical value could not be verified from the retrieved document evidence.\n\n"
                "## Key Facts\n\n- No matching numeric statement was found in the retrieved passages.\n\n"
                "## Analysis\n\nA numerical answer would be unsupported by the available document evidence.\n\n"
                "## Limitations\n\n- Select the relevant filing or provide a passage that states this value.\n\n"
                f"## Sources\n\n{source_lines}"
            )
            numeric_validation = "insufficient_evidence"
            numeric_fallback = True
            logger.info("numeric_document_answer_withheld", extra={"query_id": started.isoformat(), "retrieved_passages": len(document_passages)})

    if response is None:
        try:
            healthy = await asyncio.wait_for(ollama_client.check_health(min(timeout, 5)), timeout=timeout)
            if not healthy:
                raise OllamaError("Local AI is unavailable. Start Ollama, then retry your message.", code="ollama_disconnected")
            generation_options = {
                "timeout": timeout,
                "temperature": float(settings.get("temperature", 0.2)),
                "context_size": int(settings.get("context_size", 4096)),
                "max_output_tokens": int(settings.get("max_output_tokens", 2048)),
                "top_p": float(settings.get("top_p", 0.9)),
                "top_k": int(settings.get("top_k", 40)),
                "repeat_penalty": float(settings.get("repeat_penalty", 1.1)),
                "seed": int(settings.get("seed", 0)),
            }
            if on_token is None:
                response = await asyncio.wait_for(ollama_client.chat(messages, selected_model, **generation_options), timeout=timeout)
            else:
                async def generate_stream():
                    stream = await ollama_client.chat(messages, selected_model, stream=True, **generation_options)
                    chunks = []
                    async for item in stream:
                        if item.get("error"):
                            raise OllamaError(str(item["error"]), code="ollama_generation_failed")
                        message_chunk = item.get("message") or {}
                        token = message_chunk.get("content") if isinstance(message_chunk, dict) else ""
                        if token:
                            chunks.append(token)
                            on_token(token)
                        if item.get("done") and item.get("done_reason") == "length":
                            logger.info("model_stream_hit_length_limit", extra={"model": selected_model, "tokens_accumulated": len(chunks)})
                            break
                    text = "".join(chunks).strip()
                    if not text:
                        raise OllamaError("Ollama returned an empty response. Retry your request.", code="ollama_empty_response")
                    return text
                response = await asyncio.wait_for(generate_stream(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            logger.warning("generation_failed", extra={"reason": "request timeout", "model": selected_model})
            raise OllamaError(f"Local AI did not respond within {timeout:g} seconds. Retry or choose a smaller model.", code="ollama_timeout", status_code=504) from exc
        except OllamaError as exc:
            logger.warning("generation_failed", extra={"reason": str(exc), "model": selected_model, "error_code": exc.code})
            raise

    grounding_terms = _unsupported_answer_terms(response, message, document_passages)
    relation_terms = _unsupported_entity_relations(response, message, document_passages)
    contradictory_gap_claim = _answer_claims_evidence_is_missing(response)
    if document_passages and not numeric_fallback and (grounding_terms or relation_terms or contradictory_gap_claim):
        logger.warning("document_answer_withheld", extra={"unsupported_terms": grounding_terms[:12], "unsupported_relations": relation_terms[:12], "retrieved_passages": len(document_passages)})
        source_lines = "\n".join(f"- {source}" for source in unique_citations) or "- No matching source passage was retrieved."
        response = (
            "## Answer\n\nI couldn't verify a direct answer from the passages retrieved, so I won't guess.\n\n"
            "## Key Facts\n\n- The returned excerpts did not contain enough matching wording to support the answer.\n\n"
            "## Analysis\n\nThe selected source may contain the information elsewhere; this retrieval result did not establish it.\n\n"
            "## Limitations\n\n- Try a narrower question or re-index/select the relevant filing section.\n\n"
            f"## Sources\n\n{source_lines}"
        )
        rag_grounding_fallback = True

    format_required = bool((evidence_retrieved or dataset_path) and mode not in {"general"} and intents != {"general_chat"} and "document_qa" in intents)
    missing_sections = _missing_research_sections(response, require_sources=bool(unique_citations), detail=response_detail) if format_required else []

    if response.startswith("Error:"):
        failures.append(response)
    response_sources = response.split("## Sources", 1)[1] if "## Sources" in response else ""
    model_cited_retrieved_source = any(_citation_matches(source, response_sources) for source in unique_citations)
    citation_unverified = evidence_retrieved and (not response_sources or bool(unique_citations) and not model_cited_retrieved_source)
    if citation_unverified and unique_citations:
        if "## Sources" in response:
            response = response.split("## Sources", 1)[0].rstrip()
        response += "\n\n## Sources\n" + "\n".join(f"- {source}" for source in unique_citations)

    missing_sections = _missing_research_sections(response, require_sources=bool(unique_citations), detail=response_detail) if format_required else []
    format_unverified = bool(missing_sections)

    finished = datetime.now(timezone.utc)
    return {
        "answer": response,
        "structured_analysis": {"intents": sorted(intents), "evidence_types": [kind for kind, _ in evidence], "limitations": failures, "chart_context": {"symbol": symbol, "period": chart_period, "interval": chart_interval, "mode": chart_mode, "view": chart_view} if "technical" in intents and symbol else None},
        "citations": unique_citations,
        "structured_sources": structured_sources_list,
        "duration_seconds": max(0.5, round((finished - started).total_seconds(), 1)),
        "sources_unverified": citation_unverified or ("## Sources" in response and not unique_citations),
        "format_unverified": format_unverified,
        "numeric_validation": numeric_validation,
        "data_status": data_status,
        "data_timestamp": quote_timestamp or finished.isoformat(),
        "model": None if numeric_fallback or rag_grounding_fallback or model_identity_unavailable else selected_model,
        "answer_method": "deterministic_model_metadata" if model_identity_answer else "deterministic_insufficient_evidence" if numeric_validation == "insufficient_evidence" else "deterministic_rag_insufficient_evidence" if rag_grounding_fallback else "extractive_source_fallback" if numeric_fallback else "model_generated",
        "retrieval": {"sources": len(unique_citations), "documents": len(set(retrieved_document_citations) & set(unique_citations)), "web_sources": web_sources, "market_sources": market_sources, "document_modes": list(dict.fromkeys(retrieval_modes)), "web_sources_list": structured_sources_list},
        "request_started_at": started.isoformat(),
    }

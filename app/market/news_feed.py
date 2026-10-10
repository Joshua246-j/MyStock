"""Fresh, attributed market-wide news feed aggregation."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import logging
import re

from app.market.symbol_resolver import resolve_symbol
from app.market.storage import normalize_news_items
from app.web.crawler import search_web

logger = logging.getLogger("stockrag.market.news_feed")

COMPANY_NAMES = {
    "AAPL": "Apple", "NVDA": "NVIDIA", "MSFT": "Microsoft", "GOOGL": "Alphabet",
    "AMZN": "Amazon", "META": "Meta Platforms", "TSLA": "Tesla", "SPY": "S&P 500",
    "QQQ": "Nasdaq 100", "RELIANCE.NS": "Reliance Industries", "TCS.NS": "Tata Consultancy Services",
    "HDFCBANK.NS": "HDFC Bank", "INFY.NS": "Infosys", "ICICIBANK.NS": "ICICI Bank",
    "SBIN.NS": "State Bank of India", "BHARTIARTL.NS": "Bharti Airtel", "ITC.NS": "ITC Limited",
    "^NSEI": "Nifty 50", "^BSESN": "BSE Sensex",
}
MAX_SYMBOLS = 10
TRUSTED_PUBLISHER_NAMES = {
    "reuters", "bloomberg", "bloomberg.com", "the wall street journal", "wall street journal", "wsj",
    "cnbc", "financial times", "ft", "associated press", "ap news", "bbc", "marketwatch",
    "moneycontrol", "the economic times", "economic times", "business standard", "businessline",
    "the hindu", "ndtv", "the indian express", "indian express", "yahoo finance",
    "investor's business daily", "investors business daily", "the motley fool", "motley fool",
    "investopedia",
}


def _clean_symbols(symbols: list[str]) -> list[tuple[str, str]]:
    result = []
    seen = set()
    for raw in symbols[:MAX_SYMBOLS]:
        resolved = resolve_symbol(str(raw).strip())
        if not resolved["valid"]:
            continue
        symbol = resolved["resolved_symbol"]
        if symbol in seen:
            continue
        seen.add(symbol)
        result.append((symbol, resolved["market"].casefold()))
    return result


def _parse_published(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        from app.market.storage import _parse_datetime
        parsed = _parse_datetime(value)
        if parsed is None:
            return None
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _trusted_publisher(name: str | None) -> bool:
    normalized = re.sub(r"\s+", " ", str(name or "").casefold().replace("®", "").strip())
    normalized = re.sub(r"[.]+$", "", normalized)
    return normalized in TRUSTED_PUBLISHER_NAMES


def get_news_feed(symbols: list[str], market: str = "all", limit: int = 80, days: int = 7) -> dict:
    """Pull fresh RSS search and configured company feeds, then dedupe and rank."""
    targets = _clean_symbols(symbols)
    market = market if market in {"all", "us", "india"} else "all"
    days = max(1, min(int(days), 30))
    selected = [(symbol, region) for symbol, region in targets
                if market == "all" or (market == "india" and region == "india")
                or (market == "us" and region != "india")]

    queries: list[tuple[str, str, str]] = []
    if market in {"all", "us"}:
        queries.append(("US markets", "US stock market OR Wall Street earnings stocks", "us"))
    if market in {"all", "india"}:
        queries.append(("India markets", "India stock market NSE BSE earnings shares", "india"))
    for symbol, region in selected:
        company = COMPANY_NAMES.get(symbol, symbol.replace(".NS", "").replace(".BO", "").lstrip("^")).strip()
        queries.append((symbol, f'"{company}" stock company earnings', "india" if region == "india" else "us"))

    raw_items: list[dict] = []
    errors: list[str] = []
    tasks = {}
    # Every search is a fresh RSS request. search_web enforces HTTPS and a
    # publisher allowlist; results remain excerpts with links to the publisher.
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(queries)))) as pool:
        for ticker, query, region in queries:
            tasks[pool.submit(search_web, query, 8, 10.0)] = (ticker, region)
        for future in as_completed(tasks):
            ticker, region = tasks[future]
            try:
                results = future.result()
            except Exception as exc:
                logger.info("news_rss_search_failed", extra={"ticker": ticker, "reason": str(exc)})
                errors.append(ticker)
                continue
            target_name = COMPANY_NAMES.get(ticker, ticker.replace(".NS", "").replace(".BO", "").lstrip("^")).strip()
            base_symbol = ticker.split(".", 1)[0].lstrip("^") if ticker not in {"US markets", "India markets"} else ""
            for item in results:
                if ticker not in {"US markets", "India markets"}:
                    searchable = f"{item.get('title') or ''} {item.get('snippet') or ''}"
                    target_pattern = rf"(?<![A-Z0-9]){re.escape(target_name)}(?![A-Z0-9])"
                    symbol_pattern = rf"(?<![A-Z0-9]){re.escape(base_symbol)}(?![A-Z0-9])" if base_symbol else r"(?!)"
                    if not (re.search(target_pattern, searchable, re.I) or re.search(symbol_pattern, searchable, re.I)):
                        continue
                raw_items.append({
                    "title": item.get("title"), "url": item.get("url"),
                    "publisher": item.get("publisher"), "publisher_url": item.get("publisher_url"),
                    "summary": item.get("snippet"), "image": item.get("image"),
                    "published_at": item.get("published_at"), "ticker": ticker if ticker not in {"US markets", "India markets"} else None,
                    "related_tickers": [ticker] if ticker not in {"US markets", "India markets"} else [],
                    "market": region, "feed_source": "Google News RSS",
                    "summary_type": "publisher excerpt" if item.get("snippet") else None,
                })

    # Direct provider headlines add company-linked images and richer metadata
    # where a configured free provider returns them. Failures do not discard RSS.
    try:
        from app.dependencies import market_service
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(selected)))) as pool:
            futures = {pool.submit(market_service.get_news_result, symbol, True): (symbol, region)
                       for symbol, region in selected}
            for future in as_completed(futures):
                symbol, region = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    logger.info("news_provider_fetch_failed", extra={"symbol": symbol, "reason": str(exc)})
                    continue
                for item in result.get("news", []):
                    # Third-party company feeds can syndicate blogs, social posts,
                    # and low-context commentary. Only show named, approved outlets.
                    if not _trusted_publisher(item.get("publisher")):
                        continue
                    raw_items.append({**item, "ticker": symbol, "market": "india" if region == "india" else "us",
                                      "feed_source": result.get("source") or item.get("publisher"),
                                      "feed_status": result.get("data_status") or "UNVERIFIED_FRESHNESS",
                                      "summary_type": "publisher excerpt" if item.get("summary") else None})
    except Exception:
        logger.exception("news_provider_aggregation_failed")

    normalized = normalize_news_items(raw_items, limit=100)
    now = datetime.now(timezone.utc)
    deduped: dict[str, dict] = {}
    for item in normalized:
        published = _parse_published(item.get("published_at"))
        if published and (published > now + timedelta(minutes=5) or now - published > timedelta(days=days)):
            continue
        title_key = re.sub(r"\W+", " ", item.get("title", "").casefold()).strip()
        publisher_key = re.sub(r"\W+", " ", (item.get("publisher") or "").casefold()).strip()
        key = f"{title_key}|{publisher_key}"
        previous = deduped.get(key)
        if previous is None or (not previous.get("image") and item.get("image")) or (not previous.get("summary") and item.get("summary")):
            deduped[key] = item
    ordered = sorted(deduped.values(), key=lambda item: _parse_published(item.get("published_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    now_iso = now.isoformat()
    page = ordered[:max(1, min(int(limit), 100))]
    publishers = sorted({item.get("publisher") for item in page if item.get("publisher")})
    return {
        "success": bool(page), "news": page, "total_available": len(ordered),
        "has_more": len(ordered) > len(page), "source_count": len(publishers),
        "publishers": publishers, "retrieved_at": now_iso,
        "data_status": "LIVE_SEARCH" if page else "UNAVAILABLE",
        "errors": errors,
        "error": None if page else "No recent headlines were returned by the configured publishers.",
    }

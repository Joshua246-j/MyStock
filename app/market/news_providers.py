"""Multi-source, reliable Global and Indian financial news feed providers."""
from __future__ import annotations

import email.utils
import html
import logging
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.market.symbol_resolver import INDIAN_COMPANY_ALIASES

logger = logging.getLogger("stockrag.market.news_providers")

_SEARCH_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Company mappings for ticker detection across global and indian feeds
COMPANY_TICKER_MAP: dict[str, str] = {
    "apple": "AAPL", "aapl": "AAPL",
    "microsoft": "MSFT", "msft": "MSFT",
    "nvidia": "NVDA", "nvda": "NVDA",
    "alphabet": "GOOGL", "google": "GOOGL", "googl": "GOOGL", "goog": "GOOGL",
    "amazon": "AMZN", "amzn": "AMZN",
    "meta platforms": "META", "meta": "META",
    "tesla": "TSLA", "tsla": "TSLA",
    "s&p 500": "SPY", "spy": "SPY",
    "nasdaq": "QQQ", "qqq": "QQQ",
    "reliance industries": "RELIANCE.NS", "reliance": "RELIANCE.NS", "ril": "RELIANCE.NS",
    "tata consultancy": "TCS.NS", "tcs": "TCS.NS",
    "hdfc bank": "HDFCBANK.NS", "hdfc": "HDFCBANK.NS",
    "infosys": "INFY.NS", "infy": "INFY.NS",
    "icici bank": "ICICIBANK.NS",
    "state bank of india": "SBIN.NS", "sbi": "SBIN.NS",
    "bharti airtel": "BHARTIARTL.NS", "airtel": "BHARTIARTL.NS",
    "itc limited": "ITC.NS", "itc": "ITC.NS",
    "wipro": "WIPRO.NS",
    "hindustan unilever": "HINDUNILVR.NS", "hul": "HINDUNILVR.NS",
    "larsen & toubro": "LT.NS", "l&t": "LT.NS",
    "bajaj finance": "BAJFINANCE.NS",
    "kotak mahindra": "KOTAKBANK.NS", "kotak bank": "KOTAKBANK.NS",
    "maruti suzuki": "MARUTI.NS", "maruti": "MARUTI.NS",
    "tata motors": "TATAMOTORS.NS",
    "tata steel": "TATASTEEL.NS",
    "sun pharma": "SUNPHARMA.NS",
    "adani enterprises": "ADANIENT.NS", "adani": "ADANIENT.NS",
    "nifty 50": "^NSEI", "nifty": "^NSEI",
    "sensex": "^BSESN", "bse sensex": "^BSESN",
}

INDIAN_FEED_SOURCES = [
    {
        "name": "Google News India Business",
        "publisher": "Google News India",
        "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-IN&gl=IN&ceid=IN:en",
        "market": "india",
        "publisher_url": "https://news.google.com",
    },
    {
        "name": "Economic Times Markets",
        "publisher": "The Economic Times",
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "market": "india",
        "publisher_url": "https://economictimes.indiatimes.com",
    },
    {
        "name": "Economic Times Stocks",
        "publisher": "The Economic Times",
        "url": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
        "market": "india",
        "publisher_url": "https://economictimes.indiatimes.com",
    },
    {
        "name": "Livemint Markets",
        "publisher": "Livemint",
        "url": "https://www.livemint.com/rss/markets",
        "market": "india",
        "publisher_url": "https://www.livemint.com",
    },
    {
        "name": "Livemint Companies",
        "publisher": "Livemint",
        "url": "https://www.livemint.com/rss/companies",
        "market": "india",
        "publisher_url": "https://www.livemint.com",
    },
    {
        "name": "Business Standard Markets",
        "publisher": "Business Standard",
        "url": "https://www.business-standard.com/rss/markets-106.rss",
        "market": "india",
        "publisher_url": "https://www.business-standard.com",
    },
    {
        "name": "Business Standard Finance",
        "publisher": "Business Standard",
        "url": "https://www.business-standard.com/rss/finance-103.rss",
        "market": "india",
        "publisher_url": "https://www.business-standard.com",
    },
    {
        "name": "The Hindu BusinessLine Markets",
        "publisher": "The Hindu BusinessLine",
        "url": "https://www.thehindubusinessline.com/markets/stock-markets/feeder/default.rss",
        "market": "india",
        "publisher_url": "https://www.thehindubusinessline.com",
    },
    {
        "name": "The Hindu BusinessLine Companies",
        "publisher": "The Hindu BusinessLine",
        "url": "https://www.thehindubusinessline.com/companies/feeder/default.rss",
        "market": "india",
        "publisher_url": "https://www.thehindubusinessline.com",
    },
    {
        "name": "Moneycontrol Markets",
        "publisher": "Moneycontrol",
        "url": "https://www.moneycontrol.com/rss/marketreports.xml",
        "market": "india",
        "publisher_url": "https://www.moneycontrol.com",
    },
    {
        "name": "Moneycontrol Top News",
        "publisher": "Moneycontrol",
        "url": "https://www.moneycontrol.com/rss/MCtopnews.xml",
        "market": "india",
        "publisher_url": "https://www.moneycontrol.com",
    },
    {
        "name": "Financial Express Markets",
        "publisher": "Financial Express",
        "url": "https://www.financialexpress.com/market/feed/",
        "market": "india",
        "publisher_url": "https://www.financialexpress.com",
    },
]

GLOBAL_FEED_SOURCES = [
    {
        "name": "Google News US Business",
        "publisher": "Google News US",
        "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en",
        "market": "us",
        "publisher_url": "https://news.google.com",
    },
    {
        "name": "CNBC Markets",
        "publisher": "CNBC",
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
        "market": "us",
        "publisher_url": "https://www.cnbc.com",
    },
    {
        "name": "CNBC Business",
        "publisher": "CNBC",
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147",
        "market": "us",
        "publisher_url": "https://www.cnbc.com",
    },
    {
        "name": "Yahoo Finance News",
        "publisher": "Yahoo Finance",
        "url": "https://finance.yahoo.com/news/rssindex",
        "market": "us",
        "publisher_url": "https://finance.yahoo.com",
    },
    {
        "name": "MarketWatch Top Stories",
        "publisher": "MarketWatch",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "market": "us",
        "publisher_url": "https://www.marketwatch.com",
    },
    {
        "name": "MarketWatch Real-time",
        "publisher": "MarketWatch",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
        "market": "us",
        "publisher_url": "https://www.marketwatch.com",
    },
    {
        "name": "WSJ Markets",
        "publisher": "The Wall Street Journal",
        "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "market": "us",
        "publisher_url": "https://www.wsj.com",
    },
    {
        "name": "WSJ Business",
        "publisher": "The Wall Street Journal",
        "url": "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",
        "market": "us",
        "publisher_url": "https://www.wsj.com",
    },
    {
        "name": "BBC Business",
        "publisher": "BBC",
        "url": "http://feeds.bbci.co.uk/news/business/rss.xml",
        "market": "us",
        "publisher_url": "https://www.bbc.com/news/business",
    },
    {
        "name": "Investing.com News",
        "publisher": "Investing.com",
        "url": "https://www.investing.com/rss/news_25.rss",
        "market": "us",
        "publisher_url": "https://www.investing.com",
    },
    {
        "name": "Forbes Business",
        "publisher": "Forbes",
        "url": "https://www.forbes.com/business/feed/",
        "market": "us",
        "publisher_url": "https://www.forbes.com",
    },
    {
        "name": "Fortune Business",
        "publisher": "Fortune",
        "url": "https://fortune.com/feed/",
        "market": "us",
        "publisher_url": "https://fortune.com",
    },
    {
        "name": "Seeking Alpha Market Currents",
        "publisher": "Seeking Alpha",
        "url": "https://seekingalpha.com/market_currents.xml",
        "market": "us",
        "publisher_url": "https://seekingalpha.com",
    },
]


def _detect_tickers(text: str) -> list[str]:
    """Identify relevant stock symbols from text mentions."""
    found: set[str] = set()
    cleaned = f" {text} "
    for name, ticker in COMPANY_TICKER_MAP.items():
        pattern = rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])"
        if re.search(pattern, cleaned, re.IGNORECASE):
            found.add(ticker)
    return sorted(found)


def _parse_published_date(raw_date: str | None) -> str | None:
    """Normalize RFC 2822, RFC 822, or ISO-8601 timestamps to UTC ISO strings."""
    if not raw_date:
        return None
    raw_str = str(raw_date).strip()
    try:
        # Try RFC 2822 / 822 via email.utils
        parsed_tuple = email.utils.parsedate_to_datetime(raw_str)
        if parsed_tuple:
            if parsed_tuple.tzinfo is None:
                parsed_tuple = parsed_tuple.replace(tzinfo=timezone.utc)
            return parsed_tuple.astimezone(timezone.utc).isoformat()
    except Exception:
        pass

    try:
        dt = datetime.fromisoformat(raw_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        pass

    # Generic date parser fallback
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}):?(\d{2})?)?", raw_str)
    if match:
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        hour = int(match.group(4) or 0)
        minute = int(match.group(5) or 0)
        sec = int(match.group(6) or 0)
        try:
            return datetime(year, month, day, hour, minute, sec, tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass

    return None


def _clean_html_text(text: str | None) -> str:
    """Strip HTML markup and unescape HTML entities."""
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    clean = soup.get_text(" ", strip=True)
    return html.unescape(" ".join(clean.split()))


def _extract_image_url(item_elem: ET.Element, description_html: str = "") -> str | None:
    """Extract thumbnail or main article image from standard RSS media extensions."""
    # 1. Enclosure image
    enclosure = item_elem.find("enclosure")
    if enclosure is not None:
        enc_url = enclosure.get("url")
        enc_type = (enclosure.get("type") or "").casefold()
        if enc_url and ("image" in enc_type or enc_url.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))):
            if enc_url.startswith("https://"):
                return enc_url

    # 2. Namespaced media:content / media:thumbnail
    namespaces = {
        "media": "http://search.yahoo.com/mrss/",
        "content": "http://purl.org/rss/1.0/modules/content/",
    }
    for tag in ("media:content", "media:thumbnail"):
        elem = item_elem.find(tag, namespaces)
        if elem is not None:
            cand = elem.get("url")
            if cand and cand.startswith("https://"):
                return cand

    # 3. img tag inside description HTML
    if description_html:
        try:
            soup = BeautifulSoup(description_html, "html.parser")
            img = soup.find("img")
            if img:
                src = img.get("src")
                if src and src.startswith("https://"):
                    return src
        except Exception:
            pass

    return None


def parse_rss_feed(content: bytes | str, feed_meta: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse RSS 2.0 or Atom XML content into normalized news items."""
    results: list[dict[str, Any]] = []
    if not content:
        return results

    try:
        if isinstance(content, str):
            content = content.encode("utf-8")
        root = ET.fromstring(content)
    except Exception as exc:
        logger.debug("rss_xml_parse_error", extra={"feed": feed_meta.get("name"), "error": str(exc)})
        # Attempt fallback parsing with html.parser if XML declaration or tags had issues
        try:
            soup = BeautifulSoup(content, "html.parser")
            items = soup.find_all("item")
            for item in items:
                title = item.find("title")
                link = item.find("link")
                pub_date = item.find("pubdate")
                desc = item.find("description")
                if not title or not link:
                    continue
                t_str = _clean_html_text(title.text)
                l_str = link.text.strip()
                if not t_str or not l_str.startswith("http"):
                    continue
                d_str = _clean_html_text(desc.text if desc else "")
                published_at = _parse_published_date(pub_date.text if pub_date else None)
                img = None
                if desc:
                    img_tag = BeautifulSoup(desc.text, "html.parser").find("img")
                    if img_tag and img_tag.get("src", "").startswith("https://"):
                        img = img_tag["src"]

                detected_tickers = _detect_tickers(f"{t_str} {d_str}")
                results.append({
                    "title": t_str[:300],
                    "url": l_str,
                    "publisher": feed_meta.get("publisher", "Financial News"),
                    "publisher_url": feed_meta.get("publisher_url"),
                    "summary": d_str[:1000] if d_str else "",
                    "image": img,
                    "published_at": published_at,
                    "ticker": detected_tickers[0] if detected_tickers else None,
                    "related_tickers": detected_tickers,
                    "market": feed_meta.get("market", "us"),
                    "feed_source": feed_meta.get("name", "Direct RSS"),
                    "summary_type": "breaking topic headline",
                })
            return results
        except Exception:
            return []

    # Standard XML item iteration
    items = root.findall(".//item")
    if not items:
        # Check for Atom entries
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    for item in items:
        def get_elem_text(name: str) -> str:
            elem = item.find(name)
            if elem is None:
                # Atom namespace check
                elem = item.find(f"{{http://www.w3.org/2005/Atom}}{name}")
            return " ".join((elem.text or "").split()) if elem is not None and elem.text else ""

        title = _clean_html_text(get_elem_text("title"))
        link = get_elem_text("link")
        if not link:
            link_elem = item.find("{http://www.w3.org/2005/Atom}link")
            if link_elem is not None:
                link = link_elem.get("href", "")

        if not title or not link or not link.startswith("http"):
            continue

        raw_desc = get_elem_text("description") or get_elem_text("summary")
        summary = _clean_html_text(raw_desc)
        pub_date = get_elem_text("pubDate") or get_elem_text("published") or get_elem_text("updated")
        published_at = _parse_published_date(pub_date)
        image_url = _extract_image_url(item, raw_desc)

        # Publisher from source tag if available (e.g. Google News)
        source_elem = item.find("source")
        publisher = feed_meta.get("publisher", "Financial News")
        publisher_url = feed_meta.get("publisher_url")
        if source_elem is not None and source_elem.text:
            publisher = source_elem.text.strip()
            if source_elem.get("url"):
                publisher_url = source_elem.get("url")

        detected_tickers = _detect_tickers(f"{title} {summary}")

        results.append({
            "title": title[:300],
            "url": link,
            "publisher": publisher[:120],
            "publisher_url": publisher_url,
            "summary": summary[:1000] if summary else "",
            "image": image_url,
            "published_at": published_at,
            "ticker": detected_tickers[0] if detected_tickers else None,
            "related_tickers": detected_tickers,
            "market": feed_meta.get("market", "us"),
            "feed_source": feed_meta.get("name", "Direct RSS"),
            "summary_type": "breaking topic headline",
        })

    return results


def fetch_single_feed(feed_meta: dict[str, Any], timeout: float = 6.0) -> list[dict[str, Any]]:
    """Fetch and parse one news feed with isolated exception handling."""
    url = feed_meta["url"]
    try:
        with httpx.stream(
            "GET",
            url,
            headers={"User-Agent": _SEARCH_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, */*"},
            follow_redirects=True,
            timeout=timeout,
        ) as response:
            if response.status_code != 200:
                logger.info("feed_fetch_non_200", extra={"name": feed_meta["name"], "status": response.status_code})
                return []
            body = response.read()
        return parse_rss_feed(body, feed_meta)
    except Exception as exc:
        logger.info("feed_fetch_failed", extra={"name": feed_meta["name"], "reason": str(exc)})
        return []


def fetch_all_provider_feeds(market: str = "all", max_workers: int = 8, timeout: float = 6.0) -> list[dict[str, Any]]:
    """Concurrently fetch news across all configured Global and Indian feeds."""
    selected_feeds: list[dict[str, Any]] = []
    if market in {"all", "india"}:
        selected_feeds.extend(INDIAN_FEED_SOURCES)
    if market in {"all", "us"}:
        selected_feeds.extend(GLOBAL_FEED_SOURCES)

    if not selected_feeds:
        return []

    collected: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(selected_feeds))) as executor:
        futures = {executor.submit(fetch_single_feed, feed, timeout): feed for feed in selected_feeds}
        for future in as_completed(futures):
            try:
                items = future.result()
                collected.extend(items)
            except Exception:
                pass

    return collected


def fetch_ticker_targeted_news(symbol: str, limit: int = 25, timeout: float = 6.0) -> list[dict[str, Any]]:
    """Fetch real-time company-targeted news via Google News RSS and direct financial queries.

    Ensures that Indian stocks (e.g. HDFCBANK.NS, RELIANCE.NS, TCS.NS) and Global stocks
    always have fresh, attributed news articles even when secondary providers return empty.
    """
    from urllib.parse import quote_plus
    from app.market.symbol_resolver import resolve_symbol

    resolved = resolve_symbol(symbol)
    resolved_symbol = resolved["resolved_symbol"]
    is_india = resolved.get("market") == "india" or resolved_symbol.endswith((".NS", ".BO"))

    # Map symbol to searchable company names / query terms
    search_terms = {
        "HDFCBANK.NS": "HDFC Bank",
        "RELIANCE.NS": "Reliance Industries",
        "TCS.NS": "Tata Consultancy Services TCS",
        "INFY.NS": "Infosys",
        "ICICIBANK.NS": "ICICI Bank",
        "SBIN.NS": "State Bank of India SBI",
        "BHARTIARTL.NS": "Bharti Airtel",
        "ITC.NS": "ITC Limited",
        "WIPRO.NS": "Wipro",
        "TATAMOTORS.NS": "Tata Motors",
        "LT.NS": "Larsen Toubro",
        "KOTAKBANK.NS": "Kotak Mahindra Bank",
        "AAPL": "Apple",
        "MSFT": "Microsoft",
        "NVDA": "NVIDIA",
        "GOOGL": "Alphabet Google",
        "AMZN": "Amazon",
        "META": "Meta Platforms",
        "TSLA": "Tesla",
    }

    clean_base = resolved_symbol.split(".")[0]
    term = search_terms.get(resolved_symbol, search_terms.get(clean_base, clean_base))

    if is_india:
        query = f'"{term}" stock NSE'
        feed_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-IN&gl=IN&ceid=IN:en"
        market_region = "india"
    else:
        query = f'"{term}" stock'
        feed_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
        market_region = "us"

    feed_meta = {
        "name": f"Targeted News ({resolved_symbol})",
        "publisher": "Financial News",
        "url": feed_url,
        "market": market_region,
        "publisher_url": "https://news.google.com",
    }

    items = fetch_single_feed(feed_meta, timeout=timeout)
    # Ensure items are tagged with ticker
    for item in items:
        item["ticker"] = resolved_symbol
        if "related_tickers" not in item or not item["related_tickers"]:
            item["related_tickers"] = [resolved_symbol]
        elif resolved_symbol not in item["related_tickers"]:
            item["related_tickers"].insert(0, resolved_symbol)

    return items[:limit]

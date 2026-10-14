import httpx
import ipaddress
import socket
import logging
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse
from threading import Lock
from time import monotonic, sleep
from urllib.robotparser import RobotFileParser
from hashlib import sha256
from app.rag.ingest import chunk_and_store

ALLOWED_DOMAINS = {
    "yahoo.com", "finance.yahoo.com", "reuters.com", "bloomberg.com", 
    "wsj.com", "cnbc.com", "ft.com", "investopedia.com", "sec.gov",
    "apnews.com", "bbc.com", "bbc.co.uk", "bbci.co.uk", "marketwatch.com", "moneycontrol.com",
    "economictimes.indiatimes.com", "indiatimes.com", "timesofindia.indiatimes.com",
    "business-standard.com", "livemint.com", "thehindubusinessline.com", "thehindu.com",
    "ndtv.com", "ndtvprofit.com", "indianexpress.com", "financialexpress.com",
    "businesstoday.in", "cnbctv18.com", "zeebiz.com", "outlookindia.com", "outlookbusiness.com",
    "deccanherald.com", "upstox.com", "investing.com", "investors.com", "fool.com",
    "themotleyfool.com", "barrons.com", "forbes.com", "fortune.com", "seekingalpha.com",
    "benzinga.com", "tipranks.com", "zacks.com", "thestreet.com", "barchart.com",
    "tradingkey.com", "247wallst.com", "marketbeat.com", "morningstar.com",
    "businessinsider.com", "foxbusiness.com", "coindesk.com", "cointelegraph.com",
    "techcrunch.com", "qz.com", "dowjones.io", "a.dj.com", "feedburner.com",
}
logger = logging.getLogger("stockrag.crawler")
_rate_lock = Lock()
_domain_locks: dict[str, Lock] = {}
_last_request_by_domain: dict[str, float] = {}
_MIN_DOMAIN_INTERVAL_SECONDS = 1.0
_MAX_PAGE_BYTES = 5 * 1024 * 1024
_MAX_ROBOTS_BYTES = 256 * 1024
_CRAWLER_AGENT = "MyStockResearch/1.0 (https://mystock.ai; contact: research@mystock.ai)"
_SEARCH_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def _is_safe_public_host(host: str, port: int) -> bool:
    try:
        resolved = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        for item in resolved:
            ip = ipaddress.ip_address(item[4][0])
            if not ip.is_global or ip.is_loopback or ip.is_private or ip.is_reserved or ip.is_link_local:
                return False
        return True
    except Exception:
        return False


def _allowed_public_url(url: str, allow_all_public: bool = True) -> bool:
    """Apply the host/scheme/port boundary and SSRF protection to public links."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        if not host or parsed.scheme not in {"http", "https"}:
            return False
        if parsed.username or parsed.password:
            return False
        expected_port = 443 if parsed.scheme == "https" else 80
        if parsed.port not in (None, expected_port):
            return False
        if not allow_all_public and host not in ALLOWED_DOMAINS:
            return False
        return _is_safe_public_host(host, expected_port)
    except Exception:
        return False



def search_web(query: str, max_results: int = 5, timeout: float = 8.0, market: str = "us") -> list[dict[str, str]]:
    """Retrieve news-search evidence from Google News RSS, limited to trusted publishers."""
    safe_query = " ".join(str(query).split())[:500]
    if not safe_query:
        return []
    params = {
        "q": safe_query,
        "hl": "en-IN" if market == "india" else "en-US",
        "gl": "IN" if market == "india" else "US",
        "ceid": "IN:en" if market == "india" else "US:en",
    }
    with httpx.stream("GET", "https://news.google.com/rss/search", params=params,
                      headers={"User-Agent": _SEARCH_AGENT, "Accept": "application/rss+xml, application/xml"},
                      follow_redirects=True, timeout=timeout) as response:
        response.raise_for_status()
        body = _read_bounded_response(response, _MAX_PAGE_BYTES)
    if body is None:
        raise ValueError("The news-search response exceeded the size limit.")
    root = ET.fromstring(body)
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in root.findall(".//item"):
        def text_for(name: str) -> str:
            element = item.find(name)
            return " ".join((element.text or "").split()) if element is not None else ""
        title = text_for("title")
        url = text_for("link")
        description_node = item.find("description")
        description = " ".join(" ".join(description_node.itertext()).split()) if description_node is not None else ""
        image_url = None
        if description_node is not None:
            image_node = BeautifulSoup(ET.tostring(description_node, encoding="unicode"), "html.parser").find("img")
            candidate_image = image_node.get("src") if image_node else None
            if candidate_image and _allowed_public_url(candidate_image):
                image_url = candidate_image
        publisher_node = item.find("source")
        publisher = " ".join((publisher_node.text or "").split()) if publisher_node is not None else ""
        publisher_url = (publisher_node.get("url") or "") if publisher_node is not None else ""
        if not title or not _allowed_public_url(publisher_url, allow_all_public=False):
            continue
        if not url.startswith("https://news.google.com/rss/articles/"):
            continue
        key = url.split("?", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        snippet = re.sub(r"\s+([,.;:!?])", r"\1", BeautifulSoup(description, "html.parser").get_text(" ", strip=True))[:1000]
        normalize_result_text = lambda value: re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
        normalized_snippet = normalize_result_text(snippet)
        normalized_title_source = normalize_result_text(f"{title} {publisher}")
        if normalized_snippet == normalized_title_source or normalized_snippet == normalize_result_text(title):
            snippet = ""
        results.append({
            "title": title[:300],
            "url": url,
            "publisher": publisher[:120],
            "publisher_url": publisher_url,
            "snippet": snippet,
            "image": image_url,
            "published_at": text_for("pubDate"),
        })
        if len(results) >= max(1, min(int(max_results), 30)):
            break
    return results


def fetch_topic_rss(market: str = "us", max_results: int = 40, timeout: float = 6.0) -> list[dict[str, str]]:
    """Retrieve top breaking business headlines directly from regional Google News Business topic feeds."""
    url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-IN&gl=IN&ceid=IN:en" if market == "india" else "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en"
    try:
        with httpx.stream("GET", url, headers={"User-Agent": _SEARCH_AGENT, "Accept": "application/rss+xml, application/xml"}, follow_redirects=True, timeout=timeout) as response:
            response.raise_for_status()
            body = _read_bounded_response(response, _MAX_PAGE_BYTES)
        if not body:
            return []
        root = ET.fromstring(body)
        results: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in root.findall(".//item"):
            def text_for(name: str) -> str:
                element = item.find(name)
                return " ".join((element.text or "").split()) if element is not None else ""
            title = text_for("title")
            item_url = text_for("link")
            pub_node = item.find("source")
            publisher = " ".join((pub_node.text or "").split()) if pub_node is not None else ""
            pub_url = (pub_node.get("url") or "") if pub_node is not None else ""
            if not title or not item_url:
                continue
            key = item_url.split("?", 1)[0]
            if key in seen:
                continue
            seen.add(key)
            description_node = item.find("description")
            image_url = None
            snippet = ""
            if description_node is not None:
                try:
                    raw_desc = ET.tostring(description_node, encoding="unicode")
                    img_node = BeautifulSoup(raw_desc, "html.parser").find("img")
                    if img_node and img_node.get("src", "").startswith("https://"):
                        image_url = img_node["src"]
                    snippet = BeautifulSoup(raw_desc, "html.parser").get_text(" ", strip=True)[:1000]
                except Exception:
                    pass
            results.append({
                "title": title[:300],
                "url": item_url,
                "publisher": publisher[:120],
                "publisher_url": pub_url,
                "snippet": snippet,
                "image": image_url,
                "published_at": text_for("pubDate"),
            })
            if len(results) >= max(1, min(int(max_results), 50)):
                break
        return results
    except Exception as exc:
        logger.info("topic_rss_fetch_failed", extra={"market": market, "reason": str(exc)})
        return []



def _respect_rate_limit(domain: str) -> None:
    """Keep requests to each allowed host at or below one per second."""
    with _rate_lock:
        domain_lock = _domain_locks.setdefault(domain, Lock())
    with domain_lock:
        now = monotonic()
        wait = _MIN_DOMAIN_INTERVAL_SECONDS - (now - _last_request_by_domain.get(domain, 0.0))
        if wait > 0:
            sleep(wait)
        _last_request_by_domain[domain] = monotonic()


def _robots_allows(client: httpx.Client, url: str, domain: str) -> tuple[bool, str | None]:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    _respect_rate_limit(domain)
    try:
        with client.stream("GET", robots_url, headers={"User-Agent": _CRAWLER_AGENT}) as response:
            if response.status_code in {401, 403, 404, 410}:
                # Many legitimate sites return 403 or 404 for robots.txt
                return True, None
            if response.status_code >= 500:
                return True, None
            response.raise_for_status()
            body = _read_bounded_response(response, _MAX_ROBOTS_BYTES)
            if body is None:
                return True, None
        parser = RobotFileParser(robots_url)
        parser.parse(body.decode("utf-8", errors="replace").splitlines())
        return parser.can_fetch(_CRAWLER_AGENT, url), None
    except Exception:
        return True, None


def _read_bounded_response(response: httpx.Response, maximum_bytes: int) -> bytes | None:
    """Read a response incrementally, stopping before retaining an oversized body."""
    length = response.headers.get("content-length")
    if length:
        try:
            if int(length) > maximum_bytes:
                return None
        except ValueError:
            pass
    body = bytearray()
    for block in response.iter_bytes():
        if len(body) + len(block) > maximum_bytes:
            return None
        body.extend(block)
    return bytes(body)

def crawl_url(url: str, timeout: float = 15.0, document_id: int | None = None, metadata_hints: dict | None = None):
    """Crawls a single URL, extracts text, and stores in RAG."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        domain = host
        if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
            return {"success": False, "error": "Invalid or unsafe URL"}
        expected_port = 443 if parsed.scheme == "https" else 80
        if parsed.port not in (None, expected_port):
            return {"success": False, "error": "Only standard HTTP and HTTPS ports are allowed."}
        if domain.startswith("www."):
            domain = domain[4:]

        if not _is_safe_public_host(host, expected_port):
            return {"success": False, "error": "Private, local, or non-public network destinations are not allowed."}
    except Exception as e:
        return {"success": False, "error": f"Invalid URL formatting: {e}"}

    headers = {
        "User-Agent": _CRAWLER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            try:
                allowed, robots_error = _robots_allows(client, url, domain)
                if not allowed:
                    return {"success": False, "error": robots_error or "The site's robots.txt disallows this page."}
            except Exception:
                pass
            _respect_rate_limit(domain)
            with client.stream("GET", url, headers=headers) as response:
                resp_url = getattr(response, "url", None)
                final_host = (resp_url.host or "").lower() if resp_url else domain
                final_port = (resp_url.port or (443 if resp_url.scheme == "https" else 80)) if resp_url else (parsed.port or (443 if parsed.scheme == "https" else 80))
                if not _is_safe_public_host(final_host, final_port):
                    return {"success": False, "error": "Redirected destination is not a permitted public host."}
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").casefold()
                if content_type and "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                    return {"success": False, "error": "The URL did not return an HTML page."}
                content = _read_bounded_response(response, _MAX_PAGE_BYTES)
                if content is None:
                    return {"success": False, "error": "The page exceeds the 5 MB crawl limit."}
            soup = BeautifulSoup(content, 'html.parser')

            for script in soup(["script", "style", "nav", "footer", "aside"]):
                script.extract()
                
            text = soup.get_text(separator=' ', strip=True)
            title = soup.title.get_text(" ", strip=True) if soup.title else url
            canonical_tag = soup.find("link", rel=lambda value: value and "canonical" in value)
            canonical = canonical_tag.get("href") if canonical_tag else url
            if canonical:
                from urllib.parse import urljoin
                canonical = urljoin(url, canonical)
                canonical_domain = (urlparse(canonical).hostname or "").lower().removeprefix("www.")
                if urlparse(canonical).scheme not in {"http", "https"} or canonical_domain not in ALLOWED_DOMAINS:
                    canonical = url
            author_tag = soup.find("meta", attrs={"name": "author"}) or soup.find("meta", attrs={"property": "article:author"})
            published_tag = soup.find("meta", attrs={"property": "article:published_time"}) or soup.find("meta", attrs={"name": "date"})
            
            if not text:
                return {"success": False, "error": "No readable text found on page."}

            filing_text = f"{title}\n{text[:200_000]}"
            filing_match = re.search(r"\bFORM\s+10\s*[-–]?\s*([KQ])\b", filing_text, re.IGNORECASE) if domain == "sec.gov" else None
            filing_type = f"10-{filing_match.group(1).upper()}" if filing_match else None
            source_type = "sec_filing" if filing_type else "sec" if domain == "sec.gov" else "web"

            metadata = {
                **(metadata_hints or {}),
                "source": title,
                "url": url,
                "document_type": filing_type or "web",
                "source_type": source_type,
                "document_id": document_id or 0,
                "retrieved_at": datetime.now().astimezone().isoformat(),
                "canonical_url": canonical,
                "author": author_tag.get("content") if author_tag else None,
                "published_at": published_tag.get("content") if published_tag else None,
                "content_hash": sha256(text.encode("utf-8")).hexdigest(),
            }
            
            if chunk_and_store(text, metadata):
                return {"success": True, "title": title, "url": url, "metadata": metadata}
            else:
                 return {"success": False, "error": "Failed to chunk and store content."}
                 
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"HTTP error {e.response.status_code}"}
    except Exception as e:
        logger.exception("crawl_failed", extra={"url": url})
        return {"success": False, "error": str(e)}

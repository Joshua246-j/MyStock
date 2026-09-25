import httpx
import ipaddress
import socket
import logging
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse
from app.rag.ingest import chunk_and_store

ALLOWED_DOMAINS = {
    "yahoo.com", "finance.yahoo.com", "reuters.com", "bloomberg.com", 
    "wsj.com", "cnbc.com", "ft.com", "investopedia.com", "sec.gov"
}
logger = logging.getLogger("stockrag.crawler")

def crawl_url(url: str, timeout: float = 15.0, document_id: int | None = None):
    """Crawls a single URL, extracts text, and stores in RAG."""
    try:
        parsed = urlparse(url)
        domain = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not domain or parsed.username or parsed.password:
            return {"success": False, "error": "Invalid or unsafe URL"}
        if domain.startswith("www."):
            domain = domain[4:]
            
        if domain not in ALLOWED_DOMAINS:
            return {"success": False, "error": f"Domain {domain} is not in the allowlist of trusted financial sources."}
        resolved = socket.getaddrinfo(domain, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        if any(not ipaddress.ip_address(item[4][0]).is_global for item in resolved):
            return {"success": False, "error": "Private or non-public network destinations are not allowed."}
    except Exception as e:
        return {"success": False, "error": f"Invalid URL formatting: {e}"}

    headers = {
        "User-Agent": "Stock-Market-RAG-Bot/1.0"
    }
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.get(url, headers=headers)
            if 300 <= response.status_code < 400:
                return {"success": False, "error": "Redirects are not followed by the research crawler."}
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for script in soup(["script", "style", "nav", "footer", "aside"]):
                script.extract()
                
            text = soup.get_text(separator=' ', strip=True)
            title = soup.title.string if soup.title else url
            
            if not text:
                return {"success": False, "error": "No readable text found on page."}
                
            metadata = {
                "source": title,
                "url": url,
                "document_type": "web",
                "document_id": document_id or 0,
                "retrieved_at": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            
            if chunk_and_store(text, metadata):
                return {"success": True, "title": title, "url": url}
            else:
                 return {"success": False, "error": "Failed to chunk and store content."}
                 
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"HTTP error {e.response.status_code}"}
    except Exception as e:
        logger.exception("crawl_failed", extra={"url": url})
        return {"success": False, "error": str(e)}

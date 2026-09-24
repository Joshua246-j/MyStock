import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse
from app.rag.ingest import chunk_and_store

ALLOWED_DOMAINS = {
    "yahoo.com", "finance.yahoo.com", "reuters.com", "bloomberg.com", 
    "wsj.com", "cnbc.com", "ft.com", "investopedia.com", "sec.gov"
}

def crawl_url(url: str):
    """Crawls a single URL, extracts text, and stores in RAG."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
            
        if domain not in ALLOWED_DOMAINS:
            return {"success": False, "error": f"Domain {domain} is not in the allowlist of trusted financial sources."}
    except Exception as e:
        return {"success": False, "error": f"Invalid URL formatting: {e}"}

    headers = {
        "User-Agent": "Stock-Market-RAG-Bot/1.0"
    }
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
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
                "retrieved_at": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            
            if chunk_and_store(text, metadata):
                return {"success": True, "title": title, "url": url}
            else:
                 return {"success": False, "error": "Failed to chunk and store content."}
                 
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"HTTP error {e.response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

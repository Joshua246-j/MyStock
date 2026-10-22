import sys
import asyncio
import httpx

BASE_URL = "http://127.0.0.1:8000"

async def test_endpoint(client, method, url, **kwargs):
    try:
        if method == "GET":
            resp = await client.get(url, **kwargs)
        elif method == "POST":
            resp = await client.post(url, **kwargs)
        elif method == "PUT":
            resp = await client.put(url, **kwargs)
        elif method == "DELETE":
            resp = await client.delete(url, **kwargs)
        status = resp.status_code
        ok = 200 <= status < 300
        preview = str(resp.text)[:120].replace("\n", " ")
        print(f"[{'PASS' if ok else 'FAIL'}] {method} {url} -> {status} | {preview}")
        return ok
    except Exception as exc:
        print(f"[ERR ] {method} {url} -> {type(exc).__name__}: {exc}")
        return False

async def main():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=50.0) as client:
        endpoints = [
            ("GET", "/api/health"),
            ("GET", "/api/models"),
            ("GET", "/api/settings"),
            ("GET", "/api/symbols/popular"),
            ("GET", "/api/symbols/resolve?symbol=AAPL"),
            ("GET", "/api/stocks/AAPL"),
            ("GET", "/api/stocks/AAPL/quote"),
            ("GET", "/api/stocks/AAPL/history?period=1mo"),
            ("GET", "/api/stocks/AAPL/news"),
            ("GET", "/api/stocks/AAPL/technical"),
            ("GET", "/api/stocks/AAPL/financials"),
            ("GET", "/api/news?limit=10"),
            ("GET", "/api/documents"),
            ("GET", "/api/chat/sessions?limit=10"),
        ]
        results = []
        for method, url in endpoints:
            res = await test_endpoint(client, method, url)
            results.append(res)
        
        passed = sum(results)
        total = len(results)
        print(f"\nTotal: {passed}/{total} endpoints passed.")

if __name__ == "__main__":
    asyncio.run(main())

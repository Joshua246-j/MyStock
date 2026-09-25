import urllib.request
import json
import logging
from bs4 import BeautifulSoup
from typing import Dict, Any, List
from datetime import datetime
from app.market.providers.base import MarketDataProvider

logger = logging.getLogger("stockrag.market.finviz")

class FinvizProvider(MarketDataProvider):
    """
    A market data provider that scrapes Finviz.com for premium fundamentals,
    company profile, and recent news without requiring API keys.
    """
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        }

    def _get_html(self, symbol: str) -> BeautifulSoup:
        # Finviz only supports US symbols generally, drop non-US extensions or try them
        clean_symbol = symbol.split('.')[0].upper()
        url = f"https://finviz.com/quote.ashx?t={clean_symbol}"
        req = urllib.request.Request(url, headers=self.headers)
        response = urllib.request.urlopen(req, timeout=10)
        html = response.read().decode('utf-8')
        return BeautifulSoup(html, 'html.parser')

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported for real-time quotes", "source": "finviz"}

    def get_history(self, symbol: str, period: str = "1mo", interval: str = "1d") -> Dict[str, Any]:
        return {"success": False, "error": "Not supported for history", "source": "finviz"}

    def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        try:
            soup = self._get_html(symbol)
            # Finviz has profile info in standard tables
            name_tag = soup.find('h2', class_='quote-header_ticker-wrapper_company')
            name = name_tag.text.strip() if name_tag else symbol

            links = soup.find_all('a', class_='tab-link')
            sector = "Unknown"
            industry = "Unknown"
            country = "Unknown"
            if len(links) >= 3:
                sector = links[0].text.strip()
                industry = links[1].text.strip()
                country = links[2].text.strip()

            desc_tag = soup.find('div', class_='fullview-profile')
            desc = desc_tag.text.strip() if desc_tag else "No description available."

            return {
                "success": True,
                "symbol": symbol,
                "name": name,
                "sector": sector,
                "industry": industry,
                "description": desc,
                "country": country,
                "source": "finviz"
            }
        except Exception as e:
            logger.warning("finviz_profile_failed", extra={"symbol": symbol, "reason": str(e)})
            return {"success": False, "error": f"Could not fetch profile from finviz: {e}", "source": "finviz"}

    def get_financials(self, symbol: str) -> Dict[str, Any]:
        try:
            soup = self._get_html(symbol)
            # Finviz snapshot table
            snapshot_table = soup.find('table', class_='snapshot-table2')
            if not snapshot_table:
                raise ValueError("Snapshot table not found")

            metrics = {}
            for row in snapshot_table.find_all('tr'):
                cols = row.find_all('td')
                for i in range(0, len(cols), 2):
                    if i + 1 < len(cols):
                        key = cols[i].text.strip()
                        val = cols[i+1].text.strip()
                        if key and val and val != '-':
                            metrics[key] = val

            mapped_metrics = {
                "trailingPE": metrics.get("P/E"),
                "forwardPE": metrics.get("Forward P/E"),
                "priceToBook": metrics.get("P/B"),
                "dividendYield": metrics.get("Dividend %"),
                "returnOnEquity": metrics.get("ROE"),
                "debtToEquity": metrics.get("Debt/Eq"),
                "grossMargins": metrics.get("Gross Margin"),
                "operatingMargins": metrics.get("Oper. Margin"),
                "profitMargin": metrics.get("Profit Margin"),
                "marketCap": metrics.get("Market Cap"),
                "income": metrics.get("Income"),
                "sales": metrics.get("Sales")
            }
            # Remove Nones
            mapped_metrics = {k: v for k, v in mapped_metrics.items() if v is not None}

            return {
                "success": True,
                "symbol": symbol,
                "metrics": mapped_metrics,
                "source": "finviz",
                "retrieved_at": datetime.now().isoformat()
            }
        except Exception as e:
            logger.warning("finviz_financials_failed", extra={"symbol": symbol, "reason": str(e)})
            return {"success": False, "error": f"Could not fetch financials from finviz: {e}", "source": "finviz"}

    def get_balance_sheet(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported", "source": "finviz"}

    def get_cash_flow(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported", "source": "finviz"}

    def get_news(self, symbol: str) -> List[Dict[str, Any]]:
        try:
            soup = self._get_html(symbol)
            news_table = soup.find(id='news-table')
            if not news_table:
                return []
                
            formatted_news = []
            for row in news_table.find_all('tr'):
                a_tag = row.find('a')
                if not a_tag:
                    continue
                    
                title = a_tag.text.strip()
                url = a_tag.get('href', '')
                
                tds = row.find_all('td')
                date_str = tds[0].text.strip() if tds else ""
                
                # Finviz shows "MMM-DD-YY HH:MM" for the first article of the day, then just "HH:MM" for subsequent
                # We'll just pass the raw string since we want to avoid complicated parsing logic here
                
                formatted_news.append({
                    "title": title,
                    "url": url,
                    "publisher": "Finviz Source",
                    "published_at": date_str,
                    "retrieved_at": datetime.now().isoformat(),
                    "ticker": symbol
                })
                
                if len(formatted_news) >= 10:  # Limit to top 10
                    break
                    
            return formatted_news
        except Exception as e:
            logger.warning("finviz_news_failed", extra={"symbol": symbol, "reason": str(e)})
            return []

    def get_dividends(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported", "source": "finviz"}

    def get_splits(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported", "source": "finviz"}

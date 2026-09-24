from abc import ABC, abstractmethod
from typing import Dict, Any, List

class MarketDataProvider(ABC):
    @abstractmethod
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_history(self, symbol: str, period: str = "1mo", interval: str = "1d") -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_financials(self, symbol: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_balance_sheet(self, symbol: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_cash_flow(self, symbol: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_news(self, symbol: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_dividends(self, symbol: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_splits(self, symbol: str) -> Dict[str, Any]:
        pass

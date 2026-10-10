from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class IMarketData(ABC):
    @abstractmethod
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        pass
        
    @abstractmethod
    def get_technical_analysis(self, symbol: str, period: str = "6mo", interval: str = "1d") -> Dict[str, Any]:
        pass
        
    @abstractmethod
    def get_financials(self, symbol: str) -> Dict[str, Any]:
        pass
        
    @abstractmethod
    def get_news(self, symbol: str) -> List[Dict[str, Any]]:
        pass

class IRetriever(ABC):
    @abstractmethod
    def retrieve_context(self, message: str, k: int = 5, document_ids: Optional[List[int]] = None, metadata_filter: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        pass

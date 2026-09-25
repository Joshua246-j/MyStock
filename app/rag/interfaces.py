from abc import ABC, abstractmethod
from typing import List, Dict, Any

class IRetrieverStore(ABC):
    @abstractmethod
    def store(self, texts: List[str], metadatas: List[Dict[str, Any]]) -> bool:
        pass

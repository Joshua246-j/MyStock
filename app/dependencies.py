from typing import Dict, Any
from app.market.service import MarketDataService
from app.market.providers.yfinance_provider import YFinanceProvider
from app.market.providers.finnhub_provider import FinnhubProvider
from app.market.providers.stooq_provider import StooqProvider
from app.market.providers.finviz_provider import FinvizProvider
from app.market.providers.yahoo_api_provider import YahooApiProvider
from app.db.cache import SQLAlchemyCache

cache_impl = SQLAlchemyCache()

def default_settings_provider() -> Dict[str, Any]:
    from app.db.database import SessionLocal
    from app.db.models import UserSettings
    with SessionLocal() as db:
        settings_record = db.query(UserSettings).first()
        if settings_record and settings_record.settings:
            return settings_record.settings
    return {}

market_service = MarketDataService(
    provider=YFinanceProvider(),
    fallback_providers=[FinnhubProvider(), YahooApiProvider(), StooqProvider(), FinvizProvider()],
    cache=cache_impl,
    settings_provider=default_settings_provider
)

from app.analysis.interfaces import IRetriever
from app.rag.retriever import retrieve_context
from app.analysis.prompt_builder import PromptBuilder

class DefaultRetriever(IRetriever):
    def retrieve_context(self, message: str, k: int = 5, document_ids: list = None, metadata_filter: dict | None = None) -> Dict[str, Any]:
        return retrieve_context(message, k=k, document_ids=document_ids, metadata_filter=metadata_filter)

default_retriever = DefaultRetriever()
prompt_builder = PromptBuilder()

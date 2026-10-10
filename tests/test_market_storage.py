from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import PriceBar
from app.market import storage
from app.market.validation import validate_ohlcv_rows
from app.analysis.technical import calculate_indicator_series
import pandas as pd
import pytest
from datetime import datetime, timezone, timedelta


def test_ohlcv_validation_normalizes_and_rejects_conflicting_duplicates():
    valid = {
        "Date": "2026-10-08",
        "Open": 100,
        "High": 110,
        "Low": 95,
        "Close": 105,
        "Volume": 20,
    }
    normalized, error = validate_ohlcv_rows([valid, valid.copy()])
    assert error is None
    assert len(normalized) == 1
    assert normalized[0]["close"] == 105

    invalid = {**valid, "High": 101}
    normalized, error = validate_ohlcv_rows([invalid])
    assert normalized == []
    assert "OHLC consistency" in error

    conflicting = {**valid, "Close": 106}
    normalized, error = validate_ohlcv_rows([valid, conflicting])
    assert normalized == []
    assert "conflicting duplicate" in error


def test_validated_price_bars_persist_and_upsert_without_duplicates(monkeypatch):
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=test_engine)
    monkeypatch.setattr(storage, "engine", test_engine)
    rows, error = validate_ohlcv_rows([{
        "Date": "2026-10-08",
        "Open": 100,
        "High": 110,
        "Low": 95,
        "Close": 105,
        "Adj Close": 104.5,
        "Volume": 20,
    }])
    assert error is None

    assert storage.store_price_bars("AAPL", "1d", "fixture", "HISTORICAL", rows) == 1
    assert storage.store_price_bars("AAPL", "1d", "fixture", "HISTORICAL", rows) == 1
    with test_engine.connect() as connection:
        count = connection.execute(select(func.count()).select_from(PriceBar)).scalar_one()
        bar = connection.execute(select(PriceBar)).first()

    assert count == 1
    assert bar.close == 105
    assert bar.adj_close == 104.5
    assert bar.data_status == "HISTORICAL"
    test_engine.dispose()


def test_offline_price_history_is_returned_stale_and_duplicate_sources_are_collapsed(monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from app.market.service import MarketDataService

    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=test_engine)
    monkeypatch.setattr(storage, "engine", test_engine)
    monkeypatch.setattr(storage, "SessionLocal", sessionmaker(bind=test_engine))
    today = pd.Timestamp.now().normalize()
    bars, error = validate_ohlcv_rows([
        {"Date": (today - pd.Timedelta(days=2)).strftime("%Y-%m-%d"), "Open":100,"High":103,"Low":99,"Close":102,"Volume":1000},
        {"Date": today.strftime("%Y-%m-%d"), "Open":102,"High":105,"Low":101,"Close":104,"Volume":1100},
    ])
    assert error is None
    storage.store_price_bars("AAPL", "1d", "provider-a", "HISTORICAL", bars)
    storage.store_price_bars("AAPL", "1d", "provider-b", "HISTORICAL", bars)

    class UnavailableProvider:
        def get_history(self, *_args, **_kwargs): return {"success":False,"error":"offline"}

    class Cache:
        def get(self, _key): return None
        def set(self, *_args, **_kwargs): raise AssertionError("stale data must not be cached as fresh")
        def delete(self, *_args): pass

    service = MarketDataService(provider=UnavailableProvider(), fallback_providers=[], cache=Cache(), settings_provider=lambda:{"cache_ttl":30})
    result = service.get_history("AAPL", "1mo", "1d", refresh=True)

    assert result["success"] is True
    assert result["data_status"] == "STALE"
    assert result["status"] == "STALE"
    assert len(result["data"]) == 2
    assert result["indicators"]["success"] is True
    test_engine.dispose()


def test_chart_indicator_series_are_python_calculated_and_chart_ready():
    closes = [100 + day for day in range(30)]
    frame = pd.DataFrame({
        "Date": pd.date_range("2026-01-01", periods=len(closes)).strftime("%Y-%m-%d"),
        "Open": closes,
        "High": [value + 2 for value in closes],
        "Low": [value - 2 for value in closes],
        "Close": closes,
        "Volume": [1000 + day for day in range(len(closes))],
    })

    result = calculate_indicator_series(frame)

    assert result["success"] is True
    assert len(result["data"]) == 30
    assert result["data"][-1]["time"] == "2026-01-30"
    assert result["data"][-1]["sma20"] == 119.5
    assert result["data"][-1]["rsi14"] > 99
    assert result["data"][-1]["volume"] == 1029
    assert result["data"][-1]["macd_hist"] == pytest.approx(result["data"][-1]["macd"] - result["data"][-1]["macd_signal"])


def test_structured_fundamentals_and_deduplicated_news_persist_for_offline_fallback(monkeypatch):
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=test_engine)
    monkeypatch.setattr(storage, "engine", test_engine)
    monkeypatch.setattr(storage, "SessionLocal", sessionmaker(bind=test_engine))

    assert storage.store_fundamentals("AAPL", "fixture", {"trailingPE": 28.5, "returnOnEquity": 0.32, "invalid": float("nan")}) == 2
    assert storage.store_fundamentals("AAPL", "fixture", {"trailingPE": 29.0}) == 1
    fundamentals = storage.read_fundamentals("AAPL")
    assert fundamentals["metrics"] == {"trailingPE": 29.0, "returnOnEquity": 0.32}
    assert fundamentals["data_status"] == "STALE"

    item = {"title": "AAPL quarterly update", "url": "https://news.example.test/aapl", "publisher": "Example", "published_at": "2026-10-08T10:00:00Z", "summary": "Company results update.", "image": "https://news.example.test/aapl.jpg", "related_tickers": ["AAPL"]}
    assert storage.store_news("AAPL", [item, item]) == 1
    news = storage.read_news("AAPL")
    assert len(news) == 1
    assert news[0]["ticker"] == "AAPL"
    assert news[0]["published_at"].startswith("2026-10-08T10:00:00")
    assert news[0]["summary"] == "Company results update."
    assert news[0]["image"] == "https://news.example.test/aapl.jpg"
    assert news[0]["related_tickers"] == ["AAPL"]
    test_engine.dispose()


def test_news_normalization_sorts_rss_dates_and_rejects_unsafe_links_and_images():
    items = storage.normalize_news_items([
        {"title": "Older", "url": "https://news.example.test/old", "published_at": "Wed, 07 Oct 2026 10:00:00 GMT", "image": "javascript:alert(1)"},
        {"title": "Newer", "url": "https://news.example.test/new", "published_at": "Thu, 08 Oct 2026 10:00:00 GMT", "image": "https://images.example.test/new.jpg"},
        {"title": "Unsafe", "url": "javascript:alert(1)"},
    ])

    assert [item["title"] for item in items] == ["Newer", "Older"]
    assert items[0]["published_at"].startswith("2026-10-08T10:00:00")
    assert items[0]["image"].startswith("https://")
    assert items[1]["image"] is None


def test_news_normalization_rejects_future_publication_timestamps():
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    items = storage.normalize_news_items([{
        "title": "Provider timestamp is in the future",
        "url": "https://news.example.test/future",
        "published_at": future,
    }])

    assert len(items) == 1
    assert items[0]["published_at"] is None
    assert items[0]["publication_time_status"] == "future_timestamp_rejected"


def test_market_service_returns_labeled_stale_structured_fundamentals_and_news(monkeypatch):
    from app.market.service import MarketDataService

    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=test_engine)
    monkeypatch.setattr(storage, "engine", test_engine)
    monkeypatch.setattr(storage, "SessionLocal", sessionmaker(bind=test_engine))
    storage.store_fundamentals("AAPL", "fixture", {"trailingPE": 25.0})
    storage.store_news("AAPL", [{"title":"Prior update", "url":"https://news.example.test/prior", "publisher":"Fixture", "related_tickers":["AAPL"]}])

    class UnavailableProvider:
        def get_financials(self, _symbol): return {"success":False, "error":"offline"}
        def get_news(self, _symbol): return []

    class Cache:
        def get(self, _key): return None
        def set(self, *_args, **_kwargs): pass
        def delete(self, *_args): pass

    service = MarketDataService(provider=UnavailableProvider(), fallback_providers=[UnavailableProvider()], cache=Cache(), settings_provider=lambda: {"cache_ttl":30})
    fundamentals = service.get_financials("AAPL")
    news = service.get_news_result("AAPL")

    assert fundamentals["success"] is True
    assert fundamentals["data_status"] == "STALE"
    assert fundamentals["metrics"]["trailingPE"] == 25.0
    assert news["success"] is True
    assert news["data_status"] == "STALE"
    assert news["news"][0]["title"] == "Prior update"
    test_engine.dispose()


def test_stored_news_hides_legacy_unverified_and_mixed_market_rows(monkeypatch):
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=test_engine)
    monkeypatch.setattr(storage, "engine", test_engine)
    monkeypatch.setattr(storage, "SessionLocal", sessionmaker(bind=test_engine))

    storage.store_news("GOOGL", [
        {"title":"Unverified legacy headline", "url":"https://news.example.test/legacy", "publisher":"Example"},
        {"title":"General market headline", "url":"https://news.example.test/finviz", "publisher":"Finviz Source", "related_tickers":["GOOGL"]},
        {"title":"Google company update", "url":"https://news.example.test/google", "publisher":"Example", "related_tickers":["GOOGL"]},
    ])

    news = storage.read_news("GOOGL")

    assert [item["title"] for item in news] == ["Google company update"]
    test_engine.dispose()


def test_news_refresh_bypasses_cache_and_fetches_current_provider_result(monkeypatch):
    from app.market.service import MarketDataService

    monkeypatch.setattr(storage, "store_news", lambda *_args, **_kwargs: 0)

    cached = [{"title": "Cached headline", "url": "https://news.example.test/cached", "related_tickers":["AAPL"]}]
    fresh = [{"title": "Fresh headline", "url": "https://news.example.test/fresh", "related_tickers":["AAPL"]}]

    class Cache:
        def get(self, _key): return cached
        def set(self, *_args, **_kwargs): pass

    class Provider:
        calls = 0
        def get_news(self, _symbol):
            self.calls += 1
            return fresh

    provider = Provider()
    service = MarketDataService(provider=provider, fallback_providers=[], cache=Cache(), settings_provider=lambda: {"cache_ttl":300})

    normal = service.get_news_result("AAPL")
    refreshed = service.get_news_result("AAPL", refresh=True)

    assert normal["news"] == cached
    assert normal["source"] == "cached"
    assert refreshed["news"][0]["title"] == fresh[0]["title"]
    assert refreshed["news"][0]["related_tickers"] == ["AAPL"]
    assert refreshed["source"] == "Provider"
    assert provider.calls == 1


def test_market_news_skips_providers_without_company_ticker_evidence(monkeypatch):
    from app.market.service import MarketDataService

    monkeypatch.setattr(storage, "store_news", lambda *_args, **_kwargs: 0)
    class Cache:
        def get(self, _key): return None
        def set(self, *_args, **_kwargs): pass
    class UnverifiedProvider:
        supports_company_news = False
        calls = 0
        def get_news(self, _symbol):
            self.calls += 1
            return [{"title":"Unrelated headline", "url":"https://news.example.test/unrelated", "ticker":"AAPL"}]
    class VerifiedProvider:
        supports_company_news = True
        def get_news(self, _symbol):
            return [{"title":"AAPL company update", "url":"https://news.example.test/aapl", "ticker":"AAPL", "related_tickers":["AAPL"]}]

    primary = UnverifiedProvider()
    fallback = VerifiedProvider()
    service = MarketDataService(provider=primary, fallback_providers=[primary, fallback], cache=Cache(), settings_provider=lambda: {"cache_ttl":30})

    result = service.get_news_result("AAPL", refresh=True)

    assert primary.calls == 0
    assert result["source"] == "VerifiedProvider"
    assert result["news"][0]["related_tickers"] == ["AAPL"]


def test_quote_refresh_bypasses_market_cache():
    from app.market.service import MarketDataService

    class Cache:
        def get(self, _key): return {"success":True,"price":10,"status":"CACHED"}
        def set(self, *_args, **_kwargs): pass
        def delete(self, *_args): pass

    class Provider:
        calls = 0
        def get_quote(self, _symbol):
            self.calls += 1
            return {"success":True,"price":11,"source":"fixture","data_status":"UNVERIFIED_FRESHNESS"}

    provider = Provider()
    service = MarketDataService(provider=provider, fallback_providers=[], cache=Cache(), settings_provider=lambda:{"cache_ttl":30})

    result = service.get_quote("AAPL", refresh=True)

    assert result["price"] == 11
    assert result["status"] == "UNVERIFIED_FRESHNESS"
    assert provider.calls == 1

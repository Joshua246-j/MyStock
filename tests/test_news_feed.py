from datetime import datetime, timedelta, timezone

from app.market import news_feed


def test_feed_merges_fresh_publisher_and_company_news(monkeypatch):
    published = datetime.now(timezone.utc).isoformat()
    rss_story = {
        "title": "Apple reports quarterly results",
        "url": "https://news.google.com/rss/articles/apple-results",
        "publisher": "Reuters",
        "publisher_url": "https://www.reuters.com/",
        "snippet": "Apple published its quarterly results.",
        "image": None,
        "published_at": published,
    }

    def fake_search(query, _limit, _timeout):
        if "Apple" in query:
            return [rss_story]
        if "India" in query:
            return [{**rss_story, "title": "India market update", "url": "https://news.google.com/rss/articles/india-market", "publisher": "Business Standard"}]
        return [{**rss_story, "title": "US market update", "url": "https://news.google.com/rss/articles/us-market", "publisher": "Associated Press"}]

    class FakeMarketService:
        def get_news_result(self, symbol, refresh):
            assert refresh is True
            return {"source": "YahooApiProvider", "news": [{
                "title": rss_story["title"], "url": "https://finance.yahoo.com/apple-results",
                "publisher": "Reuters", "summary": "Company supplied story excerpt",
                "image": "https://images.reuters.com/apple.jpg", "published_at": published,
                "related_tickers": [symbol],
            }, {
                "title": "Unverified social commentary", "url": "https://example.com/commentary",
                "publisher": "Stocktwits", "summary": "A social post, not a newsroom story.",
                "published_at": published,
            }]}

    monkeypatch.setattr(news_feed, "search_web", fake_search)
    monkeypatch.setattr("app.dependencies.market_service", FakeMarketService())

    result = news_feed.get_news_feed(["AAPL"], limit=30)

    assert result["success"] is True
    assert result["total_available"] == 3
    company_story = next(item for item in result["news"] if item["ticker"] == "AAPL")
    assert company_story["publisher"] == "Reuters"
    assert company_story["image"] == "https://images.reuters.com/apple.jpg"
    assert company_story["summary"] == "Company supplied story excerpt"
    assert company_story["feed_source"] == "YahooApiProvider"
    assert all(item["publisher"] != "Stocktwits" for item in result["news"])
    assert any(item["market"] == "us" and item["ticker"] is None for item in result["news"])
    assert result["retrieved_at"]


def test_feed_discards_stale_stories_and_invalid_symbols(monkeypatch):
    old = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    monkeypatch.setattr(news_feed, "search_web", lambda *_args: [{
        "title": "Old market article", "url": "https://news.google.com/rss/articles/old",
        "publisher": "Reuters", "publisher_url": "https://reuters.com", "published_at": old,
    }])

    class EmptyMarketService:
        def get_news_result(self, *_args, **_kwargs):
            return {"news": []}

    monkeypatch.setattr("app.dependencies.market_service", EmptyMarketService())

    result = news_feed.get_news_feed(["AAPL", "bad ticker!"], market="us", limit=40)

    assert result["news"] == []
    assert result["total_available"] == 0
    assert result["data_status"] == "UNAVAILABLE"

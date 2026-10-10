from datetime import datetime, timezone

from app.market.providers.yahoo_api_provider import YahooApiProvider


def test_yahoo_news_filters_unrelated_ticker_tags_and_converts_epoch_to_utc(monkeypatch):
    published = 1_791_620_494
    payload = {
        "quotes": [{"symbol": "AAPL", "shortname": "Apple Inc.", "longname": "Apple Inc."}],
        "news": [
            {
                "title": "Solana addresses surge as the token drops",
                "link": "https://finance.yahoo.com/crypto/solana",
                "publisher": "Example",
                "providerPublishTime": published,
                "relatedTickers": ["SOL-USD", "AAPL"],
            },
            {
                "title": "Why Apple (AAPL) shares moved today",
                "link": "https://finance.yahoo.com/stocks/apple",
                "publisher": "Example",
                "providerPublishTime": published,
                "relatedTickers": ["AAPL"],
            },
            {
                "title": "Microsoft earnings preview",
                "link": "https://finance.yahoo.com/stocks/microsoft",
                "publisher": "Example",
                "providerPublishTime": published,
                "relatedTickers": ["MSFT"],
            },
        ],
    }
    provider = YahooApiProvider()
    monkeypatch.setattr(provider, "_fetch", lambda _url: payload)

    result = provider.get_news("AAPL")

    assert [item["title"] for item in result] == ["Why Apple (AAPL) shares moved today"]
    assert result[0]["ticker"] == "AAPL"
    assert result[0]["related_tickers"] == ["AAPL"]
    assert result[0]["published_at"] == datetime.fromtimestamp(published, timezone.utc).isoformat()
    assert datetime.fromisoformat(result[0]["published_at"]).utcoffset().total_seconds() == 0

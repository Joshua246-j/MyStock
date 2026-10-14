"""SQLite persistence for validated OHLCV bars."""
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from hashlib import sha256
import math
from urllib.parse import urlparse

from sqlalchemy.dialects.sqlite import insert

from app.db.database import engine, SessionLocal
from app.db.models import FundamentalMetric, NewsArticle, PriceBar


def read_price_bars(symbol: str, interval: str = "1d", period: str = "1mo") -> dict:
    """Return recent validated local bars for a transparent offline fallback."""
    days = {"1mo": 35, "3mo": 100, "6mo": 200, "1y": 400, "2y": 800, "5y": 1900}.get(period, 35)
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    with SessionLocal() as db:
        rows = (db.query(PriceBar)
                .filter(PriceBar.symbol == symbol, PriceBar.interval == interval, PriceBar.bar_at >= cutoff)
                .order_by(PriceBar.bar_at.desc(), PriceBar.retrieved_at.desc())
                .limit(2100)
                .all())
    if not rows:
        return {"success": False, "data": []}
    unique_rows = {}
    for row in rows:
        unique_rows.setdefault(row.bar_at, row)
    rows = sorted(unique_rows.values(), key=lambda row: row.bar_at)
    return {
        "success": True,
        "symbol": symbol,
        "period": period,
        "interval": interval,
        "data": [{"Date": row.bar_at.isoformat(), "Open": row.open, "High": row.high,
                  "Low": row.low, "Close": row.close, "Adj Close": row.adj_close, "Volume": row.volume}
                 for row in rows],
        "source": f"SQLite offline fallback ({rows[-1].source})",
        "timestamp": max(row.retrieved_at for row in rows).isoformat(),
        "retrieved_at": max(row.retrieved_at for row in rows).isoformat(),
        "last_bar_at": rows[-1].bar_at.isoformat(),
        "data_status": "STALE",
        "status": "STALE",
    }


def store_price_bars(symbol: str, interval: str, source: str, data_status: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    retrieved_at = datetime.now(timezone.utc).replace(tzinfo=None)
    table = PriceBar.__table__
    values = [
        {
            "symbol": symbol,
            "bar_at": row["bar_at"],
            "interval": interval,
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "adj_close": row["adj_close"],
            "volume": row["volume"],
            "source": source,
            "retrieved_at": retrieved_at,
            "data_status": data_status,
        }
        for row in rows
    ]
    statement = insert(table).values(values)
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.symbol, table.c.bar_at, table.c.interval, table.c.source],
        set_={
            "open": statement.excluded.open,
            "high": statement.excluded.high,
            "low": statement.excluded.low,
            "close": statement.excluded.close,
            "adj_close": statement.excluded.adj_close,
            "volume": statement.excluded.volume,
            "retrieved_at": statement.excluded.retrieved_at,
            "data_status": statement.excluded.data_status,
        },
    )
    with engine.begin() as connection:
        connection.execute(statement)
    return len(values)


def _parse_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        try:
            parsed = parsedate_to_datetime(str(value))
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def normalize_news_items(items: list[dict], limit: int = 50) -> list[dict]:
    """Validate news links/media, reject impossible future dates, dedupe and sort."""
    by_url: dict[str, tuple[datetime | None, dict]] = {}
    future_cutoff = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5)
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        parsed_url = urlparse(url)
        if not title or parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname or parsed_url.username or parsed_url.password:
            continue
        item["title"] = title[:1000]
        item["url"] = url
        if item.get("published_at"):
            published = _parse_datetime(item["published_at"])
            if published:
                if published > future_cutoff:
                    published = None
                    item["published_at"] = None
                    item["publication_time_status"] = "future_timestamp_rejected"
                else:
                    item["published_at"] = published.replace(tzinfo=timezone.utc).isoformat()
        else:
            published = None
        if item.get("image"):
            image = str(item["image"]).strip()
            image_url = urlparse(image)
            item["image"] = image if image_url.scheme == "https" and image_url.hostname and not image_url.username and not image_url.password else None
        related = item.get("related_tickers")
        item_ticker = str(item.get("ticker") or item.get("symbol") or "").strip().upper()
        if isinstance(related, (list, tuple, set)):
            related_set = {str(value).strip().upper() for value in related if str(value).strip()}
        else:
            related_set = set()
        if item_ticker:
            related_set.add(item_ticker)
        item["related_tickers"] = sorted(related_set)
        key = url.split("#", 1)[0]
        existing = by_url.get(key)
        if existing is None or (existing[0] is None and published is not None):
            by_url[key] = (published, item)
    ordered = sorted(by_url.values(), key=lambda entry: (entry[0] is not None, entry[0] or datetime.min), reverse=True)
    return [item for _, item in ordered[:max(1, min(int(limit), 100))]]


def store_fundamentals(symbol: str, source: str, metrics: dict, data_status: str = "UNVERIFIED_FRESHNESS") -> int:
    valid = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for metric, raw in metrics.items():
        try:
            value = float(raw)
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(value):
            continue
        valid.append({"symbol": symbol, "metric": str(metric), "value": value, "period": "latest", "source": source,
                      "retrieved_at": now, "data_status": data_status})
    if not valid:
        return 0
    table = FundamentalMetric.__table__
    statement = insert(table).values(valid)
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.symbol, table.c.metric, table.c.period, table.c.source],
        set_={"value": statement.excluded.value, "retrieved_at": statement.excluded.retrieved_at,
              "data_status": statement.excluded.data_status},
    )
    with engine.begin() as connection:
        connection.execute(statement)
    return len(valid)


def read_fundamentals(symbol: str) -> dict:
    with SessionLocal() as db:
        rows = db.query(FundamentalMetric).filter(FundamentalMetric.symbol == symbol).order_by(FundamentalMetric.retrieved_at.desc()).all()
    latest = {}
    for row in rows:
        latest.setdefault(row.metric, row)
    if not latest:
        return {"success": False, "metrics": {}}
    most_recent = max(row.retrieved_at for row in latest.values())
    return {"success": True, "symbol": symbol, "metrics": {metric: row.value for metric, row in latest.items()},
            "source": ", ".join(sorted({row.source for row in latest.values()})), "retrieved_at": most_recent.isoformat(),
            "data_status": "STALE"}


def store_news(symbol: str, news: list[dict]) -> int:
    table = NewsArticle.__table__
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    values_by_url = {}
    for item in news:
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        parsed_url = urlparse(url)
        if not title or parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            continue
        published = _parse_datetime(item.get("published_at"))
        ticker = str(item.get("ticker") or symbol)
        digest = sha256(f"{ticker}|{url}|{title}|{published.isoformat() if published else ''}".encode("utf-8")).hexdigest()
        related = item.get("related_tickers")
        related_tickers = sorted({str(value).strip().upper() for value in related if str(value).strip()}) if isinstance(related, (list, tuple, set)) else []
        values_by_url[url] = {"title": title[:1000],
                              "publisher": str(item.get("publisher") or "")[:200] or None,
                              "related_tickers": related_tickers,
                              "summary": str(item.get("summary") or "")[:4000] or None,
                              "image": str(item.get("image") or "")[:2000] or None, "url": url,
                              "published_at": published, "retrieved_at": now, "content_hash": digest,
                              "sentiment": None, "sentiment_score": None}
    values = list(values_by_url.values())
    if not values:
        return 0
    statement = insert(table).values(values)
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.url],
        set_={"title": statement.excluded.title, "publisher": statement.excluded.publisher,
              "related_tickers": statement.excluded.related_tickers,
              "summary": statement.excluded.summary, "image": statement.excluded.image,
              "published_at": statement.excluded.published_at, "retrieved_at": statement.excluded.retrieved_at,
              "content_hash": statement.excluded.content_hash},
    ).returning(table.c.id, table.c.url)
    with engine.begin() as connection:
        result = connection.execute(statement).mappings().all()
        assoc_values = []
        for row in result:
            article_id = row['id']
            url = row['url']
            for t in values_by_url[url]["related_tickers"]:
                assoc_values.append({"article_id": article_id, "ticker": t})
        if assoc_values:
            from app.db.models import news_article_tickers
            assoc_statement = insert(news_article_tickers).values(assoc_values).on_conflict_do_nothing()
            connection.execute(assoc_statement)
    return len(values)


def read_news(symbol: str, limit: int = 20) -> list[dict]:
    normalized_symbol = symbol.strip().upper()
    with SessionLocal() as db:
        from app.db.models import news_article_tickers
        rows = db.query(NewsArticle).join(
            news_article_tickers, NewsArticle.id == news_article_tickers.c.article_id
        ).filter(
            news_article_tickers.c.ticker == normalized_symbol
        ).order_by(NewsArticle.published_at.desc(), NewsArticle.retrieved_at.desc()).all()
    verified_rows = [row for row in rows
                     if (row.publisher or "").casefold() != "finviz source"]
    return [{"title": row.title, "url": row.url, "publisher": row.publisher,
             "related_tickers": row.related_tickers or [],
             "summary": row.summary, "image": row.image,
             "published_at": row.published_at.isoformat() if row.published_at else None,
             "retrieved_at": row.retrieved_at.isoformat(), "ticker": normalized_symbol,
             "content_hash": row.content_hash, "sentiment": row.sentiment,
             "sentiment_score": row.sentiment_score} for row in verified_rows[:max(1, min(int(limit), 100))]]

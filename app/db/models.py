from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON, UniqueConstraint, Table, ForeignKey
from app.db.database import Base
import datetime


def utcnow_naive() -> datetime.datetime:
    """Return UTC with SQLite-compatible naive timestamps for existing columns."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=utcnow_naive)
    parent_session_id = Column(String, nullable=True, index=True)
    branch_from_message_id = Column(Integer, nullable=True)
    document_ids = Column(JSON, nullable=False, default=list)
    dataset_id = Column(Integer, nullable=True)
    title = Column(String(200), nullable=True)
    is_pinned = Column(Integer, default=0, nullable=False)

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)
    role = Column(String)  # 'user' or 'assistant'
    content = Column(Text)
    created_at = Column(DateTime, default=utcnow_naive)
    sources = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)

class DocumentMetadata(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    document_type = Column(String)
    storage_path = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    uploaded_at = Column(DateTime, default=utcnow_naive)
    status = Column(String) # 'processing', 'completed', 'failed'

class PriceBar(Base):
    __tablename__ = "price_bars"
    __table_args__ = (UniqueConstraint("symbol", "bar_at", "interval", "source", name="uq_price_bar_identity"),)

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    bar_at = Column(DateTime, nullable=False, index=True)
    interval = Column(String, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    adj_close = Column(Float, nullable=True)
    volume = Column(Float, nullable=False)
    source = Column(String, nullable=False)
    retrieved_at = Column(DateTime, nullable=False, default=utcnow_naive)
    data_status = Column(String, nullable=False, default="UNKNOWN")

class FundamentalMetric(Base):
    __tablename__ = "fundamental_metrics"
    __table_args__ = (UniqueConstraint("symbol", "metric", "period", "source", name="uq_fundamental_metric_identity"),)

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    metric = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    units = Column(String, nullable=True)
    currency = Column(String, nullable=True)
    fiscal_period = Column(String, nullable=True)
    period = Column(String, nullable=False, default="latest")
    source = Column(String, nullable=False)
    retrieved_at = Column(DateTime, nullable=False, default=utcnow_naive)
    data_status = Column(String, nullable=False, default="UNVERIFIED_FRESHNESS")

news_article_tickers = Table(
    "news_article_tickers",
    Base.metadata,
    Column("article_id", Integer, ForeignKey("news_articles.id", ondelete="CASCADE"), primary_key=True),
    Column("ticker", String, primary_key=True, index=True)
)

class NewsArticle(Base):
    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    publisher = Column(String, nullable=True)
    related_tickers = Column(JSON, nullable=False, default=list)
    summary = Column(String, nullable=True)
    image = Column(String, nullable=True)
    url = Column(String, nullable=False, unique=True, index=True)
    published_at = Column(DateTime, nullable=True, index=True)
    retrieved_at = Column(DateTime, nullable=False, default=utcnow_naive)
    content_hash = Column(String, nullable=False, index=True)
    sentiment = Column(String, nullable=True)
    sentiment_score = Column(Float, nullable=True)

class CacheEntry(Base):
    __tablename__ = "cache_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)
    value = Column(JSON)
    created_at = Column(DateTime, default=utcnow_naive)
    expires_at = Column(DateTime)
    source = Column(String)

class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    settings = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)


class ForecastRecord(Base):
    __tablename__ = "forecast_records"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    horizon = Column(Integer, nullable=False)
    model_name = Column(String, nullable=False)
    reference_price = Column(Float, nullable=False)
    reference_date = Column(String, nullable=False)
    target_date = Column(String, nullable=False)
    expected_price = Column(Float, nullable=False)
    expected_return_percent = Column(Float, nullable=False)
    lower_bound_price = Column(Float, nullable=False)
    upper_bound_price = Column(Float, nullable=False)
    confidence_percent = Column(Integer, nullable=False, default=80)
    directional_prob = Column(Float, nullable=True)
    directional_label = Column(String, nullable=True)
    val_mae_percent = Column(Float, nullable=True)
    val_rmse_percent = Column(Float, nullable=True)
    val_sample_size = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default="pending")  # pending, evaluated, abstain
    realized_price = Column(Float, nullable=True)
    realized_error = Column(Float, nullable=True)
    realized_error_percent = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utcnow_naive)
    metadata_json = Column(JSON, nullable=False, default=dict)


class UserMemory(Base):
    __tablename__ = "user_memories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, default="default_user", index=True, nullable=False)
    key = Column(String(100), nullable=False, index=True)
    value = Column(Text, nullable=False)
    category = Column(String(50), default="preference", nullable=False)  # "preference", "constraint", "watchlist", "context"
    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)
    metadata_json = Column(JSON, nullable=False, default=dict)


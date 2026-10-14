from abc import ABC, abstractmethod
from typing import Optional, Any
import datetime
import logging
import math
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.db.database import SessionLocal
from app.db.models import CacheEntry

logger = logging.getLogger("stockrag.cache")


def _utcnow_naive():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return _json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return value

class CacheInterface(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: int = 300, source: str = "cache") -> None:
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        pass

class SQLAlchemyCache(CacheInterface):
    def get(self, key: str) -> Optional[Any]:
        with SessionLocal() as db:
            entry = db.query(CacheEntry).filter(CacheEntry.key == key).first()
            if entry:
                if entry.expires_at > _utcnow_naive():
                    logger.info("cache_hit", extra={"cache_key": key, "source": entry.source})
                    return entry.value
                else:
                    db.delete(entry)
                    db.commit()
            logger.info("cache_miss", extra={"cache_key": key})
            return None

    def set(self, key: str, value: Any, ttl_seconds: int = 300, source: str = "cache") -> None:
        expires = _utcnow_naive() + datetime.timedelta(seconds=ttl_seconds)
        statement = sqlite_insert(CacheEntry).values(
            key=key,
            value=_json_safe(value),
            expires_at=expires,
            source=source,
        ).on_conflict_do_update(
            index_elements=[CacheEntry.key],
            set_={"value": _json_safe(value), "expires_at": expires, "source": source},
        )
        with SessionLocal() as db:
            db.execute(statement)
            db.commit()

    def delete(self, key: str) -> None:
        with SessionLocal() as db:
            entry = db.query(CacheEntry).filter(CacheEntry.key == key).first()
            if entry:
                db.delete(entry)
                db.commit()

class MemoryCache(CacheInterface):
    def __init__(self):
        self._store = {}
        
    def get(self, key: str) -> Optional[Any]:
        if key in self._store:
            entry = self._store[key]
            if entry["expires_at"] > _utcnow_naive():
                logger.info("cache_hit", extra={"cache_key": key, "source": entry["source"]})
                return entry["value"]
            else:
                del self._store[key]
        logger.info("cache_miss", extra={"cache_key": key})
        return None
        
    def set(self, key: str, value: Any, ttl_seconds: int = 300, source: str = "cache") -> None:
        expires = _utcnow_naive() + datetime.timedelta(seconds=ttl_seconds)
        self._store[key] = {
            "value": _json_safe(value),
            "expires_at": expires,
            "source": source
        }
        
    def delete(self, key: str) -> None:
        if key in self._store:
            del self._store[key]

# Provide backwards compatibility temporarily for tests / unresolved imports
default_cache = SQLAlchemyCache()

def get_cache(key: str):
    return default_cache.get(key)

def set_cache(key: str, value: Any, ttl_seconds: int = 300, source: str = "cache"):
    return default_cache.set(key, value, ttl_seconds, source)

def clear_expired():
    with SessionLocal() as db:
        removed = db.query(CacheEntry).filter(CacheEntry.expires_at <= _utcnow_naive()).delete(synchronize_session=False)
        db.commit()
        return removed

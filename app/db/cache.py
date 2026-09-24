import json
import datetime
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.db.models import CacheEntry

def get_cache(key: str):
    with SessionLocal() as db:
        entry = db.query(CacheEntry).filter(CacheEntry.key == key).first()
        if entry:
            if entry.expires_at > datetime.datetime.utcnow():
                return entry.value
            else:
                db.delete(entry)
                db.commit()
        return None

def set_cache(key: str, value: dict, ttl_seconds: int = 300, source: str = "cache"):
    with SessionLocal() as db:
        expires = datetime.datetime.utcnow() + datetime.timedelta(seconds=ttl_seconds)
        entry = db.query(CacheEntry).filter(CacheEntry.key == key).first()
        if entry:
            entry.value = value
            entry.expires_at = expires
            entry.source = source
        else:
            entry = CacheEntry(key=key, value=value, expires_at=expires, source=source)
            db.add(entry)
        db.commit()

def clear_expired():
    with SessionLocal() as db:
        db.query(CacheEntry).filter(CacheEntry.expires_at <= datetime.datetime.utcnow()).delete()
        db.commit()

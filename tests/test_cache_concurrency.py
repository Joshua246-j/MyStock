from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db import cache as cache_module
from app.db.database import Base
from app.db.models import CacheEntry


def test_cache_upsert_handles_concurrent_writes_to_same_key(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'cache-race.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(cache_module, "SessionLocal", sessionmaker(bind=engine))
    cache = cache_module.SQLAlchemyCache()

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(lambda number: cache.set("same-key", {"writer": number}, ttl_seconds=60), range(36)))

    with engine.connect() as connection:
        count = connection.execute(select(func.count()).select_from(CacheEntry)).scalar_one()
        value = connection.execute(select(CacheEntry.value).where(CacheEntry.key == "same-key")).scalar_one()

    assert count == 1
    assert value["writer"] in range(36)
    engine.dispose()

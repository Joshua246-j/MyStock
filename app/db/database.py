from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, declarative_base
import os

DB_PATH = os.getenv("DB_PATH", "sqlite:///./data/stock_terminal.db")
database_url = make_url(DB_PATH)
connect_args = {}
if database_url.get_backend_name() == "sqlite":
    connect_args["check_same_thread"] = False
    if database_url.database and database_url.database != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(database_url.database)), exist_ok=True)

engine = create_engine(DB_PATH, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

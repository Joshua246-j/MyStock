from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from app.config import PROJECT_ROOT

default_db_path = (PROJECT_ROOT / "data" / "stock_terminal.db").as_posix()
DB_PATH = os.getenv("DB_PATH", f"sqlite:///{default_db_path}")
database_url = make_url(DB_PATH)
connect_args = {}
if database_url.get_backend_name() == "sqlite":
    connect_args["check_same_thread"] = False
    if database_url.database and database_url.database != ":memory:":
        database_file = database_url.database
        if not os.path.isabs(database_file):
            database_file = os.path.join(PROJECT_ROOT, database_file)
        os.makedirs(os.path.dirname(database_file), exist_ok=True)
        DB_PATH = database_url.set(database=database_file).render_as_string(hide_password=False)

engine = create_engine(DB_PATH, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "sqlite:///./broker.db")
    # Render/Heroku podają postgres://, SQLAlchemy 2 wymaga postgresql://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    # Używamy sterownika psycopg 3
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _database_url()
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
# Pula połączeń (test obciążenia 13.11.2026): domyślne 5+10 z czekaniem 30 s zatykało serwer przy
# ~20 jednoczesnych osobach. pool_pre_ping: po uśpieniu darmowego serwera/bazy na Renderze stare
# połączenia bywają zerwane; sprawdzamy je przed użyciem zamiast zwracać błąd pierwszej osobie.
_pool_args = {} if DATABASE_URL.startswith("sqlite") else {
    "pool_size": 10, "max_overflow": 20, "pool_timeout": 15, "pool_pre_ping": True, "pool_recycle": 1800,
}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True, **_pool_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

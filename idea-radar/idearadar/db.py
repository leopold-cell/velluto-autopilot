from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


def utcnow() -> datetime:
    """Naive UTC; SQLite drops tzinfo, so everything is kept naive-UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def make_session_factory(database_url: str) -> sessionmaker[Session]:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)

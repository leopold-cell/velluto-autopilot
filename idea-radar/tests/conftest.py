import pytest

from idearadar.config import Settings
from idearadar.db import make_session_factory


@pytest.fixture
def cfg():
    return Settings(database_url="sqlite://", admin_api_key="k", min_gap_seconds=0)


@pytest.fixture
def session(cfg):
    from sqlalchemy.pool import StaticPool
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from idearadar.models import Base

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(engine, expire_on_commit=False)()
    yield s
    s.close()

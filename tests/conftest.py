"""Shared fixtures for all tests."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.approval import Approval, ApprovalStatus
from app.models.audit import AuditLog
from app.models.kpi import KpiSnapshot
from app.models.rollback import RollbackRecord
from app.models.task import Task, TaskStatus

TEST_DB_URL = "postgresql+asyncpg://velluto:velluto@localhost:5432/velluto_test"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(test_engine):
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db):
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def sample_kpi_snapshot():
    return KpiSnapshot(
        snapshot_date=datetime.now(timezone.utc).date(),
        period="day",
        orders_count=4,
        orders_target=7,
        revenue_eur=596.0,
        aov_eur=149.0,
        ad_spend_eur=85.0,
        ad_roas=7.0,
        ad_cpa_eur=21.25,
        ad_ctr_pct=2.3,
        ad_impressions=12000,
        organic_clicks=45,
        avg_position=14.5,
        sessions=320,
        conversion_rate_pct=1.25,
        cart_abandonment_rate_pct=72.0,
        email_revenue_eur=89.0,
        email_open_rate_pct=28.5,
        raw={},
    )


@pytest.fixture
def sample_approval():
    return Approval(
        action="meta_adjust_campaign_budget",
        module="meta",
        risk_level="high",
        payload={"campaign_id": "123", "new_daily_budget": 120.0, "reason": "ROAS > 3.0"},
        reason="ROAS 3.5 exceeds scale target",
        status=ApprovalStatus.pending,
    )


@pytest.fixture
def mock_whatsapp():
    with patch("app.modules.whatsapp.client.WhatsAppClient") as mock:
        instance = MagicMock()
        instance.send_text = AsyncMock(return_value={"messages": [{"id": "wamid.test"}]})
        instance.send_interactive_buttons = AsyncMock(return_value={"messages": [{"id": "wamid.test"}]})
        mock.return_value = instance
        yield instance


@pytest.fixture
def mock_anthropic():
    with patch("anthropic.AsyncAnthropic") as mock:
        instance = MagicMock()
        mock.return_value = instance
        yield instance

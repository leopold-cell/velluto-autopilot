from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class KpiSnapshot(Base):
    __tablename__ = "kpi_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(16), nullable=False)  # day|week|month

    # Sales
    orders_count: Mapped[int] = mapped_column(Integer, default=0)
    orders_target: Mapped[int] = mapped_column(Integer, default=0)
    revenue_eur: Mapped[float] = mapped_column(Float, default=0.0)
    aov_eur: Mapped[float] = mapped_column(Float, default=0.0)

    # Meta Ads
    ad_spend_eur: Mapped[float] = mapped_column(Float, default=0.0)
    ad_roas: Mapped[float] = mapped_column(Float, default=0.0)
    ad_cpa_eur: Mapped[float] = mapped_column(Float, default=0.0)
    ad_ctr_pct: Mapped[float] = mapped_column(Float, default=0.0)
    ad_impressions: Mapped[int] = mapped_column(Integer, default=0)

    # SEO
    organic_sessions: Mapped[int] = mapped_column(Integer, default=0)
    organic_clicks: Mapped[int] = mapped_column(Integer, default=0)
    avg_position: Mapped[float] = mapped_column(Float, default=0.0)

    # Shopify / CRO
    sessions: Mapped[int] = mapped_column(Integer, default=0)
    conversion_rate_pct: Mapped[float] = mapped_column(Float, default=0.0)
    cart_abandonment_rate_pct: Mapped[float] = mapped_column(Float, default=0.0)

    # Email
    email_revenue_eur: Mapped[float] = mapped_column(Float, default=0.0)
    email_open_rate_pct: Mapped[float] = mapped_column(Float, default=0.0)

    # Raw data for deep analysis
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

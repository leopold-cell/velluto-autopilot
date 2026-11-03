from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class RawItem(Base):
    __tablename__ = "raw_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    url: Mapped[str] = mapped_column(String(1024), unique=True)
    author_handle: Mapped[str] = mapped_column(String(128), default="")
    text: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)


class Problem(Base):
    __tablename__ = "problems"
    id: Mapped[int] = mapped_column(primary_key=True)
    raw_item_id: Mapped[int] = mapped_column(ForeignKey("raw_items.id"))
    summary: Mapped[str] = mapped_column(Text)
    persona: Mapped[str] = mapped_column(String(256), default="")
    affluence: Mapped[float] = mapped_column(Float, default=0.0)  # 0..1, only with verified evidence
    affluence_evidence: Mapped[str] = mapped_column(Text, default="")
    wtp: Mapped[float] = mapped_column(Float, default=0.0)  # 0..1 willingness-to-pay evidence
    wtp_evidence: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Idea(Base):
    __tablename__ = "ideas"
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[datetime] = mapped_column(Date)
    cluster_key: Mapped[str] = mapped_column(String(256), index=True)
    title: Mapped[str] = mapped_column(String(256))
    score: Mapped[float] = mapped_column(Float)
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    card: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|approved|rejected|expired
    price_eur: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[int] = mapped_column(primary_key=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id"))
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|ended|killed
    starts_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    test_days: Mapped[int] = mapped_column(Integer, default=14)
    budget_eur: Mapped[float] = mapped_column(Float, default=100.0)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)  # visitors, signups, preorders, spend_eur


class OutreachMessage(Base):
    __tablename__ = "outreach_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"))
    channel: Mapped[str] = mapped_column(String(16))
    target_handle: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))  # blocked|dry_run|assist|queued|sent
    reason: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Suppression(Base):
    __tablename__ = "suppressions"
    __table_args__ = (UniqueConstraint("channel", "handle"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(16))  # "*" = every channel
    handle: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(String(128), default="")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(256))


class LLMSpend(Base):
    __tablename__ = "llm_spend"
    day: Mapped[datetime] = mapped_column(Date, primary_key=True)
    usd: Mapped[float] = mapped_column(Float, default=0.0)

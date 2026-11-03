"""Every outbound message passes through here before anything is sent.

Design rules (see README): kill switch, dry-run by default, LinkedIn is never automated
(assist queue only), e-mail only to opted-in waitlist members, mandatory disclosure,
per-channel daily caps, minimum gap, suppression list, opt-out detection.
"""
import re
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings
from .db import utcnow
from .models import OutreachMessage, Setting, Suppression

DISCLOSURE_PATTERNS = [
    r"\bich baue (gerade|an)\b", r"\bich arbeite (gerade )?an\b", r"\bwir bauen\b",
    r"\bi'?m building\b", r"\bi am building\b", r"\bi'?m working on\b", r"\bwe'?re building\b",
]
OPT_OUT_PATTERNS = [r"\bstopp?\b", r"\bunsubscribe\b", r"\bnicht mehr schreiben\b", r"\bleave me alone\b", r"\bno thanks\b", r"\bkein interesse\b"]
FORBIDDEN_CLAIMS = [r"\bgarantiert\b", r"\bguaranteed\b", r"\b100 ?% ?(sicher|safe)\b", r"\bkundenstimmen?\b", r"\btestimonial"]
NEVER_AUTOMATED = {"linkedin"}
CAPS = {"x": "cap_x_per_day", "reddit": "cap_reddit_per_day", "email": "cap_email_per_day"}
KNOWN_CHANNELS = {"x", "reddit", "email", "linkedin"}


@dataclass
class Decision:
    allowed: bool
    mode: str  # blocked | dry_run | assist | live
    reason: str = ""


def has_disclosure(body: str) -> bool:
    return any(re.search(p, body, re.I) for p in DISCLOSURE_PATTERNS)


def is_opt_out(text: str) -> bool:
    return any(re.search(p, text, re.I) for p in OPT_OUT_PATTERNS)


def qa_check(body: str) -> str | None:
    """Deterministic content QA. Returns a blocking reason or None."""
    if len(body.strip()) < 20:
        return "message too short"
    if len(body) > 1200:
        return "message too long"
    if not has_disclosure(body):
        return "missing disclosure (must say that you are building something)"
    for p in FORBIDDEN_CLAIMS:
        if re.search(p, body, re.I):
            return f"forbidden claim pattern: {p}"
    return None


class Guardrails:
    def __init__(self, session: Session, settings: Settings):
        self.s = session
        self.cfg = settings

    # --- kill switch (runtime toggle in DB, env var is the floor) ---
    def kill_switch_on(self) -> bool:
        row = self.s.get(Setting, "kill_switch")
        return self.cfg.kill_switch or (row is not None and row.value == "1")

    def set_kill_switch(self, enabled: bool) -> None:
        row = self.s.get(Setting, "kill_switch")
        if row is None:
            self.s.add(Setting(key="kill_switch", value="1" if enabled else "0"))
        else:
            row.value = "1" if enabled else "0"
        self.s.commit()

    def suppress(self, channel: str, handle: str, reason: str = "") -> None:
        exists = self.s.scalar(select(Suppression).where(Suppression.channel == channel, Suppression.handle == handle))
        if not exists:
            self.s.add(Suppression(channel=channel, handle=handle, reason=reason))
            self.s.commit()

    def _suppressed(self, channel: str, handle: str) -> bool:
        stmt = select(Suppression.id).where(Suppression.handle == handle, Suppression.channel.in_([channel, "*"]))
        return self.s.scalar(stmt) is not None

    def _sent_today(self, channel: str) -> int:
        start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(func.count()).select_from(OutreachMessage).where(
            OutreachMessage.channel == channel,
            OutreachMessage.created_at >= start,
            OutreachMessage.status.in_(["queued", "sent", "dry_run"]),
        )
        return self.s.scalar(stmt) or 0

    def _last_message_age_ok(self, channel: str) -> bool:
        last = self.s.scalar(
            select(OutreachMessage.created_at)
            .where(OutreachMessage.channel == channel, OutreachMessage.status.in_(["queued", "sent", "dry_run"]))
            .order_by(OutreachMessage.created_at.desc())
            .limit(1)
        )
        return last is None or utcnow() - last >= timedelta(seconds=self.cfg.min_gap_seconds)

    def check(self, channel: str, handle: str, body: str, *, opted_in: bool = False) -> Decision:
        channel = channel.lower()
        if self.kill_switch_on():
            return Decision(False, "blocked", "kill switch is on")
        if channel not in KNOWN_CHANNELS:
            return Decision(False, "blocked", f"unknown channel {channel}")
        if self._suppressed(channel, handle):
            return Decision(False, "blocked", "recipient is on the suppression list")
        if reason := qa_check(body):
            return Decision(False, "blocked", reason)
        if channel == "email" and not opted_in:
            return Decision(False, "blocked", "e-mail only to double-opt-in waitlist members (UWG §7)")
        if channel in NEVER_AUTOMATED:
            return Decision(True, "assist", "linkedin is never automated: human sends from the assist queue")
        cap = getattr(self.cfg, CAPS[channel])
        if self._sent_today(channel) >= cap:
            return Decision(False, "blocked", f"daily cap {cap} reached for {channel}")
        if not self._last_message_age_ok(channel):
            return Decision(False, "blocked", "minimum gap between messages not reached")
        if self.cfg.dry_run or channel not in self.cfg.live_channel_set:
            return Decision(True, "dry_run", "dry run (global DRY_RUN or channel not in LIVE_CHANNELS)")
        return Decision(True, "live", "")

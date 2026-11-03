from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .guardrails import Guardrails, is_opt_out
from .models import OutreachMessage

STATUS = {"blocked": "blocked", "dry_run": "dry_run", "assist": "assist", "live": "queued"}


def queue_outreach(session: Session, cfg: Settings, experiment_id: int, channel: str, handle: str, body: str,
                   *, opted_in: bool = False) -> OutreachMessage:
    """Validates a message and stores it. Nothing is sent here: a sender worker picks up 'queued'
    rows (not implemented yet), humans work the 'assist' queue, 'dry_run' rows are only logged."""
    d = Guardrails(session, cfg).check(channel, handle, body, opted_in=opted_in)
    msg = OutreachMessage(experiment_id=experiment_id, channel=channel.lower(), target_handle=handle, body=body,
                          status=STATUS[d.mode], reason=d.reason)
    session.add(msg)
    session.commit()
    return msg


def handle_reply(session: Session, cfg: Settings, channel: str, handle: str, text: str) -> bool:
    """Any opt-out reply suppresses the person on every channel."""
    if is_opt_out(text):
        Guardrails(session, cfg).suppress("*", handle, "opt-out reply")
        return True
    return False


def assist_queue(session: Session) -> list[OutreachMessage]:
    return list(session.scalars(select(OutreachMessage).where(OutreachMessage.status == "assist").order_by(OutreachMessage.id)))

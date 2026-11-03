from idearadar.config import Settings
from idearadar.guardrails import Guardrails, has_disclosure, is_opt_out, qa_check
from idearadar.models import Experiment, Idea
from idearadar.outreach import handle_reply, queue_outreach

GOOD = "Hi, ich baue gerade ein Tool für Immobilienverwaltung und würde gern wissen, wie du das heute löst."


def _exp(session):
    from datetime import date
    session.add(Idea(day=date.today(), cluster_key="k", title="t", score=1))
    session.flush()
    session.add(Experiment(idea_id=1))
    session.commit()


def test_disclosure_and_qa():
    assert has_disclosure(GOOD)
    assert qa_check(GOOD) is None
    assert qa_check("Hallo, kauf unser Produkt, garantiert der beste Preis für dich heute.")
    assert "disclosure" in qa_check("Hallo, dies ist ein langer Text ohne irgendeinen Hinweis auf den Absender.")


def test_default_is_dry_run_never_live(session, cfg):
    _exp(session)
    m = queue_outreach(session, cfg, 1, "x", "alice", GOOD)
    assert m.status == "dry_run"


def test_live_requires_channel_whitelist_and_dry_run_off(session):
    _exp(session)
    cfg = Settings(dry_run=False, live_channels="x", min_gap_seconds=0)
    assert queue_outreach(session, cfg, 1, "x", "a", GOOD).status == "queued"
    assert queue_outreach(session, cfg, 1, "reddit", "b", GOOD).status == "dry_run"


def test_linkedin_is_always_assist_even_when_live(session):
    _exp(session)
    cfg = Settings(dry_run=False, live_channels="linkedin,x", min_gap_seconds=0)
    assert queue_outreach(session, cfg, 1, "linkedin", "a", GOOD).status == "assist"


def test_email_requires_opt_in(session, cfg):
    _exp(session)
    assert queue_outreach(session, cfg, 1, "email", "a@b.de", GOOD).status == "blocked"
    assert queue_outreach(session, cfg, 1, "email", "a@b.de", GOOD, opted_in=True).status == "dry_run"


def test_daily_cap(session):
    _exp(session)
    cfg = Settings(cap_reddit_per_day=2, min_gap_seconds=0)
    st = [queue_outreach(session, cfg, 1, "reddit", f"u{i}", GOOD).status for i in range(3)]
    assert st == ["dry_run", "dry_run", "blocked"]


def test_min_gap(session):
    _exp(session)
    cfg = Settings(min_gap_seconds=600)
    assert queue_outreach(session, cfg, 1, "x", "a", GOOD).status == "dry_run"
    assert queue_outreach(session, cfg, 1, "x", "b", GOOD).status == "blocked"


def test_kill_switch_blocks_everything(session, cfg):
    _exp(session)
    Guardrails(session, cfg).set_kill_switch(True)
    assert queue_outreach(session, cfg, 1, "x", "a", GOOD).status == "blocked"
    assert queue_outreach(session, cfg, 1, "linkedin", "a", GOOD).status == "blocked"


def test_opt_out_suppresses_on_all_channels(session, cfg):
    _exp(session)
    assert is_opt_out("bitte STOP")
    assert handle_reply(session, cfg, "x", "alice", "Stopp bitte")
    assert queue_outreach(session, cfg, 1, "reddit", "alice", GOOD).status == "blocked"
    assert not handle_reply(session, cfg, "x", "bob", "klingt spannend, erzähl mehr")

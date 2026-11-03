import logging
from typing import Protocol

import httpx

log = logging.getLogger("idearadar.mail")


class Mailer(Protocol):
    def send(self, to: str, subject: str, text: str) -> None: ...


class LogMailer:
    """Default: nothing leaves the system, mails are only logged (and kept for tests)."""

    def __init__(self):
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, text: str) -> None:
        self.sent.append((to, subject, text))
        log.info("[dry-run mail] to=%s subject=%s", to, subject)


class SendGridMailer:
    def __init__(self, api_key: str, sender: str, client: httpx.Client | None = None):
        self.key, self.sender = api_key, sender
        self.client = client or httpx.Client(timeout=15)

    def send(self, to: str, subject: str, text: str) -> None:
        r = self.client.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {self.key}"},
            json={"personalizations": [{"to": [{"email": to}]}], "from": {"email": self.sender},
                  "subject": subject, "content": [{"type": "text/plain", "value": text}]},
        )
        r.raise_for_status()

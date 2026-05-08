"""Email marketing client — SendGrid-based replacement for Klaviyo."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, To

from app.config import settings

log = structlog.get_logger()


class EmailClient:
    def __init__(self):
        self._sg = SendGridAPIClient(settings.sendgrid_api_key)

    async def get_today_stats(self) -> dict[str, Any]:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._sg.client.stats.get(
                    query_params={"start_date": today, "aggregated_by": "day"}
                ),
            )
            if response.status_code == 200:
                import json
                data = json.loads(response.body)
                stats = data[0].get("stats", [{}])[0].get("metrics", {}) if data else {}
                opens = stats.get("opens", 0)
                delivered = stats.get("delivered", 0)
                open_rate = (opens / delivered * 100) if delivered > 0 else 0.0
                return {
                    "revenue": 0.0,  # SendGrid doesn't track revenue; integrate via Shopify webhooks
                    "open_rate": round(open_rate, 2),
                    "delivered": delivered,
                    "opens": opens,
                    "clicks": stats.get("clicks", 0),
                }
        except Exception as e:
            log.warning("email.stats_failed", error=str(e))
        return {"revenue": 0.0, "open_rate": 0.0, "delivered": 0, "opens": 0, "clicks": 0}

    async def send_transactional(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        from_email: str | None = None,
        dry_run: bool = False,
    ) -> dict:
        if dry_run:
            return {"dry_run": True, "to": to_email, "subject": subject}

        message = Mail(
            from_email=from_email or f"{settings.email_from_name} <{settings.email_from_address}>",
            to_emails=to_email,
            subject=subject,
            html_content=html_content,
        )
        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: self._sg.send(message))
        return {"status_code": response.status_code, "sent": True}

    async def send_bulk(
        self,
        recipients: list[dict],
        subject: str,
        html_template: str,
        dry_run: bool = False,
    ) -> dict:
        """
        recipients: [{"email": "...", "name": "...", "personalization": {...}}]
        HIGH RISK — always requires approval for > 100 recipients.
        """
        if dry_run:
            return {"dry_run": True, "recipients_count": len(recipients), "subject": subject}

        sent = 0
        failed = 0
        for recipient in recipients:
            try:
                html = html_template.format(**recipient.get("personalization", {}))
                await self.send_transactional(recipient["email"], subject, html)
                sent += 1
            except Exception as e:
                log.warning("email.bulk_send_failed", email=recipient["email"], error=str(e))
                failed += 1

        return {"sent": sent, "failed": failed, "total": len(recipients)}

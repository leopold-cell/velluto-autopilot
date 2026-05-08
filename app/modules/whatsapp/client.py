"""
WhatsApp Business API client (Meta Cloud API).
Sends text messages, interactive buttons, and receives webhooks.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.config import settings

log = structlog.get_logger()

BASE = "https://graph.facebook.com/v21.0"


class WhatsAppClient:
    def __init__(self):
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {settings.meta_access_token}"},
            timeout=15.0,
        )
        self.phone_number_id = settings.whatsapp_phone_number_id
        self.recipient = settings.whatsapp_recipient_number

    async def send_text(self, text: str, to: str | None = None) -> dict:
        return await self._send(
            to=to or self.recipient,
            message={"type": "text", "text": {"body": text, "preview_url": False}},
        )

    async def send_interactive_buttons(
        self,
        body: str,
        buttons: list[dict],
        to: str | None = None,
        header: str | None = None,
        footer: str | None = None,
    ) -> dict:
        """Send a message with up to 3 quick-reply buttons."""
        action = {
            "buttons": [
                {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                for b in buttons[:3]
            ]
        }
        payload: dict[str, Any] = {
            "type": "button",
            "body": {"text": body},
            "action": action,
        }
        if header:
            payload["header"] = {"type": "text", "text": header}
        if footer:
            payload["footer"] = {"text": footer}

        return await self._send(
            to=to or self.recipient,
            message={"type": "interactive", "interactive": payload},
        )

    async def _send(self, to: str, message: dict) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            **message,
        }
        r = await self._client.post(
            f"{BASE}/{self.phone_number_id}/messages",
            json=payload,
        )
        if r.status_code != 200:
            log.error("whatsapp.send_failed", status=r.status_code, body=r.text)
        r.raise_for_status()
        data = r.json()
        log.info("whatsapp.sent", message_id=data.get("messages", [{}])[0].get("id"))
        return data

    def verify_webhook(self, mode: str, token: str, challenge: str) -> str | None:
        if mode == "subscribe" and token == settings.whatsapp_verify_token:
            return challenge
        return None

    def parse_incoming(self, body: dict) -> dict | None:
        """Parse an incoming webhook and return a normalized message dict."""
        try:
            entry = body["entry"][0]["changes"][0]["value"]
            messages = entry.get("messages", [])
            if not messages:
                return None
            msg = messages[0]
            return {
                "from": msg.get("from"),
                "type": msg.get("type"),
                "text": msg.get("text", {}).get("body"),
                "button_id": msg.get("interactive", {}).get("button_reply", {}).get("id"),
                "button_title": msg.get("interactive", {}).get("button_reply", {}).get("title"),
                "timestamp": msg.get("timestamp"),
            }
        except (KeyError, IndexError):
            return None

"""Minimal Stripe REST client: Checkout Sessions + webhook signature verification (no SDK)."""
import hashlib
import hmac
import json
import time

import httpx

API = "https://api.stripe.com/v1"


class StripeError(RuntimeError):
    pass


def create_checkout_session(secret_key: str, *, amount_cents: int, product_name: str, success_url: str, cancel_url: str,
                            email: str, experiment_id: int, variant: str, client: httpx.Client | None = None) -> dict:
    if not secret_key:
        raise StripeError("STRIPE_SECRET_KEY is not configured")
    data = {
        "mode": "payment",
        "success_url": success_url, "cancel_url": cancel_url,
        "customer_email": email,
        "client_reference_id": f"exp{experiment_id}",
        "metadata[experiment_id]": str(experiment_id), "metadata[variant]": variant,
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": "eur",
        "line_items[0][price_data][unit_amount]": str(amount_cents),
        "line_items[0][price_data][product_data][name]": product_name,
    }
    c = client or httpx.Client(timeout=20)
    r = c.post(f"{API}/checkout/sessions", data=data, headers={"Authorization": f"Bearer {secret_key}"})
    if r.status_code >= 400:
        raise StripeError(f"stripe error {r.status_code}: {r.text[:200]}")
    return r.json()


def verify_webhook(payload: bytes, sig_header: str, secret: str, *, tolerance: int = 300, now: float | None = None) -> dict:
    """Stripe scheme: header 't=<ts>,v1=<hmac>'; HMAC-SHA256 over '<ts>.<payload>'."""
    if not secret:
        raise StripeError("webhook secret not configured")
    parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
    ts, sigs = parts.get("t"), [v for k, v in (p.split("=", 1) for p in sig_header.split(",") if "=" in p) if k == "v1"]
    if not ts or not sigs:
        raise StripeError("malformed signature header")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in sigs):
        raise StripeError("signature mismatch")
    if abs((now if now is not None else time.time()) - int(ts)) > tolerance:
        raise StripeError("timestamp outside tolerance")
    return json.loads(payload)

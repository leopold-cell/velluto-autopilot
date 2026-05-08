from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "Velluto Autopilot"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    secret_key: str = "dev-secret-change-in-production"

    # Database
    database_url: str = "postgresql+asyncpg://velluto:velluto@localhost:5432/velluto_autopilot"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_max_tokens: int = 8192

    # Shopify
    shopify_shop_name: str = ""
    shopify_api_key: str = ""
    shopify_api_secret: str = ""
    shopify_access_token: str = ""
    shopify_api_version: str = "2024-10"

    # Meta Ads
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_access_token: str = ""
    meta_ad_account_id: str = ""

    # WhatsApp
    whatsapp_provider: Literal["meta", "twilio"] = "meta"
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_recipient_number: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_number: str = ""

    # Google
    google_service_account_json: str = ""
    gsc_site_url: str = ""

    # Microsoft Clarity
    clarity_project_id: str = ""
    clarity_api_token: str = ""

    # Email
    sendgrid_api_key: str = ""
    email_from_address: str = "hello@velluto.com"
    email_from_name: str = "Velluto Eyewear"

    # OpenAI
    openai_api_key: str = ""

    # Sentry
    sentry_dsn: str = ""

    # Business targets
    daily_sales_target: int = 7
    monthly_sales_target: int = 200

    # Scheduling
    daily_report_time: str = "08:30"
    daily_report_timezone: str = "Europe/Berlin"

    # Autonomy thresholds
    max_auto_budget_change_pct: float = 0.10
    max_auto_discount_pct: float = 0.00

    # Competitor monitoring
    competitor_urls: list[str] = Field(default_factory=list)

    # Metrics
    metrics_port: int = 9090


settings = Settings()

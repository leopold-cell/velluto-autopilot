from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./idearadar.db"
    admin_api_key: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    youtube_api_key: str = ""

    # LLM budget (USD). Prices are per million tokens and only used for the cap.
    daily_llm_budget_usd: float = 8.0
    llm_input_usd_per_mtok: float = 3.0
    llm_output_usd_per_mtok: float = 15.0

    # safety defaults: nothing leaves the system unless explicitly enabled
    dry_run: bool = True
    live_channels: str = ""
    kill_switch: bool = False

    # per-channel daily caps; linkedin is never automated
    cap_x_per_day: int = 15
    cap_reddit_per_day: int = 5
    cap_email_per_day: int = 50
    min_gap_seconds: int = 120

    # public landing pages
    public_base_url: str = "http://localhost:8100"
    hash_secret: str = "change-me"            # salts the cookie-less visitor hash
    legal_company: str = ""                   # Impressum / Datenschutz are rendered from these;
    legal_address: str = ""                   # landing pages are refused while they are empty
    legal_email: str = ""
    deposit_eur: float = 9.0
    sendgrid_api_key: str = ""
    mail_from: str = ""

    # Stripe (REST, no SDK). Test keys (sk_test_...) first.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # experiment defaults
    explore_days: int = 7
    default_test_days: int = 14
    go_signups: int = 30
    go_preorders: int = 3
    target_monthly_profit_eur: float = 5000.0
    max_payers_needed: int = 2000
    ideas_per_day: int = 3

    @property
    def live_channel_set(self) -> set[str]:
        return {c.strip().lower() for c in self.live_channels.split(",") if c.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()

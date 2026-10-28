from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Global configuration loader for rata-hire.
    Reads environment variables from `.env` and dynamically resolves paths
    for the active user profile (`profiles/{active_profile}/`).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Active User Profile (Multi-user ready: defaults to 'ephrata')
    active_profile: str = "ephrata"

    # LLM & Notification Credentials
    gemini_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Model Routing
    gemini_fast_model: str = "gemini-2.5-flash"
    gemini_pro_model: str = "gemini-2.5-pro"

    # Storage & Browser Automation
    database_url: str = "sqlite:///./data/rata_hire.db"
    playwright_headless: bool = False
    discovery_interval_hours: int = 24

    @property
    def base_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def config_dir(self) -> Path:
        return self.base_dir / "config"

    @property
    def job_sources_path(self) -> Path:
        return self.config_dir / "job_sources.yaml"

    @property
    def templates_dir(self) -> Path:
        return self.base_dir / "data" / "templates"

    @property
    def profile_dir(self) -> Path:
        path = self.base_dir / "profiles" / self.active_profile
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def master_cv_path(self) -> Path:
        return self.profile_dir / "master_cv_contract.json"

    @property
    def qa_bank_path(self) -> Path:
        return self.profile_dir / "qa_bank.json"

    @property
    def candidate_profile_path(self) -> Path:
        return self.profile_dir / "candidate_profile.yaml"

    @property
    def artifacts_dir(self) -> Path:
        path = self.profile_dir / "artifacts"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def browser_profile_dir(self) -> Path:
        path = self.profile_dir / ".browser_profile"
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()

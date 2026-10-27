"""Application configuration loaded from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings


# ── Profile presets ───────────────────────────────────────────
# PROFILE selects default provider/model for agent + judge.
# Explicit LLM_PROVIDER / JUDGE_PROVIDER in .env override these.

PROFILES = {
    "local": {
        "llm_provider": "ollama",
        "llm_model": "qwen2.5:7b",
        "judge_provider": "ollama",
        "judge_model": "qwen2.5:7b",
    },
    "free": {
        "llm_provider": "groq",
        "llm_model": "qwen/qwen3.8-27b",
        "judge_provider": "groq",
        "judge_model": "qwen/qwen3.8-27b",
    },
    "paid": {
        "llm_provider": "openai",
        "llm_model": "gpt-4o-mini",
        "judge_provider": "openai",
        "judge_model": "gpt-4o-mini",
    },
}


class Settings(BaseSettings):
    """Global settings for Keystone."""

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "keystone"
    postgres_user: str = "keystone"
    postgres_password: str = "keystone_dev_password"
    database_url: str = (
        "postgresql+asyncpg://keystone:keystone_dev_password@localhost:5432/keystone"
    )

    @property
    def sync_database_url(self) -> str:
        """Synchronous database URL for seeding."""
        return self.database_url.replace("+asyncpg", "").replace(
            "postgresql://", "postgresql+psycopg://"
        )

    @property
    def raw_database_url(self) -> str:
        """Plain psycopg URL for raw connections."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Profile (local / free / paid)
    profile: str = "local"

    # LLM — global defaults (used by agent unless overridden)
    llm_provider: str = ""
    llm_model: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""

    # Per-component overrides (blank = use profile or global default)
    judge_provider: str = ""
    judge_model: str = ""
    seed_provider: str = ""
    seed_model: str = ""

    # Ollama
    ollama_base_url: str = "http://localhost:11434/v1"

    def _profile_defaults(self) -> dict:
        return PROFILES.get(self.profile, PROFILES["local"])

    def effective_llm_provider(self) -> str:
        return self.llm_provider or self._profile_defaults()["llm_provider"]

    def effective_llm_model(self) -> str:
        return self.llm_model or self._profile_defaults()["llm_model"]

    def effective_judge_provider(self) -> str:
        return self.judge_provider or self._profile_defaults()["judge_provider"]

    def effective_judge_model(self) -> str:
        return self.judge_model or self._profile_defaults()["judge_model"]

    # Cerbos
    cerbos_host: str = "localhost"
    cerbos_port: int = 3593
    cerbos_http_port: int = 3592

    # Langfuse
    langfuse_secret_key: str = ""
    langfuse_public_key: str = ""
    langfuse_host: str = "http://localhost:3001"

    # JWT
    jwt_secret_key: str = "change-this-to-a-random-secret-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60

    # Seed
    seed_random_seed: int = 42
    seed_llm_cache_dir: str = ".seed_cache"

    @property
    def seed_cache_path(self) -> Path:
        return Path(self.seed_llm_cache_dir)

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    streamlit_port: int = 8501
    log_level: str = "INFO"

    # ── Eval ablation flags ─────────────────────────────────────
    # These are ONLY respected when eval_mode=True.
    # The API and UI never set eval_mode, so protections cannot be
    # disabled outside the eval harness.
    eval_mode: bool = False
    ablation_policy_checks: bool = True
    ablation_rls: bool = True
    ablation_retrieval_prefilter: bool = True
    ablation_aggregation_guard: bool = True
    ablation_injection_scanner: bool = True
    ablation_output_scanner: bool = True
    ablation_system_prompt_rules: bool = True  # False = strip permission rules from system prompt

    def protection_enabled(self, name: str) -> bool:
        """Check if a protection layer is active.

        Always returns True outside eval_mode — protections cannot be
        disabled in the API or UI, only in the eval harness.
        """
        if not self.eval_mode:
            return True
        return getattr(self, f"ablation_{name}", True)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

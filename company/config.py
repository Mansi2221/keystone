"""Application configuration loaded from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings


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

    # LLM
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    anthropic_api_key: str = ""

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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

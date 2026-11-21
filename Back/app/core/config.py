from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações globais da aplicação carregadas a partir de variáveis de ambiente."""
    PROJECT_NAME: str = "Fique de Olho API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Conexão de desenvolvimento com o PostgreSQL do Compose da raiz.
    DATABASE_URL: str = (
        "postgresql+psycopg2://fique_de_olho:fique_de_olho_dev"
        "@localhost:5432/fique_de_olho"
    )

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str) -> str:
        """Garante que a URL do banco utilize o driver psycopg2 compativel com SQLAlchemy."""
        if isinstance(v, str):
            if v.startswith("postgres://"):
                return v.replace("postgres://", "postgresql+psycopg2://", 1)
            elif v.startswith("postgresql://") and not v.startswith("postgresql+"):
                return v.replace("postgresql://", "postgresql+psycopg2://", 1)
        return v

    # Configurações de Autenticação JWT e Google OAuth
    JWT_SECRET_KEY: str = "insecure-secret-key-change-in-production-mds-2026"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 horas
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = ""
    NOTIFICATION_SCHEDULER_ENABLED: bool = True
    NOTIFICATION_SCHEDULER_INTERVAL_SECONDS: int = 3600

    # Agendador em segundo plano de coleta periódica de editais (Issue #74 / #125)
    SCRAPER_SCHEDULER_ENABLED: bool = True
    SCRAPER_SCHEDULER_INTERVAL_HOURS: int = 12
    SCRAPER_SCHEDULER_RUN_ON_STARTUP: bool = False
    SCRAPER_SCHEDULER_FETCH_DOCS: bool = True
    SCRAPER_SCHEDULER_PDF_ENRICHMENT: bool = True

    # Cache em memória Stale-While-Revalidate da listagem de editais (Issue #116)
    EDITAIS_CACHE_TTL_SECONDS: int = 900

    # Camada 2 (LLM) de resumo/normalização de títulos e metadados — Issues #77, #106, #121, #125 e #129.
    # Opcional: sem chave, o pipeline usa apenas a heurística local (Camada 1).
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_FALLBACK_MODEL: str = "gemini-flash-lite-latest"
    GEMINI_TIMEOUT_SECONDS: float = 15.0
    GEMINI_RETRY_DELAY_SECONDS: float = 2.0

    @field_validator(
        "SENDGRID_API_KEY",
        "SENDGRID_FROM_EMAIL",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "GEMINI_FALLBACK_MODEL",
        mode="before",
    )
    @classmethod
    def strip_external_service_settings(cls, v: str) -> str:
        """Remove espaços ou quebras de linha acidentais em credenciais/modelos de ambiente."""
        if isinstance(v, str):
            return v.strip()
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

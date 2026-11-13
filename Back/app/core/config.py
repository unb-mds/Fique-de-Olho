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

    # Configurações de Autenticação JWT (Issue #63)
    JWT_SECRET_KEY: str = "insecure-secret-key-change-in-production-mds-2026"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 horas
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = ""
    NOTIFICATION_SCHEDULER_ENABLED: bool = True
    NOTIFICATION_SCHEDULER_INTERVAL_SECONDS: int = 86400

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

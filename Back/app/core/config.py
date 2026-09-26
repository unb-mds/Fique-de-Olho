from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações globais da aplicação carregadas a partir de variáveis de ambiente."""
    PROJECT_NAME: str = "Fique de Olho API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Conexão com banco de dados
    DATABASE_URL: str = "postgresql://fiquedeolho:fiquedeolho@localhost:5432/fiquedeolho_db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

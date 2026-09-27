from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.core.config import settings

# Engine de conexão do SQLAlchemy
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # Verifica se a conexão com o banco ainda está viva antes de usar
)

# Fábrica de sessões para requisições
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base declarativa para todos os modelos SQLAlchemy da aplicação
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency injection para fornecer a sessão de banco por requisição FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from enum import Enum as PyEnum
from typing import Generator

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    func,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

from app.core.config import settings


class StatusEdital(PyEnum):
    ABERTO = "aberto"
    ENCERRADO = "encerrado"


class TipoDocumento(PyEnum):
    ORIGINAL = "original"
    RESULTADO_PROVISORIO = "resultado_provisorio"
    RESULTADO_FINAL = "resultado_final"
    RETIFICACAO = "retificacao"


# Engine de conexão do SQLAlchemy
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # Verifica se a conexão com o banco ainda está viva antes de usar
)

# Fábrica de sessões para requisições
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base declarativa para todos os modelos SQLAlchemy da aplicação
Base = declarative_base()


class Edital(Base):
    __tablename__ = "editais"

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(255), nullable=False)
    url_pagina = Column(String(500), unique=True, nullable=False, index=True)
    campus = Column(String(255), nullable=True)
    tipo = Column(String(100), nullable=True)
    data_publicacao = Column(DateTime(timezone=True), nullable=False)
    status = Column(Enum(StatusEdital, name="status_edital", create_type=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    documentos = relationship("EditalDocumento", back_populates="edital", cascade="all, delete-orphan")
    favoritos = relationship("Favorito", back_populates="edital", cascade="all, delete-orphan")


class EditalDocumento(Base):
    __tablename__ = "edital_documentos"

    id = Column(Integer, primary_key=True, index=True)
    edital_id = Column(Integer, ForeignKey("editais.id"), nullable=False, index=True)
    url_pdf = Column(String(500), nullable=False)
    tipo_documento = Column(Enum(TipoDocumento, name="tipo_documento", create_type=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    edital = relationship("Edital", back_populates="documentos")


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    senha_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    favoritos = relationship("Favorito", back_populates="usuario", cascade="all, delete-orphan")


class Favorito(Base):
    __tablename__ = "favoritos"

    usuario_id = Column(Integer, ForeignKey("usuarios.id"), primary_key=True)
    edital_id = Column(Integer, ForeignKey("editais.id"), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    usuario = relationship("Usuario", back_populates="favoritos")
    edital = relationship("Edital", back_populates="favoritos")


def get_db() -> Generator[Session, None, None]:
    """Dependency injection para fornecer a sessão de banco por requisição FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

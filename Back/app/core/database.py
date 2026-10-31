from enum import Enum as PyEnum
from typing import Generator

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
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


class TipoEdital(Base):
    __tablename__ = "tipos_editais"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False, unique=True)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Campus(Base):
    __tablename__ = "campi"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False, unique=True)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Curso(Base):
    __tablename__ = "cursos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(200), nullable=False, unique=True)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Edital(Base):
    __tablename__ = "editais"
    __table_args__ = (
        CheckConstraint(
            "inicio_inscricao IS NULL OR fim_inscricao IS NULL "
            "OR inicio_inscricao <= fim_inscricao",
            name="editais_periodo_inscricao_ck",
        ),
        CheckConstraint(
            "status_processamento IN "
            "('pendente', 'processado', 'parcialmente_processado', 'erro')",
            name="editais_status_processamento_ck",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(500), nullable=False)
    url_pagina = Column(String(500), unique=True, nullable=True, index=True)
    campus = Column(String(255), nullable=True)
    tipo = Column(String(100), nullable=True)
    data_publicacao = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(StatusEdital, name="status_edital", create_type=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Campos complementares para suportar metadados detalhados, scraper e catálogo
    identificador_origem = Column(String(200), unique=True, nullable=True)
    resumo = Column(Text, nullable=True)
    url_pdf = Column(String(500), unique=True, nullable=True)
    texto_extraido = Column(Text, nullable=True)
    inicio_inscricao = Column(Date, nullable=True)
    fim_inscricao = Column(Date, nullable=True, index=True)
    status_processamento = Column(String(30), nullable=False,default="pendente", server_default="pendente")
    hash_conteudo = Column(String(64), nullable=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    atualizado_em = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    #Coloquei para a issues #52
    orgao_emissor = Column(String(50), nullable=True)
    vagas = Column(Integer, nullable=True)
    valor_bolsa = Column(Numeric(10, 2), nullable=True)

    # Relacionamentos com documentos, favoritos e catálogos M:N
    documentos = relationship("EditalDocumento", back_populates="edital", cascade="all, delete-orphan")
    favoritos = relationship("Favorito", back_populates="edital", cascade="all, delete-orphan")
    tipos = relationship("TipoEdital", secondary="edital_tipos", lazy="selectin")
    campi = relationship("Campus", secondary="edital_campi", lazy="selectin")
    cursos = relationship("Curso", secondary="edital_cursos", lazy="selectin")


class EditalDocumento(Base):
    __tablename__ = "edital_documentos"

    id = Column(Integer, primary_key=True, index=True)
    edital_id = Column(Integer, ForeignKey("editais.id"), nullable=False, index=True)
    url_pdf = Column(String(500), nullable=False)
    tipo_documento = Column(Enum(TipoDocumento, name="tipo_documento", create_type=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    edital = relationship("Edital", back_populates="documentos")


class EditalTipo(Base):
    __tablename__ = "edital_tipos"

    edital_id = Column(Integer, ForeignKey("editais.id", ondelete="CASCADE"), primary_key=True)
    tipo_edital_id = Column(Integer, ForeignKey("tipos_editais.id", ondelete="RESTRICT"), primary_key=True)


class EditalCampus(Base):
    __tablename__ = "edital_campi"

    edital_id = Column(Integer, ForeignKey("editais.id", ondelete="CASCADE"), primary_key=True)
    campus_id = Column(Integer, ForeignKey("campi.id", ondelete="RESTRICT"), primary_key=True)


class EditalCurso(Base):
    __tablename__ = "edital_cursos"

    edital_id = Column(Integer, ForeignKey("editais.id", ondelete="CASCADE"), primary_key=True)
    curso_id = Column(Integer, ForeignKey("cursos.id", ondelete="RESTRICT"), primary_key=True)


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


class Coleta(Base):
    __tablename__ = "coletas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fonte = Column(String(100), nullable=False, server_default="DEG")
    iniciada_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finalizada_em = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, server_default="executando")
    editais_encontrados = Column(Integer, nullable=False, server_default="0")
    mensagem_erro = Column(Text, nullable=True)


def get_db() -> Generator[Session, None, None]:
    """Dependency injection para fornecer a sessão de banco por requisição FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

"""Modelos ORM SQLAlchemy mapeando as tabelas do schema de editais."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import relationship

from app.core.database import Base


class TipoEdital(Base):
    __tablename__ = "tipos_editais"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False, unique=True)
    criado_em = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class Campus(Base):
    __tablename__ = "campi"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False, unique=True)
    criado_em = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class Curso(Base):
    __tablename__ = "cursos"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    nome = Column(String(200), nullable=False, unique=True)
    criado_em = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class Edital(Base):
    __tablename__ = "editais"
    __table_args__ = (
        CheckConstraint(
            "status_processamento IN ('pendente', 'processado', 'parcialmente_processado', 'erro')",
            name="editais_status_processamento_ck",
        ),
        CheckConstraint(
            "inicio_inscricao IS NULL OR fim_inscricao IS NULL OR inicio_inscricao <= fim_inscricao",
            name="editais_periodo_inscricao_ck",
        ),
        Index("editais_fim_inscricao_idx", "fim_inscricao"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    identificador_origem = Column(String(200), unique=True, nullable=True)
    titulo = Column(String(500), nullable=False)
    resumo = Column(Text, nullable=True)
    url_pdf = Column(Text, nullable=False, unique=True)
    texto_extraido = Column(Text, nullable=True)
    data_publicacao = Column(Date, nullable=True)
    inicio_inscricao = Column(Date, nullable=True)
    fim_inscricao = Column(Date, nullable=True)
    status_processamento = Column(String(30), nullable=False, server_default="pendente")
    hash_conteudo = Column(String(64), nullable=True)
    criado_em = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    atualizado_em = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # Relacionamentos M:N
    tipos = relationship("TipoEdital", secondary="edital_tipos", lazy="selectin")
    campi = relationship("Campus", secondary="edital_campi", lazy="selectin")
    cursos = relationship("Curso", secondary="edital_cursos", lazy="selectin")


class EditalTipo(Base):
    __tablename__ = "edital_tipos"

    edital_id = Column(BigInteger, ForeignKey("editais.id", ondelete="CASCADE"), primary_key=True)
    tipo_edital_id = Column(BigInteger, ForeignKey("tipos_editais.id", ondelete="RESTRICT"), primary_key=True)


class EditalCampus(Base):
    __tablename__ = "edital_campi"

    edital_id = Column(BigInteger, ForeignKey("editais.id", ondelete="CASCADE"), primary_key=True)
    campus_id = Column(BigInteger, ForeignKey("campi.id", ondelete="RESTRICT"), primary_key=True)


class EditalCurso(Base):
    __tablename__ = "edital_cursos"

    edital_id = Column(BigInteger, ForeignKey("editais.id", ondelete="CASCADE"), primary_key=True)
    curso_id = Column(BigInteger, ForeignKey("cursos.id", ondelete="RESTRICT"), primary_key=True)


class Coleta(Base):
    __tablename__ = "coletas"
    __table_args__ = (
        CheckConstraint(
            "status IN ('executando', 'concluida', 'falhou')",
            name="coletas_status_ck",
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    fonte = Column(String(100), nullable=False, server_default="DEG")
    iniciada_em = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    finalizada_em = Column(TIMESTAMP(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, server_default="executando")
    editais_encontrados = Column(BigInteger, nullable=False, server_default="0")
    mensagem_erro = Column(Text, nullable=True)

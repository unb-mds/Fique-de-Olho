"""Modelos ORM SQLAlchemy para o módulo de Editais.

Centraliza e reexporta os modelos declarativos a partir de app.core.database
para evitar declarações duplicadas e garantir metadados unificados.
"""

from app.core.database import (
    AlertaEdital,
    Base,
    Campus,
    Coleta,
    Curso,
    Edital,
    EditalCampus,
    EditalCurso,
    EditalDocumento,
    EditalTipo,
    Favorito,
    StatusEdital,
    TipoDocumento,
    TipoEdital,
    Usuario,
    Notificacao,
    StatusNotificacao,
    TipoNotificacao,
)

__all__ = [
    "AlertaEdital",
    "Base",
    "Campus",
    "Coleta",
    "Curso",
    "Edital",
    "EditalCampus",
    "EditalCurso",
    "EditalDocumento",
    "EditalTipo",
    "Favorito",
    "StatusEdital",
    "TipoDocumento",
    "TipoEdital",
    "Usuario",
    "Notificacao",
    "StatusNotificacao",
    "TipoNotificacao",
]

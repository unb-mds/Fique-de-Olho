"""Modelos ORM SQLAlchemy para o módulo de Editais.

Centraliza e reexporta os modelos declarativos a partir de app.core.database
para evitar declarações duplicadas e garantir metadados unificados.
"""

from app.core.database import (
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
)

__all__ = [
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
]

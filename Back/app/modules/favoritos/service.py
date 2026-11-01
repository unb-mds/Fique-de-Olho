"""Camada de serviço para a gestão de favoritos associados a usuários autenticados (Issue #65)."""

from typing import Any, Dict, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import Edital, Favorito


def favoritar_edital(db: Session, edital_id: int, usuario_id: int) -> Dict[str, Any]:
    """Adiciona um edital à lista de favoritos do usuário autenticado.

    Operação idempotente: se já estiver favoritado, confirma sem duplicar.

    Raises:
        HTTPException(404): Se o edital não existir.
    """
    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edital com ID {edital_id} não encontrado.",
        )

    favorito = (
        db.query(Favorito)
        .filter(Favorito.usuario_id == usuario_id, Favorito.edital_id == edital_id)
        .first()
    )

    if not favorito:
        favorito = Favorito(usuario_id=usuario_id, edital_id=edital_id)
        db.add(favorito)
        db.commit()

    return {
        "message": "Edital favoritado com sucesso.",
        "edital_id": edital_id,
        "usuario_id": usuario_id,
        "favoritado": True,
    }


def desfavoritar_edital(db: Session, edital_id: int, usuario_id: int) -> Dict[str, Any]:
    """Remove um edital da lista de favoritos do usuário autenticado.

    Raises:
        HTTPException(404): Se o edital não existir.
    """
    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edital com ID {edital_id} não encontrado.",
        )

    favorito = (
        db.query(Favorito)
        .filter(Favorito.usuario_id == usuario_id, Favorito.edital_id == edital_id)
        .first()
    )

    if favorito:
        db.delete(favorito)
        db.commit()

    return {
        "message": "Edital desfavoritado com sucesso.",
        "edital_id": edital_id,
        "usuario_id": usuario_id,
        "favoritado": False,
    }


def listar_favoritos_usuario(db: Session, usuario_id: int) -> List[Edital]:
    """Recupera todos os editais que foram favoritados pelo usuário autenticado."""
    return (
        db.query(Edital)
        .join(Favorito, Favorito.edital_id == Edital.id)
        .filter(Favorito.usuario_id == usuario_id)
        .all()
    )


def listar_favoritos_usuario(db: Session, usuario_id: int) -> List[Edital]:
    """Recupera todos os editais que foram favoritados pelo usuário autenticado."""
    return (
        db.query(Edital)
        .join(Favorito, Favorito.edital_id == Edital.id)
        .filter(Favorito.usuario_id == usuario_id)
        .all()
    )


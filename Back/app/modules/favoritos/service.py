from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import Edital, Favorito, Usuario


def get_or_create_default_user(db: Session, user_id: Optional[int] = None) -> Usuario:
    """Retorna o usuário pelo ID ou obtém/cria um usuário padrão para a sessão."""
    if user_id is not None:
        user = db.query(Usuario).filter(Usuario.id == user_id).first()
        if user:
            return user
        # Se um ID específico foi solicitado mas não existe, cria com esse ID
        user = Usuario(
            id=user_id,
            nome=f"Usuário {user_id}",
            email=f"usuario{user_id}@unb.br",
            senha_hash="hash_padrao",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    # Usuário padrão
    user = db.query(Usuario).first()
    if not user:
        user = Usuario(
            nome="Usuário Padrão",
            email="usuario@unb.br",
            senha_hash="hash_padrao",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def favoritar_edital(db: Session, edital_id: int, usuario_id: int) -> dict:
    """Adiciona um edital à lista de favoritos do usuário."""
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


def desfavoritar_edital(db: Session, edital_id: int, usuario_id: int) -> dict:
    """Remove um edital da lista de favoritos do usuário."""
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

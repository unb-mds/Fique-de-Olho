from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.favoritos.service import (
    favoritar_edital,
    desfavoritar_edital,
    get_or_create_default_user,
)

router = APIRouter(prefix="/editais", tags=["Editais"])


@router.get("/", response_model=List[Dict[str, Any]])
def list_editais():
    """Retorna listagem inicial de editais disponíveis (estrutura inicial de setup)."""
    return [
        {
            "id": 1,
            "titulo": "Edital Monitoria DEG 01/2026",
            "campus": "Darcy Ribeiro",
            "status": "aberto",
            "resumo": "Processo seletivo para monitores bolsistas e voluntários nos departamentos da UnB."
        }
    ]


@router.post("/{id}/favoritar", status_code=status.HTTP_200_OK)
def favoritar(
    id: int,
    db: Session = Depends(get_db),
    usuario_id: Optional[int] = Query(None, description="ID do usuário via query param"),
    x_user_id: Optional[int] = Header(None, alias="X-User-Id", description="ID do usuário via header"),
):
    """Marca um edital como favorito para o usuário."""
    uid = x_user_id or usuario_id
    user = get_or_create_default_user(db, uid)
    return favoritar_edital(db=db, edital_id=id, usuario_id=user.id)


@router.delete("/{id}/favoritar", status_code=status.HTTP_200_OK)
def desfavoritar(
    id: int,
    db: Session = Depends(get_db),
    usuario_id: Optional[int] = Query(None, description="ID do usuário via query param"),
    x_user_id: Optional[int] = Header(None, alias="X-User-Id", description="ID do usuário via header"),
):
    """Remove um edital dos favoritos do usuário."""
    uid = x_user_id or usuario_id
    user = get_or_create_default_user(db, uid)
    return desfavoritar_edital(db=db, edital_id=id, usuario_id=user.id)

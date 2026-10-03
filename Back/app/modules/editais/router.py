"""Rotas da API para consulta, detalhamento e sincronização de editais."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.editais.schemas import EditalResponse, EditalDetailResponse, SyncResult
from app.modules.editais.service import get_editais, get_edital_by_id
from app.modules.scraper.service import sync_deg_editais

router = APIRouter(prefix="/editais", tags=["Editais"])


@router.get("/", response_model=List[EditalResponse])
def list_editais(
    status: Optional[str] = Query(None, description="Filtrar por status ('aberto' ou 'fechado')"),
    categoria: Optional[str] = Query(None, description="Filtrar por tipo/categoria (ex: Monitoria, PIBIC, Extensões)"),
    campus: Optional[str] = Query(None, description="Filtrar por campus (ex: Darcy Ribeiro, FGA)"),
    busca: Optional[str] = Query(None, description="Busca textual por termo no título ou resumo"),
    db: Session = Depends(get_db),
):
    """Retorna listagem de editais cadastrados no PostgreSQL com suporte a filtros e busca."""
    return get_editais(db, status=status, categoria=categoria, campus=campus, busca=busca)


@router.get("/{edital_id}", response_model=EditalDetailResponse)
def get_edital(
    edital_id: int,
    db: Session = Depends(get_db),
):
    """Retorna detalhes completos de um edital específico pelo ID."""
    edital = get_edital_by_id(db, edital_id)
    if not edital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edital com ID {edital_id} não encontrado.",
        )
    return edital


@router.post("/sync", response_model=SyncResult)
def trigger_sync_editais(
    max_itens: int = Query(20, ge=1, le=100, description="Quantidade máxima de itens a processar"),
    db: Session = Depends(get_db),
):
    """Executa a raspagem do portal DEG UnB e persiste novos editais no banco de dados."""
    try:
        resultado = sync_deg_editais(db, max_items=max_itens)
        return resultado
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao sincronizar editais: {str(e)}",
        )


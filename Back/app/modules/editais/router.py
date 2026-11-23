import logging
import secrets
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.core.database import Usuario, get_db
from app.modules.editais.service import (
    get_edital_by_id,
    invalidar_cache_editais,
    listar_editais_com_cache,
    obter_stats_editais_com_cache,
    serialize_edital,
)
from app.modules.favoritos.service import (
    desfavoritar_edital,
    favoritar_edital,
    listar_favoritos_usuario,
)
from app.modules.notificacoes.processor import (
    processar_alerta_ativado_em_segundo_plano,
    sendgrid_configurado,
)
from app.modules.notificacoes.service import (
    ativar_alerta_edital,
    desativar_alerta_edital,
    listar_alertas_usuario,
)
from app.modules.scraper.scheduler import ColetaEmAndamentoError, controlar_concorrencia_coleta
from app.modules.usuarios import get_current_user

router = APIRouter(prefix="/editais", tags=["Editais"])


PUBLIC_CACHE_HEADER = "public, max-age=60, stale-while-revalidate=300"


@router.get("/stats", response_model=Dict[str, int])
def editais_stats(
    background_tasks: BackgroundTasks,
    response: Response,
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = PUBLIC_CACHE_HEADER
    return obter_stats_editais_com_cache(
        db=db,
        agendar_tarefa=background_tasks.add_task,
    )


@router.get("/", response_model=List[Dict[str, Any]])
def list_editais(
    background_tasks: BackgroundTasks,
    response: Response,
    ano: Optional[int] = Query(None, description="Filtra editais pelo ano de publicação"),
    q: Optional[str] = Query(None, description="Busca textual por título"),
    busca: Optional[str] = Query(None, description="Alias para parâmetro de busca textual"),
    status: Optional[str] = Query(None, description="Filtra por status ('aberto' ou 'fechado')"),
    categoria: Optional[str] = Query(None, description="Filtra por categoria/tipo"),
    campus: Optional[str] = Query(None, description="Filtra por campus"),
    skip: int = Query(0, ge=0, description="Quantidade de registros a ignorar"),
    limit: int = Query(24, ge=1, le=100, description="Quantidade máxima de registros"),
    db: Session = Depends(get_db),
):
    """
    Retorna a listagem de editais com suporte a filtros dinâmicos:
    - `ano`: ano de publicação (ex: 2026)
    - `q` ou `busca`: termo de busca textual no título ou resumo
    - `status`: 'aberto' ou 'fechado'
    - `categoria`: categoria/tipo do edital
    - `campus`: campus da UnB
    """
    response.headers["Cache-Control"] = PUBLIC_CACHE_HEADER
    try:
        resultado = listar_editais_com_cache(
            db=db,
            agendar_tarefa=background_tasks.add_task,
            ano=ano,
            q=q,
            busca=busca,
            status=status,
            categoria=categoria,
            campus=campus,
            skip=skip,
            limit=limit,
        )
        if resultado is not None:
            return resultado
    except Exception:
        logger.exception("Falha ao consultar editais no banco de dados; utilizando fallback inicial.")

    # Fallback inicial para quando o banco estiver indisponível ou vazio sem filtros
    return [
        {
            "id": 1,
            "titulo": "Edital Monitoria DEG 01/2026",
            "campus": "Darcy Ribeiro",
            "unidade": "Darcy Ribeiro",
            "categoria": "Monitoria",
            "tipo": "Monitoria",
            "status": "aberto",
            "resumo": "Processo seletivo para monitores bolsistas e voluntários nos departamentos da UnB.",
            "descricao": "Processo seletivo para monitores bolsistas e voluntários nos departamentos da UnB.",
            "url_pdf": "https://deg.unb.br/editais/edital-monitoria-deg-01-2026.pdf",
            "urlDocumento": "https://deg.unb.br/editais/edital-monitoria-deg-01-2026.pdf",
            "documentos": [],
            "campi": [],
            "tipos": [],
        }
    ]


@router.get(
    "/favoritos",
    response_model=List[Dict[str, Any]],
    summary="Listar editais favoritos do usuário autenticado",
    description="Retorna todos os editais favoritados pelo estudante logado via token Bearer/JWT.",
)
def listar_favoritos(
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    editais_db = listar_favoritos_usuario(db=db, usuario_id=usuario_atual.id)
    return [serialize_edital(e) for e in editais_db]


@router.get(
    "/alertas",
    response_model=Dict[str, Any],
    summary="Listar editais com alertas por e-mail ativados",
    description="Retorna os IDs dos editais para os quais o usuário autenticado ativou o envio de e-mails.",
)
def listar_alertas(
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    edital_ids = listar_alertas_usuario(db=db, usuario_id=usuario_atual.id)
    return {
        "edital_ids": edital_ids,
        "email_configurado": sendgrid_configurado(),
    }


@router.get("/{id}", response_model=Dict[str, Any])
def get_edital(id: str, response: Response, db: Session = Depends(get_db)):
    """Retorna os detalhes completos de um edital pelo seu ID."""
    if not id.isdigit():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edital com ID {id} não encontrado.",
        )

    edital_id = int(id)
    try:
        edital = get_edital_by_id(db=db, edital_id=edital_id)
        if edital:
            response.headers["Cache-Control"] = PUBLIC_CACHE_HEADER
            return serialize_edital(edital, detail=True)
    except Exception:
        logger.exception("Falha ao consultar editais no banco de dados; utilizando fallback inicial.")

    # Fallback para ID 1 caso o banco esteja indisponível/não inicializado
    if edital_id == 1:
        return {
            "id": 1,
            "titulo": "Edital Monitoria DEG 01/2026",
            "campus": "Darcy Ribeiro",
            "unidade": "Darcy Ribeiro",
            "categoria": "Monitoria",
            "tipo": "Monitoria",
            "status": "aberto",
            "resumo": "Processo seletivo para monitores bolsistas e voluntários nos departamentos da UnB.",
            "descricao": "Processo seletivo para monitores bolsistas e voluntários nos departamentos da UnB.",
            "url_pdf": "https://deg.unb.br/editais/edital-monitoria-deg-01-2026.pdf",
            "urlDocumento": "https://deg.unb.br/editais/edital-monitoria-deg-01-2026.pdf",
            "documentos": [],
            "campi": [],
            "tipos": [],
        }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Edital com ID {edital_id} não encontrado.",
    )


def verificar_chave_admin(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
) -> None:
    """Valida a chave administrativa caso ``ADMIN_API_KEY`` esteja configurada no ambiente."""
    if not settings.ADMIN_API_KEY:
        return
    if not x_admin_key or not secrets.compare_digest(x_admin_key, settings.ADMIN_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chave administrativa inválida ou ausente.",
        )


@router.post("/sync", response_model=Dict[str, Any])
def sync_editais(
    max_itens: int = Query(30, ge=1, le=500, description="Número máximo de editais a processar por portal"),
    orgao: Optional[str] = Query(
        None,
        description="Sigla do órgão a sincronizar. Se omitido, sincroniza todos os portais registrados.",
    ),
    _admin: None = Depends(verificar_chave_admin),
    db: Session = Depends(get_db),
):
    """Dispara a coleta periódica com o portal informado (ou todos os registrados em SCRAPERS_REGISTRY)."""
    try:
        with controlar_concorrencia_coleta():
            from app.modules.scraper.service import sync_orgaos_editais

            resultado = sync_orgaos_editais(
                db=db,
                orgao=orgao,
                max_items_per_orgao=max_itens,
                fetch_docs=True,
                enable_pdf_enrichment=True,
            )
            invalidar_cache_editais()
            return resultado
    except ColetaEmAndamentoError as lock_exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(lock_exc),
        )
    except ValueError as val_exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao coletar editais: {str(exc)}",
        )


@router.post(
    "/{id}/favoritar",
    status_code=status.HTTP_200_OK,
    summary="Favoritar edital",
    description="Adiciona um edital aos favoritos do usuário autenticado via Bearer/JWT.",
)
def favoritar(
    id: int,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    """Marca um edital como favorito exclusivamente para o usuário autenticado."""
    return favoritar_edital(db=db, edital_id=id, usuario_id=usuario_atual.id)


@router.delete(
    "/{id}/favoritar",
    status_code=status.HTTP_200_OK,
    summary="Desfavoritar edital",
    description="Remove um edital dos favoritos do usuário autenticado via Bearer/JWT.",
)
def desfavoritar(
    id: int,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    """Remove um edital dos favoritos exclusivamente para o usuário autenticado."""
    return desfavoritar_edital(db=db, edital_id=id, usuario_id=usuario_atual.id)


@router.post(
    "/{id}/alertas",
    status_code=status.HTTP_200_OK,
    summary="Ativar alertas por e-mail para um edital",
    description=(
        "Ativa o sistema de notificações por e-mail (atualizações e prazos de 3 dias, "
        "1 dia e no dia do encerramento) especificamente para o edital informado."
    ),
)
def ativar_alerta(
    id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    """Ativa o envio de e-mails para um edital específico e dispara verificação/envio imediato."""
    resultado = ativar_alerta_edital(db=db, edital_id=id, usuario_id=usuario_atual.id)
    bind = db.get_bind() if hasattr(db, "get_bind") else getattr(db, "bind", None)
    if bind is not None and (resultado["recem_ativado"] or resultado["notificacao_gerada"]):
        background_tasks.add_task(
            processar_alerta_ativado_em_segundo_plano,
            bind,
            usuario_id=usuario_atual.id,
            edital_id=id,
            enviar_confirmacao=resultado["recem_ativado"] and not resultado["notificacao_gerada"],
        )
    return {
        "message": resultado["message"],
        "edital_id": resultado["edital_id"],
        "usuario_id": resultado["usuario_id"],
        "notificar_email": True,
        "email_configurado": sendgrid_configurado(),
    }


@router.delete(
    "/{id}/alertas",
    status_code=status.HTTP_200_OK,
    summary="Desativar alertas por e-mail para um edital",
    description="Desativa o envio de notificações por e-mail para o edital informado.",
)
def desativar_alerta(
    id: int,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    """Desativa o envio de e-mails para o edital e descarta notificações pendentes dele."""
    return desativar_alerta_edital(db=db, edital_id=id, usuario_id=usuario_atual.id)

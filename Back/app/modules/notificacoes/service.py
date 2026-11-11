"""Serviços para registrar notificações de forma idempotente."""

from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.database import Edital, Favorito, Notificacao, TipoNotificacao


def listar_notificacoes_usuario(
    db: Session,
    usuario_id: int,
    limite: int = 50,
) -> list[Notificacao]:
    """Lista as notificações mais recentes de um usuário."""
    return (
        db.query(Notificacao)
        .filter(Notificacao.usuario_id == usuario_id)
        .order_by(Notificacao.criada_em.desc(), Notificacao.id.desc())
        .limit(limite)
        .all()
    )


def registrar_notificacao(
    db: Session,
    *,
    usuario_id: int,
    edital_id: int,
    tipo: TipoNotificacao,
    chave_evento: str,
) -> bool:
    """Cria uma notificação apenas uma vez para a ocorrência informada."""
    existente = (
        db.query(Notificacao)
        .filter(
            Notificacao.usuario_id == usuario_id,
            Notificacao.edital_id == edital_id,
            Notificacao.tipo == tipo,
            Notificacao.chave_evento == chave_evento,
        )
        .first()
    )
    if existente:
        return False

    db.add(
        Notificacao(
            usuario_id=usuario_id,
            edital_id=edital_id,
            tipo=tipo,
            chave_evento=chave_evento,
        )
    )
    return True


def notificar_edital_atualizado(db: Session, edital: Edital, hash_conteudo: str) -> int:
    """Registra uma notificação para cada usuário que favoritou o edital."""
    favoritos = db.query(Favorito).filter(Favorito.edital_id == edital.id).all()
    chave_evento = f"alteracao:{hash_conteudo}"
    return sum(
        registrar_notificacao(
            db,
            usuario_id=favorito.usuario_id,
            edital_id=edital.id,
            tipo=TipoNotificacao.EDITAL_ATUALIZADO,
            chave_evento=chave_evento,
        )
        for favorito in favoritos
    )


def gerar_notificacoes_prazo(
    db: Session,
    data_referencia: Optional[date] = None,
) -> int:
    """Gera alertas para editais que encerram em três dias, um dia ou hoje."""
    referencia = data_referencia or date.today()
    editais = (
        db.query(Edital)
        .filter(Edital.fim_inscricao.in_(
            [referencia, referencia + timedelta(days=1), referencia + timedelta(days=3)]
        ))
        .all()
    )

    total = 0
    for edital in editais:
        if not edital.fim_inscricao:
            continue
        dias_restantes = (edital.fim_inscricao - referencia).days
        if dias_restantes not in {0, 1, 3}:
            continue
        chave_evento = f"prazo:{referencia.isoformat()}"
        favoritos = db.query(Favorito).filter(Favorito.edital_id == edital.id).all()
        total += sum(
            registrar_notificacao(
                db,
                usuario_id=favorito.usuario_id,
                edital_id=edital.id,
                tipo=TipoNotificacao.PRAZO_ENCERRANDO,
                chave_evento=chave_evento,
            )
            for favorito in favoritos
        )

    db.commit()
    return total

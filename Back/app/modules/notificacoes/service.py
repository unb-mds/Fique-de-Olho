"""Serviços para alertas por edital e registro idempotente de notificações."""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import (
    AlertaEdital,
    Edital,
    Notificacao,
    StatusNotificacao,
    TipoNotificacao,
    Usuario,
)

DIAS_ALERTA_PRAZO = {0, 1, 3}
FUSO_BRASILIA = timezone(timedelta(hours=-3))


def data_hoje_brasilia() -> date:
    """Retorna a data atual no horário de Brasília (UTC-3), independente do timezone do servidor."""
    return datetime.now(FUSO_BRASILIA).date()


def listar_notificacoes_usuario(
    db: Session,
    usuario_id: int,
    limite: int = 50,
) -> list[Notificacao]:
    """Lista as notificações mais recentes de um usuário."""
    return (
        db.query(Notificacao)
        .options(joinedload(Notificacao.edital))
        .filter(Notificacao.usuario_id == usuario_id)
        .order_by(Notificacao.criada_em.desc(), Notificacao.id.desc())
        .limit(limite)
        .all()
    )


def listar_alertas_usuario(db: Session, usuario_id: int) -> list[int]:
    """Retorna os IDs dos editais com alertas por e-mail ativados pelo usuário."""
    registros = (
        db.query(AlertaEdital.edital_id)
        .filter(AlertaEdital.usuario_id == usuario_id)
        .order_by(AlertaEdital.edital_id)
        .all()
    )
    return [edital_id for (edital_id,) in registros]


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


def gerar_notificacao_prazo_edital(
    db: Session,
    *,
    edital: Edital,
    usuario_id: int,
    data_referencia: Optional[date] = None,
) -> bool:
    """Registra alerta de prazo se o edital encerrar em 3 dias, 1 dia ou hoje."""
    if not edital.fim_inscricao:
        return False
    referencia = data_referencia or data_hoje_brasilia()
    dias_restantes = (edital.fim_inscricao - referencia).days
    if dias_restantes not in DIAS_ALERTA_PRAZO:
        return False

    return registrar_notificacao(
        db,
        usuario_id=usuario_id,
        edital_id=edital.id,
        tipo=TipoNotificacao.PRAZO_ENCERRANDO,
        chave_evento=f"prazo:{referencia.isoformat()}",
    )


def ativar_alerta_edital(
    db: Session,
    edital_id: int,
    usuario_id: int,
    data_referencia: Optional[date] = None,
) -> dict[str, Any]:
    """Ativa alertas por e-mail para um edital específico e avalia o prazo imediatamente."""
    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edital com ID {edital_id} não encontrado.",
        )

    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if usuario is not None and not usuario.receber_emails:
        usuario.receber_emails = True

    alerta = (
        db.query(AlertaEdital)
        .filter(
            AlertaEdital.usuario_id == usuario_id,
            AlertaEdital.edital_id == edital_id,
        )
        .first()
    )
    recem_ativado = alerta is None
    if recem_ativado:
        db.add(AlertaEdital(usuario_id=usuario_id, edital_id=edital_id))

    notificacao_gerada = gerar_notificacao_prazo_edital(
        db,
        edital=edital,
        usuario_id=usuario_id,
        data_referencia=data_referencia,
    )
    db.commit()

    return {
        "message": "Alertas por e-mail ativados para este edital.",
        "edital_id": edital_id,
        "usuario_id": usuario_id,
        "notificar_email": True,
        "recem_ativado": recem_ativado,
        "notificacao_gerada": notificacao_gerada,
    }


def desativar_alerta_edital(
    db: Session,
    edital_id: int,
    usuario_id: int,
) -> dict[str, Any]:
    """Desativa alertas por e-mail para um edital específico e cancela pendentes."""
    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edital com ID {edital_id} não encontrado.",
        )

    alerta = (
        db.query(AlertaEdital)
        .filter(
            AlertaEdital.usuario_id == usuario_id,
            AlertaEdital.edital_id == edital_id,
        )
        .first()
    )
    if alerta:
        db.delete(alerta)

    db.query(Notificacao).filter(
        Notificacao.usuario_id == usuario_id,
        Notificacao.edital_id == edital_id,
        Notificacao.status == StatusNotificacao.PENDENTE,
    ).delete(synchronize_session=False)
    db.commit()

    return {
        "message": "Alertas por e-mail desativados para este edital.",
        "edital_id": edital_id,
        "usuario_id": usuario_id,
        "notificar_email": False,
    }


def notificar_edital_atualizado(db: Session, edital: Edital, hash_conteudo: str) -> int:
    """Registra uma notificação para cada usuário que ativou alertas para o edital."""
    alertas = db.query(AlertaEdital).filter(AlertaEdital.edital_id == edital.id).all()
    chave_evento = f"alteracao:{hash_conteudo}"
    return sum(
        registrar_notificacao(
            db,
            usuario_id=alerta.usuario_id,
            edital_id=edital.id,
            tipo=TipoNotificacao.EDITAL_ATUALIZADO,
            chave_evento=chave_evento,
        )
        for alerta in alertas
    )


def gerar_notificacoes_prazo(
    db: Session,
    data_referencia: Optional[date] = None,
) -> int:
    """Gera alertas para editais com sino ativo que encerram em três dias, um dia ou hoje."""
    referencia = data_referencia or data_hoje_brasilia()
    editais = (
        db.query(Edital)
        .filter(
            Edital.fim_inscricao.in_(
                [referencia, referencia + timedelta(days=1), referencia + timedelta(days=3)]
            )
        )
        .all()
    )

    total = 0
    for edital in editais:
        if not edital.fim_inscricao:
            continue
        dias_restantes = (edital.fim_inscricao - referencia).days
        if dias_restantes not in DIAS_ALERTA_PRAZO:
            continue
        chave_evento = f"prazo:{referencia.isoformat()}"
        alertas = db.query(AlertaEdital).filter(AlertaEdital.edital_id == edital.id).all()
        total += sum(
            registrar_notificacao(
                db,
                usuario_id=alerta.usuario_id,
                edital_id=edital.id,
                tipo=TipoNotificacao.PRAZO_ENCERRANDO,
                chave_evento=chave_evento,
            )
            for alerta in alertas
        )

    db.commit()
    return total

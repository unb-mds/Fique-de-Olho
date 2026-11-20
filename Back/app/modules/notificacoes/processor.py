"""Processamento de notificações pendentes e envio de emails via SendGrid."""

import logging
from datetime import datetime, timezone
from html import escape
from time import sleep
from typing import Any

from sqlalchemy.orm import Session, joinedload, sessionmaker

from app.core.config import settings
from app.core.database import (
    Edital,
    Notificacao,
    StatusNotificacao,
    TipoNotificacao,
    Usuario,
)
from app.modules.notificacoes.email_service import enviar_email

logger = logging.getLogger(__name__)


def sendgrid_configurado() -> bool:
    """Indica se as credenciais obrigatórias do SendGrid estão presentes."""
    return bool(settings.SENDGRID_API_KEY and settings.SENDGRID_FROM_EMAIL)


def _link_edital_html(edital: Edital) -> str:
    url = (edital.url_pagina or edital.url_pdf or "").strip()
    if not url:
        return ""
    return f'<p><a href="{escape(url)}">Ver edital</a></p>'


def _conteudo_notificacao(notificacao: Notificacao) -> tuple[str, str]:
    edital = notificacao.edital
    titulo = escape(edital.titulo or "Edital UnB")
    bloco_link = _link_edital_html(edital)

    if notificacao.tipo == TipoNotificacao.PRAZO_ENCERRANDO:
        prazo_texto = ""
        if edital.fim_inscricao:
            prazo_fmt = edital.fim_inscricao.strftime("%d/%m/%Y")
            prazo_texto = f" (prazo final: <strong>{prazo_fmt}</strong>)"
        return (
            f"Prazo de inscrição se aproximando: {edital.titulo}",
            f"<p>O prazo de inscrição do edital <strong>{titulo}</strong> "
            f"está se aproximando{prazo_texto}.</p>{bloco_link}",
        )

    return (
        f"Edital atualizado: {edital.titulo}",
        f"<p>O edital <strong>{titulo}</strong> foi atualizado.</p>{bloco_link}",
    )


def _conteudo_confirmacao_alerta(edital: Edital) -> tuple[str, str]:
    titulo = escape(edital.titulo or "Edital UnB")
    bloco_link = _link_edital_html(edital)
    prazo_bloco = ""
    if edital.fim_inscricao:
        prazo_bloco = (
            f"<p>Prazo final de inscrição registrado: "
            f"<strong>{edital.fim_inscricao.strftime('%d/%m/%Y')}</strong>.</p>"
        )
    return (
        f"Alertas ativados: {edital.titulo}",
        f"<p>Você ativou as notificações por e-mail para o edital "
        f"<strong>{titulo}</strong> no Fique de Olho.</p>"
        f"{prazo_bloco}"
        "<p>Você será avisado automaticamente quando houver atualizações neste edital "
        "e quando faltarem 3 dias, 1 dia e no dia do encerramento das inscrições.</p>"
        f"{bloco_link}",
    )


def processar_notificacoes_pendentes(
    db: Session,
    *,
    api_key: str,
    remetente: str,
    max_tentativas: int = 3,
    backoff_seconds: float = 1.0,
) -> dict[str, int]:
    """Envia notificações pendentes e atualiza o status de cada uma."""
    notificacoes = (
        db.query(Notificacao)
        .options(joinedload(Notificacao.usuario), joinedload(Notificacao.edital))
        .join(Usuario, Notificacao.usuario_id == Usuario.id)
        .filter(Notificacao.status == StatusNotificacao.PENDENTE)
        .filter(Usuario.receber_emails.is_(True))
        .order_by(Notificacao.id)
        .all()
    )
    enviadas = 0
    falhas = 0

    for notificacao in notificacoes:
        assunto, html = _conteudo_notificacao(notificacao)
        enviado = False
        ultimo_erro: Exception | None = None
        for tentativa in range(max_tentativas):
            try:
                enviar_email(
                    destinatario=notificacao.usuario.email,
                    assunto=assunto,
                    html=html,
                    api_key=api_key,
                    remetente=remetente,
                )
            except Exception as exc:
                ultimo_erro = exc
                logger.warning(
                    "Tentativa %s/%s falhou ao enviar notificação id=%s para %s: %s",
                    tentativa + 1,
                    max_tentativas,
                    notificacao.id,
                    notificacao.usuario.email,
                    exc,
                )
                if tentativa < max_tentativas - 1:
                    sleep(backoff_seconds * (2**tentativa))
                continue
            enviado = True
            break

        if not enviado:
            notificacao.status = StatusNotificacao.FALHOU
            falhas += 1
            logger.error(
                "Notificação id=%s marcada como FALHOU após %s tentativas: %s",
                notificacao.id,
                max_tentativas,
                ultimo_erro,
            )
        else:
            notificacao.status = StatusNotificacao.ENVIADA
            notificacao.enviada_em = datetime.now(timezone.utc)
            enviadas += 1
        db.commit()

    if enviadas or falhas:
        logger.info(
            "Processamento de notificações concluído: enviadas=%s, falhas=%s.",
            enviadas,
            falhas,
        )

    return {"enviadas": enviadas, "falhas": falhas}


def processar_notificacoes_configuradas(db: Session) -> dict[str, int]:
    """Processa pendentes usando as credenciais configuradas no ambiente."""
    if not sendgrid_configurado():
        raise RuntimeError(
            "Configuração do SendGrid ausente: defina SENDGRID_API_KEY e "
            "SENDGRID_FROM_EMAIL."
        )

    return processar_notificacoes_pendentes(
        db,
        api_key=settings.SENDGRID_API_KEY,
        remetente=settings.SENDGRID_FROM_EMAIL,
    )


def processar_notificacoes_se_configuradas(db: Session) -> dict[str, int] | None:
    """Processa pendentes quando o envio está configurado no ambiente."""
    if not sendgrid_configurado():
        logger.warning(
            "Envio de emails ignorado: configure SENDGRID_API_KEY e SENDGRID_FROM_EMAIL "
            "(SENDGRID_API_KEY=%s, SENDGRID_FROM_EMAIL=%s).",
            "definida" if settings.SENDGRID_API_KEY else "ausente",
            "definido" if settings.SENDGRID_FROM_EMAIL else "ausente",
        )
        return None
    return processar_notificacoes_configuradas(db)


def enviar_confirmacao_alerta_se_configurado(
    db: Session,
    *,
    usuario_id: int,
    edital_id: int,
) -> bool:
    """Envia email de confirmação de alerta ativado quando o SendGrid está configurado."""
    if not sendgrid_configurado():
        logger.warning(
            "Confirmação de alerta não enviada para usuario_id=%s edital_id=%s: "
            "SENDGRID_API_KEY ou SENDGRID_FROM_EMAIL ausente.",
            usuario_id,
            edital_id,
        )
        return False

    usuario = db.get(Usuario, usuario_id)
    edital = db.get(Edital, edital_id)
    if not usuario or not edital or not usuario.receber_emails:
        return False

    assunto, html = _conteudo_confirmacao_alerta(edital)
    enviar_email(
        destinatario=usuario.email,
        assunto=assunto,
        html=html,
        api_key=settings.SENDGRID_API_KEY,
        remetente=settings.SENDGRID_FROM_EMAIL,
    )
    return True


def processar_alerta_ativado_em_segundo_plano(
    bind: Any,
    *,
    usuario_id: int,
    edital_id: int,
    enviar_confirmacao: bool,
) -> None:
    """Dispara o envio imediato de notificações pendentes e/ou confirmação em sessão isolada."""
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=bind)
    db = session_factory()
    try:
        processar_notificacoes_se_configuradas(db)
        if enviar_confirmacao:
            enviar_confirmacao_alerta_se_configurado(
                db,
                usuario_id=usuario_id,
                edital_id=edital_id,
            )
    except Exception:
        logger.exception(
            "Falha ao processar envio imediato após ativação de alerta "
            "(usuario_id=%s, edital_id=%s).",
            usuario_id,
            edital_id,
        )
    finally:
        db.close()

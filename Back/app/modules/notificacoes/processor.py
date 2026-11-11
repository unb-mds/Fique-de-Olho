"""Processamento de notificações pendentes."""

from datetime import datetime, timezone
from html import escape
from time import sleep

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import Notificacao, StatusNotificacao, TipoNotificacao, Usuario
from app.modules.notificacoes.email_service import enviar_email


def _conteudo_notificacao(notificacao: Notificacao) -> tuple[str, str]:
    edital = notificacao.edital
    link = escape(edital.url_pagina)
    titulo = escape(edital.titulo)

    if notificacao.tipo == TipoNotificacao.PRAZO_ENCERRANDO:
        return (
            f"Prazo de inscrição se aproximando: {edital.titulo}",
            f"<p>O prazo de inscrição do edital <strong>{titulo}</strong> "
            f"está se aproximando.</p><p><a href=\"{link}\">Ver edital</a></p>",
        )

    return (
        f"Edital atualizado: {edital.titulo}",
        f"<p>O edital <strong>{titulo}</strong> foi atualizado.</p>"
        f"<p><a href=\"{link}\">Ver edital</a></p>",
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
        for tentativa in range(max_tentativas):
            try:
                enviar_email(
                    destinatario=notificacao.usuario.email,
                    assunto=assunto,
                    html=html,
                    api_key=api_key,
                    remetente=remetente,
                )
            except Exception:
                if tentativa < max_tentativas - 1:
                    sleep(backoff_seconds * (2**tentativa))
                continue
            enviado = True
            break

        if not enviado:
            notificacao.status = StatusNotificacao.FALHOU
            falhas += 1
        else:
            notificacao.status = StatusNotificacao.ENVIADA
            notificacao.enviada_em = datetime.now(timezone.utc)
            enviadas += 1
        db.commit()

    return {"enviadas": enviadas, "falhas": falhas}


def processar_notificacoes_configuradas(db: Session) -> dict[str, int]:
    """Processa pendentes usando as credenciais configuradas no ambiente."""
    if not settings.SENDGRID_API_KEY or not settings.SENDGRID_FROM_EMAIL:
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
    if not settings.SENDGRID_API_KEY or not settings.SENDGRID_FROM_EMAIL:
        return None
    return processar_notificacoes_configuradas(db)

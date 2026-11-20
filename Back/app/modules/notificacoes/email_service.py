"""Integração de email transacional com o SendGrid."""

import logging

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

logger = logging.getLogger(__name__)


def enviar_email(
    *,
    destinatario: str,
    assunto: str,
    html: str,
    api_key: str,
    remetente: str,
) -> bool:
    """Envia um email e retorna sucesso apenas quando o SendGrid aceita a mensagem."""
    mensagem = Mail(
        from_email=remetente,
        to_emails=destinatario,
        subject=assunto,
        html_content=html,
    )
    try:
        resposta = SendGridAPIClient(api_key).send(mensagem)
    except Exception as exc:
        detalhes = getattr(exc, "body", None)
        status_code = getattr(exc, "status_code", None)
        logger.error(
            "Erro ao enviar email via SendGrid para %s (status=%s): %s | detalhes=%s",
            destinatario,
            status_code,
            exc,
            detalhes,
        )
        raise

    if not 200 <= resposta.status_code < 300:
        logger.error(
            "SendGrid rejeitou email para %s com status %s: %s",
            destinatario,
            resposta.status_code,
            getattr(resposta, "body", None),
        )
        raise RuntimeError(
            f"SendGrid rejeitou o email com status {resposta.status_code}."
        )

    logger.info(
        "Email aceito pelo SendGrid para %s (status=%s, assunto=%r).",
        destinatario,
        resposta.status_code,
        assunto,
    )
    return True

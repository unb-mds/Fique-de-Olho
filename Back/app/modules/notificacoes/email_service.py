"""Integração de email transacional com o SendGrid."""

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


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
    resposta = SendGridAPIClient(api_key).send(mensagem)
    if not 200 <= resposta.status_code < 300:
        raise RuntimeError(
            f"SendGrid rejeitou o email com status {resposta.status_code}."
        )
    return True

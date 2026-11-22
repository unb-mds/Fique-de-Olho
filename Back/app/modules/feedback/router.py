"""Módulo de feedback de usuários (RF07)."""

from datetime import datetime
from html import escape
import logging
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import Feedback, get_db
from app.modules.notificacoes.email_service import enviar_email
from app.modules.notificacoes.processor import sendgrid_configurado

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["Feedback"])

_TIPO_LABEL = {
    "sugestao": "Sugestão",
    "problema": "Relato de problema",
    "elogio": "Elogio",
}


def _enviar_email_feedback(
    *,
    feedback_id: int,
    tipo: str,
    mensagem: str,
    email_usuario: Optional[str],
    pagina: Optional[str],
) -> None:
    destinatario = (settings.FEEDBACK_TO_EMAIL or "").strip()
    if not destinatario or not sendgrid_configurado():
        return

    tipo_fmt = _TIPO_LABEL.get(tipo, tipo)
    assunto = f"[Fique de Olho] Novo feedback ({tipo_fmt}) #{feedback_id}"
    remetente_info = escape(email_usuario) if email_usuario else "Não informado"
    pagina_info = escape(pagina) if pagina else "Não informada"
    mensagem_html = escape(mensagem).replace("\n", "<br>")

    html = (
        f"<h2>Novo feedback recebido no Fique de Olho (#{feedback_id})</h2>"
        f"<p><strong>Tipo:</strong> {escape(tipo_fmt)}</p>"
        f"<p><strong>E-mail do usuário:</strong> {remetente_info}</p>"
        f"<p><strong>Página:</strong> {pagina_info}</p>"
        f"<p><strong>Mensagem:</strong></p>"
        f"<blockquote>{mensagem_html}</blockquote>"
    )
    try:
        enviar_email(
            destinatario=destinatario,
            assunto=assunto,
            html=html,
            api_key=settings.SENDGRID_API_KEY,
            remetente=settings.SENDGRID_FROM_EMAIL,
        )
    except Exception:
        logger.exception("Falha ao enviar e-mail de feedback #%s para %s.", feedback_id, destinatario)


class FeedbackCriacao(BaseModel):
    """Payload enviado pelo formulário acessível de feedback."""

    tipo: Literal["sugestao", "problema", "elogio"] = Field(
        default="sugestao",
        description="Categoria do feedback enviado pelo usuário",
    )
    mensagem: str = Field(
        min_length=5,
        max_length=2000,
        description="Descrição da sugestão, crítica ou problema encontrado",
    )
    email: Optional[EmailStr] = Field(
        default=None,
        description="E-mail opcional para retorno da equipe",
    )
    pagina: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Rota ou contexto de onde o feedback foi enviado",
    )

    @field_validator("email", "pagina", mode="before")
    @classmethod
    def empty_str_to_none(cls, value: Optional[str]) -> Optional[str]:
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value

    @field_validator("mensagem")
    @classmethod
    def strip_mensagem(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 5:
            raise ValueError("A mensagem deve ter pelo menos 5 caracteres.")
        return cleaned


class FeedbackResposta(BaseModel):
    """Resposta retornada após registrar o feedback."""

    id: int
    tipo: str
    mensagem: str
    email: Optional[str] = None
    pagina: Optional[str] = None
    criado_em: datetime
    message: str = "Feedback enviado com sucesso. Obrigado por ajudar a melhorar o Fique de Olho!"

    model_config = ConfigDict(from_attributes=True)


@router.post(
    "",
    response_model=FeedbackResposta,
    status_code=status.HTTP_201_CREATED,
    summary="Enviar feedback",
    description="Registra sugestões, críticas ou relatos de problema enviados pelos usuários (RF07).",
)
@router.post(
    "/",
    response_model=FeedbackResposta,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def criar_feedback(
    dados: FeedbackCriacao,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> FeedbackResposta:
    registro = Feedback(
        tipo=dados.tipo,
        mensagem=dados.mensagem,
        email=str(dados.email) if dados.email else None,
        pagina=dados.pagina,
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)

    if settings.FEEDBACK_TO_EMAIL and sendgrid_configurado():
        background_tasks.add_task(
            _enviar_email_feedback,
            feedback_id=registro.id,
            tipo=registro.tipo,
            mensagem=registro.mensagem,
            email_usuario=registro.email,
            pagina=registro.pagina,
        )

    return FeedbackResposta(
        id=registro.id,
        tipo=registro.tipo,
        mensagem=registro.mensagem,
        email=registro.email,
        pagina=registro.pagina,
        criado_em=registro.criado_em,
    )

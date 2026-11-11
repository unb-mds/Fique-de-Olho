from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.database import StatusNotificacao, TipoNotificacao


class NotificacaoResposta(BaseModel):
    id: int
    edital_id: int
    edital_titulo: str
    tipo: TipoNotificacao
    status: StatusNotificacao
    criada_em: datetime
    enviada_em: datetime | None

    model_config = ConfigDict(from_attributes=True)

"""Rotina diária de geração e envio de notificações."""

import asyncio
import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.modules.notificacoes.processor import processar_notificacoes_se_configuradas
from app.modules.notificacoes.service import gerar_notificacoes_prazo

logger = logging.getLogger(__name__)


def executar_ciclo_notificacoes(
    session_factory: Callable[[], Session] = SessionLocal,
) -> dict[str, int | None]:
    """Gera alertas de prazo e tenta enviar as notificações pendentes."""
    db = session_factory()
    try:
        geradas = gerar_notificacoes_prazo(db)
        resultado_envio = processar_notificacoes_se_configuradas(db)
        return {
            "geradas": geradas,
            "enviadas": resultado_envio["enviadas"] if resultado_envio else None,
            "falhas": resultado_envio["falhas"] if resultado_envio else None,
        }
    finally:
        db.close()


async def executar_scheduler_notificacoes(
    intervalo_segundos: int = 24 * 60 * 60,
) -> None:
    """Executa o ciclo na inicialização e uma vez a cada intervalo configurado."""
    while True:
        try:
            executar_ciclo_notificacoes()
        except Exception:
            logger.exception("Falha no ciclo automático de notificações.")
        await asyncio.sleep(intervalo_segundos)

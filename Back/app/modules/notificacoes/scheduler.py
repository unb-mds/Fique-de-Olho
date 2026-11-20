"""Rotina periódica de geração e envio de notificações."""

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
        resultado = {
            "geradas": geradas,
            "enviadas": resultado_envio["enviadas"] if resultado_envio else None,
            "falhas": resultado_envio["falhas"] if resultado_envio else None,
        }
        logger.info("Ciclo automático de notificações concluído: %s", resultado)
        return resultado
    finally:
        db.close()


async def executar_scheduler_notificacoes(
    intervalo_segundos: int = 60 * 60,
) -> None:
    """Executa o ciclo na inicialização e uma vez a cada intervalo configurado sem bloquear o loop."""
    try:
        while True:
            try:
                await asyncio.to_thread(executar_ciclo_notificacoes)
            except Exception:
                logger.exception("Falha no ciclo automático de notificações.")
            await asyncio.sleep(intervalo_segundos)
    except asyncio.CancelledError:
        logger.info("Scheduler periódico de notificações encerrado com sucesso.")
        return

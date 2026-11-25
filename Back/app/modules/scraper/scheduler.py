"""Agendador em segundo plano (Scheduler/Cron) para coleta periódica automatizada de editais (Issue #74)."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, Iterator, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.editais.service import invalidar_cache_editais
from app.modules.scraper.service import sync_all_portais

logger = logging.getLogger(__name__)
SCRAPER_SYNC_LOCK = threading.Lock()


class ColetaEmAndamentoError(RuntimeError):
    """Lançada quando uma nova coleta é solicitada com outra já em execução."""


@contextmanager
def controlar_concorrencia_coleta() -> Iterator[None]:
    """Garante exclusão mútua não bloqueante entre execuções manuais e periódicas de coleta."""
    if not SCRAPER_SYNC_LOCK.acquire(blocking=False):
        raise ColetaEmAndamentoError("Já existe uma coleta de editais em andamento.")
    try:
        yield
    finally:
        SCRAPER_SYNC_LOCK.release()


def executar_ciclo_scraping(
    session_factory: Callable[[], Session] = SessionLocal,
    orgaos: Optional[List[str]] = None,
    max_items_per_orgao: Optional[int] = 100,
    fetch_docs: Optional[bool] = None,
    enable_pdf_enrichment: Optional[bool] = None,
    skip_closed_existing: bool = False,
    recent_years_window: Optional[int] = None,
) -> dict[str, Any]:
    """Executa um ciclo completo de sincronização periódica dos portais configurados.

    Garante isolamento de erros por órgão (registrando falhas na tabela ``coletas``),
    captura exceções inesperadas sem propagá-las ao loop assíncrono e fecha a sessão
    do banco de dados no bloco ``finally``.
    """
    try:
        with controlar_concorrencia_coleta():
            eff_fetch_docs = settings.SCRAPER_SCHEDULER_FETCH_DOCS if fetch_docs is None else fetch_docs
            eff_pdf_enrichment = (
                settings.SCRAPER_SCHEDULER_PDF_ENRICHMENT
                if enable_pdf_enrichment is None
                else enable_pdf_enrichment
            )
            db = session_factory()
            try:
                resultado = sync_all_portais(
                    db=db,
                    orgaos=orgaos,
                    max_items_per_orgao=max_items_per_orgao,
                    fetch_docs=eff_fetch_docs,
                    enable_pdf_enrichment=eff_pdf_enrichment,
                    skip_closed_existing=skip_closed_existing,
                    recent_years_window=recent_years_window,
                )
                invalidar_cache_editais()
                return resultado
            except Exception as exc:
                logger.exception("Falha no ciclo automático de coleta de editais.")
                return {
                    "status": "error",
                    "erro": str(exc),
                }
            finally:
                db.close()
    except ColetaEmAndamentoError:
        logger.warning("Ciclo periódico de coleta ignorado: já existe uma coleta de editais em andamento.")
        return {"status": "skipped", "motivo": "coleta_em_andamento"}


async def executar_scheduler_scraper(
    intervalo_segundos: int | float = 12 * 60 * 60,
    run_on_startup: bool = False,
) -> None:
    """Executa a coleta periódica em segundo plano a cada ``intervalo_segundos``.

    Roda ``executar_ciclo_scraping`` em thread separada (``asyncio.to_thread``) para
    nunca bloquear o event loop da API FastAPI e encerra de forma limpa quando cancelado.
    """
    try:
        if not run_on_startup:
            await asyncio.sleep(intervalo_segundos)

        while True:
            try:
                await asyncio.to_thread(executar_ciclo_scraping)
            except Exception:
                logger.exception("Falha inesperada na execução do scheduler de coleta de editais.")
            await asyncio.sleep(intervalo_segundos)
    except asyncio.CancelledError:
        logger.info("Scheduler periódico de coleta de editais encerrado com sucesso.")
        return

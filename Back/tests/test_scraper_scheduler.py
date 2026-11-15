"""Testes TDD da Issue #74 — Agendador periódico (Scheduler/Cron) de coleta automatizada de editais."""

import asyncio
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base
from app.modules.editais.models import Coleta, Edital
from app.modules.scraper import SCRAPERS_REGISTRY


def test_settings_possui_configuracoes_do_scraper_scheduler():
    assert hasattr(settings, "SCRAPER_SCHEDULER_ENABLED")
    assert hasattr(settings, "SCRAPER_SCHEDULER_INTERVAL_HOURS")
    assert hasattr(settings, "SCRAPER_SCHEDULER_RUN_ON_STARTUP")
    assert isinstance(settings.SCRAPER_SCHEDULER_ENABLED, bool)
    assert settings.SCRAPER_SCHEDULER_INTERVAL_HOURS == 12
    assert settings.SCRAPER_SCHEDULER_RUN_ON_STARTUP is False


def test_executar_ciclo_scraping_chama_sync_all_portais_e_fecha_sessao(monkeypatch):
    from app.modules.scraper import scheduler

    eventos = []

    class FakeSession:
        def close(self):
            eventos.append("close")

    def fake_sync_all_portais(db, orgaos=None, max_items_per_orgao=100, **kwargs):
        eventos.append(("sync", orgaos, max_items_per_orgao))
        return {
            "status": "success",
            "portais_processados": 2,
            "editais_encontrados": 5,
            "novos_editais": 3,
            "editais_atualizados": 1,
        }

    monkeypatch.setattr(scheduler, "sync_all_portais", fake_sync_all_portais)

    resultado = scheduler.executar_ciclo_scraping(
        session_factory=lambda: FakeSession(),
        orgaos=["DEG", "DPG"],
        max_items_per_orgao=25,
    )

    assert resultado["status"] == "success"
    assert resultado["novos_editais"] == 3
    assert eventos == [("sync", ["DEG", "DPG"], 25), "close"]


def test_executar_ciclo_scraping_captura_excecao_inesperada_e_fecha_sessao(monkeypatch, caplog):
    from app.modules.scraper import scheduler

    eventos = []

    class FakeSession:
        def close(self):
            eventos.append("close")

    def boom(*args, **kwargs):
        raise RuntimeError("Falha catastrófica de conexão com o banco")

    monkeypatch.setattr(scheduler, "sync_all_portais", boom)

    with caplog.at_level("ERROR"):
        resultado = scheduler.executar_ciclo_scraping(session_factory=lambda: FakeSession())

    assert resultado["status"] == "error"
    assert "Falha catastrófica" in resultado["erro"]
    assert eventos == ["close"]
    assert any("Falha no ciclo automático de coleta de editais" in rec.message for rec in caplog.records)


def test_executar_ciclo_scraping_isola_falha_de_portal_e_grava_coletas(monkeypatch):
    """Falha em um portal é registrada na tabela coletas sem interromper os demais órgãos."""
    from app.modules.scraper import scheduler
    from app.modules.scraper import service as scraper_service

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    fake_ok = MagicMock()
    fake_ok.fetch_editais.return_value = [
        {
            "titulo": "Edital DEG Nº 10/2026 - Monitoria de Graduação",
            "link": "https://deg.unb.br/editais/monitoria-10-2026",
            "data_publicacao": "2026-10-01",
        }
    ]
    fake_fail = MagicMock()
    fake_fail.fetch_editais.side_effect = RuntimeError("Timeout no portal externo")

    monkeypatch.setitem(SCRAPERS_REGISTRY, "DEG", fake_ok)
    monkeypatch.setitem(SCRAPERS_REGISTRY, "DPG", fake_fail)
    monkeypatch.setattr(scraper_service, "processar_notificacoes_se_configuradas", lambda db: None)
    monkeypatch.setattr(scraper_service, "gerar_notificacoes_prazo", lambda db: 0)

    resumo = scheduler.executar_ciclo_scraping(
        session_factory=TestingSession,
        orgaos=["DEG", "DPG"],
        max_items_per_orgao=10,
    )

    assert resumo["status"] == "success"
    assert resumo["novos_editais"] == 1
    assert resumo["portais"]["DEG"]["status"] == "success"
    assert resumo["portais"]["DPG"]["status"] == "error"

    with TestingSession() as db:
        assert db.query(Edital).count() == 1
        coletas = {c.fonte: c for c in db.query(Coleta).all()}
        assert coletas["DEG"].status == "concluida"
        assert coletas["DPG"].status == "falhou"
        assert "Timeout no portal externo" in (coletas["DPG"].mensagem_erro or "")


@pytest.mark.asyncio
async def test_executar_scheduler_scraper_run_on_startup_e_cancelamento_gracioso(monkeypatch):
    from app.modules.scraper import scheduler

    execucoes = []
    evento_rodou = asyncio.Event()

    def fake_ciclo():
        execucoes.append("ciclo")
        evento_rodou.set()
        return {"status": "success"}

    monkeypatch.setattr(scheduler, "executar_ciclo_scraping", fake_ciclo)

    task = asyncio.create_task(
        scheduler.executar_scheduler_scraper(intervalo_segundos=3600, run_on_startup=True)
    )
    await asyncio.wait_for(evento_rodou.wait(), timeout=2.0)
    assert execucoes == ["ciclo"]

    task.cancel()
    resultados = await asyncio.gather(task, return_exceptions=True)
    assert resultados == [None]


@pytest.mark.asyncio
async def test_executar_scheduler_scraper_aguarda_intervalo_quando_run_on_startup_false(monkeypatch):
    from app.modules.scraper import scheduler

    execucoes = []
    segundo_ciclo = asyncio.Event()

    def fake_ciclo():
        execucoes.append("ciclo")
        if len(execucoes) >= 2:
            segundo_ciclo.set()
        return {"status": "success"}

    monkeypatch.setattr(scheduler, "executar_ciclo_scraping", fake_ciclo)

    task = asyncio.create_task(
        scheduler.executar_scheduler_scraper(intervalo_segundos=0.01, run_on_startup=False)
    )
    await asyncio.wait_for(segundo_ciclo.wait(), timeout=2.0)
    assert len(execucoes) >= 2

    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_executar_scheduler_scraper_sobrevive_a_excecao_no_ciclo(monkeypatch, caplog):
    from app.modules.scraper import scheduler

    chamadas = 0
    recuperou = asyncio.Event()

    def ciclo_instavel():
        nonlocal chamadas
        chamadas += 1
        if chamadas == 1:
            raise RuntimeError("Erro transitório na thread de scraping")
        recuperou.set()
        return {"status": "success"}

    monkeypatch.setattr(scheduler, "executar_ciclo_scraping", ciclo_instavel)

    with caplog.at_level("ERROR"):
        task = asyncio.create_task(
            scheduler.executar_scheduler_scraper(intervalo_segundos=0.01, run_on_startup=True)
        )
        await asyncio.wait_for(recuperou.wait(), timeout=2.0)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert chamadas >= 2
    assert any("Falha inesperada na execução do scheduler de coleta" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_lifespan_inicia_e_cancela_scraper_scheduler_quando_habilitado(monkeypatch):
    import app.main as main_mod

    eventos = []

    async def fake_scraper_scheduler(intervalo_segundos: int, run_on_startup: bool = False):
        eventos.append(("start", intervalo_segundos, run_on_startup))
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            eventos.append("cancelled")
            raise

    monkeypatch.setattr(settings, "NOTIFICATION_SCHEDULER_ENABLED", False)
    monkeypatch.setattr(settings, "SCRAPER_SCHEDULER_ENABLED", True)
    monkeypatch.setattr(settings, "SCRAPER_SCHEDULER_INTERVAL_HOURS", 6)
    monkeypatch.setattr(settings, "SCRAPER_SCHEDULER_RUN_ON_STARTUP", False)
    monkeypatch.setattr(main_mod, "executar_scheduler_scraper", fake_scraper_scheduler, raising=False)

    async with main_mod.lifespan(main_mod.app):
        await asyncio.sleep(0)
        assert eventos == [("start", 6 * 3600, False)]

    assert eventos == [("start", 6 * 3600, False), "cancelled"]


@pytest.mark.asyncio
async def test_lifespan_nao_inicia_scraper_scheduler_quando_desabilitado(monkeypatch):
    import app.main as main_mod

    chamado = False

    async def fail_if_called(*args, **kwargs):
        nonlocal chamado
        chamado = True

    monkeypatch.setattr(settings, "NOTIFICATION_SCHEDULER_ENABLED", False)
    monkeypatch.setattr(settings, "SCRAPER_SCHEDULER_ENABLED", False)
    monkeypatch.setattr(main_mod, "executar_scheduler_scraper", fail_if_called, raising=False)

    async with main_mod.lifespan(main_mod.app):
        await asyncio.sleep(0)

    assert chamado is False

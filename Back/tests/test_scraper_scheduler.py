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


def test_sync_portal_incremental_pula_encerrados_e_atualiza_abertos(monkeypatch):
    """skip_closed_existing=True pula ENCERRADO sem buscar docs, mas atualiza ABERTO e insere novos."""
    from app.core.database import StatusEdital
    from app.modules.scraper import service as scraper_service

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with TestingSession() as db:
        encerrado = Edital(
            titulo="Edital Encerrado 2025",
            url_pagina="https://deg.unb.br/editais/encerrado-2025",
            orgao_emissor="DEG",
            status=StatusEdital.ENCERRADO,
        )
        aberto = Edital(
            titulo="Edital Aberto DEG 01/2026",
            url_pagina="https://deg.unb.br/editais/aberto-2026",
            orgao_emissor="DEG",
            status=StatusEdital.ABERTO,
        )
        db.add_all([encerrado, aberto])
        db.commit()

        docs_chamados = []

        fake_scraper = MagicMock()
        fake_scraper.fetch_editais.return_value = [
            {
                "titulo": "Edital Encerrado 2025",
                "link": "https://deg.unb.br/editais/encerrado-2025",
                "data_publicacao": "2025-05-01",
                "ano": 2025,
            },
            {
                "titulo": "Edital Aberto DEG 01/2026",
                "link": "https://deg.unb.br/editais/aberto-2026",
                "data_publicacao": "2026-10-01",
                "ano": 2026,
            },
            {
                "titulo": "Edital Novo DEG 02/2026",
                "link": "https://deg.unb.br/editais/novo-2026",
                "data_publicacao": "2026-11-24",
                "ano": 2026,
            },
        ]

        def fake_fetch_docs(url):
            docs_chamados.append(url)
            if "aberto-2026" in url:
                return [
                    {
                        "titulo": "Resultado Final",
                        "link": "https://deg.unb.br/docs/resultado-final-2026.pdf",
                        "tipo": "resultado_final",
                    }
                ]
            return []

        fake_scraper.fetch_documentos.side_effect = fake_fetch_docs

        monkeypatch.setitem(SCRAPERS_REGISTRY, "DEG", fake_scraper)
        monkeypatch.setattr(scraper_service, "processar_notificacoes_se_configuradas", lambda _db: None)

        res = scraper_service.sync_portal_editais(
            db=db,
            orgao="DEG",
            max_items=10,
            fetch_docs=True,
            enable_pdf_enrichment=False,
            skip_closed_existing=True,
            recent_years_window=2,
        )

        assert res["status"] == "success"
        assert res["novos_editais"] == 1
        assert res["editais_atualizados"] == 1
        assert res["editais_ignorados"] == 1
        assert docs_chamados == [
            "https://deg.unb.br/editais/aberto-2026",
            "https://deg.unb.br/editais/novo-2026",
        ]
        db.refresh(aberto)
        assert aberto.status == StatusEdital.ENCERRADO
        assert db.query(Edital).count() == 3


def test_janela_movel_de_anos_acompanha_virada_de_ano(monkeypatch):
    """recent_years_window=2 acompanha dinamicamente o ano atual (ex.: em 2027 aceita 2026 e 2027)."""
    from datetime import date as real_date
    from app.core.database import StatusEdital
    from app.modules.scraper import scheduler
    from app.modules.scraper import service as scraper_service

    class FakeDate2027(real_date):
        @classmethod
        def today(cls):
            return cls(2027, 2, 15)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with TestingSession() as db:
        # Edital de 2025 que ainda está ABERTO no banco deve continuar recebendo atualizações mesmo em 2027
        db.add(
            Edital(
                titulo="Edital 2025 Ainda Aberto",
                url_pagina="https://www.cebraspe.org.br/concursos/UNB_25_ABERTO",
                orgao_emissor="CEBRASPE",
                status=StatusEdital.ABERTO,
            )
        )
        db.commit()

    fake_cebraspe = MagicMock()
    fake_cebraspe.fetch_editais.return_value = [
        {
            "titulo": "Vestibular Antigo 2015",
            "link": "https://www.cebraspe.org.br/concursos/VESTUNB_15_2_REMANESCENTES",
            "data_publicacao": "2015-01-01",
            "ano": 2015,
        },
        {
            "titulo": "Vestibular 2025 Novo Fora da Janela de 2027",
            "link": "https://www.cebraspe.org.br/concursos/VESTUNB_25_NOVO",
            "data_publicacao": "2025-06-01",
            "ano": 2025,
        },
        {
            "titulo": "Edital 2025 Ainda Aberto",
            "link": "https://www.cebraspe.org.br/concursos/UNB_25_ABERTO",
            "data_publicacao": "2025-11-01",
            "ano": 2025,
        },
        {
            "titulo": "Vestibular 2026 Dentro da Janela de 2027",
            "link": "https://www.cebraspe.org.br/concursos/VESTUNB_26",
            "data_publicacao": "2026-10-01",
            "ano": 2026,
        },
        {
            "titulo": "Vestibular 2027 Ano Atual",
            "link": "https://www.cebraspe.org.br/concursos/VESTUNB_27",
            "data_publicacao": "2027-01-15",
            "ano": 2027,
        },
    ]
    fake_cebraspe.fetch_documentos.return_value = []

    monkeypatch.setattr(scraper_service, "date", FakeDate2027)
    monkeypatch.setitem(SCRAPERS_REGISTRY, "CEBRASPE", fake_cebraspe)
    monkeypatch.setattr(scraper_service, "processar_notificacoes_se_configuradas", lambda _db: None)
    monkeypatch.setattr(scraper_service, "gerar_notificacoes_prazo", lambda _db: 0)

    resumo = scheduler.executar_ciclo_scraping(
        session_factory=TestingSession,
        orgaos=["CEBRASPE"],
        max_items_per_orgao=10,
        fetch_docs=True,
        enable_pdf_enrichment=False,
        skip_closed_existing=True,
        recent_years_window=2,
    )

    assert resumo["status"] == "success"
    assert resumo["novos_editais"] == 2
    assert resumo["editais_ignorados"] == 2
    chamados = [call.args[0] for call in fake_cebraspe.fetch_documentos.call_args_list]
    assert chamados == [
        "https://www.cebraspe.org.br/concursos/UNB_25_ABERTO",
        "https://www.cebraspe.org.br/concursos/VESTUNB_26",
        "https://www.cebraspe.org.br/concursos/VESTUNB_27",
    ]


def test_reprocessamento_edital_sem_fim_inscricao_nao_rechama_gemini_nem_pdf(monkeypatch):
    """Edital inalterado (mesmo hash) sem fim_inscricao não deve re-chamar Gemini nem baixar PDF de novo."""
    import httpx
    from app.modules.scraper import pipeline as pipeline_mod
    from app.modules.scraper import summarizer as summarizer_mod
    from app.modules.scraper.pdf import PDFDocumentExtraction

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fake-key")
    summarizer_mod.reset_gemini_rate_limit_state()

    pdf_calls = {"n": 0}
    llm_calls = {"n": 0}

    def fake_pdf(url, timeout=10.0):
        pdf_calls["n"] += 1
        return PDFDocumentExtraction(
            source=url,
            num_pages=1,
            full_text="EDITAL DEG Nº 80/2026 - Convocação de fluxo contínuo para estudantes da UnB.",
        )

    def fake_gemini(req: httpx.Request) -> httpx.Response:
        llm_calls["n"] += 1
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": '{"resumo": "Convocação de fluxo contínuo para estudantes da UnB."}'
                                }
                            ]
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(fake_gemini)
    monkeypatch.setattr(pipeline_mod, "extract_pdf", fake_pdf)
    monkeypatch.setattr(
        summarizer_mod,
        "_build_client",
        lambda timeout: httpx.Client(transport=transport, timeout=timeout),
    )

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    payload = {
        "titulo": "Edital DEG Nº 80/2026 - Fluxo Contínuo",
        "link": "https://deg.unb.br/editais/80-2026",
        "url_pdf": "https://deg.unb.br/editais/80-2026.pdf",
        "data_publicacao": "2026-11-20",
    }

    with TestingSession() as db:
        e1 = pipeline_mod.upsert_edital(db, payload, enable_pdf_enrichment=True)
        assert e1.fim_inscricao is None
        assert pdf_calls["n"] == 1
        assert llm_calls["n"] == 1

        # Segunda execução sem alteração: NÃO baixa PDF nem chama Gemini novamente
        e2 = pipeline_mod.upsert_edital(db, payload, enable_pdf_enrichment=True)
        assert e2.id == e1.id
        assert pdf_calls["n"] == 1
        assert llm_calls["n"] == 1


def test_gemini_circuit_breaker_abre_apos_429_consecutivos(monkeypatch):
    """Após 3 falhas HTTP 429 consecutivas, o circuit breaker evita novas chamadas HTTP até o reset."""
    import httpx
    from app.modules.scraper import summarizer as summarizer_mod

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(settings, "GEMINI_RETRY_DELAY_SECONDS", 0.0)
    summarizer_mod.reset_gemini_rate_limit_state()

    http_calls = {"n": 0}

    def always_429(req: httpx.Request) -> httpx.Response:
        http_calls["n"] += 1
        return httpx.Response(429, json={"error": {"message": "Quota exceeded"}})

    transport = httpx.MockTransport(always_429)
    monkeypatch.setattr(
        summarizer_mod,
        "_build_client",
        lambda timeout: httpx.Client(transport=transport, timeout=timeout),
    )

    try:
        for i in range(5):
            summarizer_mod.enrich_edital_with_llm(
                titulo="AQUI",
                texto_extraido=f"1. DO OBJETO\nSeleção de estudantes da UnB número {i}.",
                orgao_emissor="DEG",
                pedir_metadados=False,
            )

        # Apenas 3 chamadas lógicas (cada uma com 1 tentativa + 1 retry = 6 HTTP calls);
        # a 4ª e 5ª caíram imediatamente no fallback sem fazer requisição HTTP.
        assert http_calls["n"] == 6
        assert summarizer_mod.is_gemini_rate_limit_open() is True
    finally:
        summarizer_mod.reset_gemini_rate_limit_state()

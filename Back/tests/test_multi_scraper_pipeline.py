"""Testes TDD da Issue #78 — Conexão multi-órgão de SCRAPERS_REGISTRY ao pipeline, service e endpoint /sync."""

from typing import Any, Dict, List, Optional
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, Edital, EditalDocumento, StatusEdital, get_db
from app.main import app
from app.modules.editais.models import Coleta
from app.modules.scraper import SCRAPERS_REGISTRY
from app.modules.scraper.base import BaseScraper
from app.modules.scraper.pdf import PDFDocumentExtraction
from app.modules.scraper.pipeline import run_pipeline
from app.modules.scraper.service import sync_orgaos_editais


class FakePortalScraper(BaseScraper):
    """Implementação fake de BaseScraper para testes isolados de pipeline multi-órgão."""

    def __init__(
        self,
        orgao: str,
        items: List[Dict[str, Any]],
        docs_by_url: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        should_fail: bool = False,
    ):
        self._orgao = orgao
        self._items = items
        self._docs_by_url = docs_by_url or {}
        self._should_fail = should_fail

    @property
    def orgao_origem(self) -> str:
        return self._orgao

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        if self._should_fail:
            raise ConnectionError(f"Timeout simulado no portal {self._orgao}")
        return list(self._items)

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        return list(self._docs_by_url.get(edital_url, []))


@pytest.fixture
def db_session(monkeypatch):
    """Sessão SQLite em memória isolada com mock de extract_pdf."""
    import app.modules.scraper.pipeline as pipeline_mod

    monkeypatch.setattr(
        pipeline_mod,
        "extract_pdf",
        lambda url, **kw: PDFDocumentExtraction(
            source=str(url), num_pages=1, full_text="", pages=[], tables=[]
        ),
    )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA ignore_check_constraints = OFF")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


def test_run_pipeline_accepts_base_scraper_instance_and_orgao_sigla(db_session, monkeypatch):
    """Valida que run_pipeline aceita tanto instância de BaseScraper quanto sigla do órgão em SCRAPERS_REGISTRY."""
    dpg_url = "https://dpg.unb.br/editais/pos-2026"
    dpg_pdf = "https://dpg.unb.br/arquivos/edital_pos_2026.pdf"
    fake_dpg = FakePortalScraper(
        orgao="DPG",
        items=[
            {
                "titulo": "Edital DPG Pós-Graduação 01/2026",
                "link": dpg_url,
                "data_publicacao": "2026-08-10",
            }
        ],
        docs_by_url={
            dpg_url: [
                {"titulo": "Edital de Abertura", "link": dpg_pdf, "tipo": "original"},
                {"titulo": "Retificação 01", "link": "https://dpg.unb.br/arquivos/ret_01.pdf", "tipo": "retificacao"},
            ]
        },
    )

    # 1. Passando instância direta de BaseScraper
    salvos_inst = run_pipeline(db=db_session, scraper=fake_dpg, enable_pdf_enrichment=False)
    assert len(salvos_inst) == 1
    assert salvos_inst[0].orgao_emissor == "DPG"
    assert salvos_inst[0].url_pagina == dpg_url
    assert salvos_inst[0].url_pdf == dpg_pdf
    assert len(salvos_inst[0].documentos) == 2

    # 2. Passando sigla de órgão registrada em SCRAPERS_REGISTRY (idempotência: não duplica)
    monkeypatch.setitem(SCRAPERS_REGISTRY, "DPG", fake_dpg)
    salvos_sigla = run_pipeline(db=db_session, orgao="DPG", enable_pdf_enrichment=False)
    assert len(salvos_sigla) == 1
    assert db_session.query(Edital).count() == 1
    assert db_session.query(EditalDocumento).count() == 2


def test_sync_orgaos_editais_single_and_all_with_error_isolation(db_session, monkeypatch):
    """Valida sync_orgaos_editais filtrando por órgão específico ou iterando todos com isolamento de falhas e Coleta."""
    fake_cead = FakePortalScraper(
        orgao="CEAD",
        items=[
            {
                "titulo": "Edital Tutoria UAB/CEAD 2026",
                "link": "https://cead.unb.br/editais/tutoria-2026",
                "data_publicacao": "2026-09-01",
                "documentos": [
                    {"titulo": "Edital UAB", "link": "https://cead.unb.br/docs/uab.pdf", "tipo": "original"}
                ],
            }
        ],
    )
    fake_concursos = FakePortalScraper(
        orgao="CONCURSOS",
        items=[
            {
                "titulo": "Concurso Docente Magistério Superior 2026",
                "link": "https://concursos.unb.br/editais/docente-2026",
                "data_publicacao": "2026-09-15",
                "documentos": [
                    {
                        "titulo": "Resultado Final",
                        "link": "https://concursos.unb.br/docs/resultado_final.pdf",
                        "tipo": "resultado_final",
                    }
                ],
            }
        ],
    )
    fake_broken = FakePortalScraper(orgao="FAL", items=[], should_fail=True)

    monkeypatch.setattr(
        "app.modules.scraper.SCRAPERS_REGISTRY",
        {"CEAD": fake_cead, "CONCURSOS": fake_concursos, "FAL": fake_broken},
    )

    # A. Sincronização de um único órgão (orgao="CEAD")
    res_single = sync_orgaos_editais(db=db_session, orgao="CEAD", max_items_per_orgao=10)
    assert res_single["status"] == "success"
    assert res_single["fonte"] == "CEAD"
    assert res_single["novos_editais"] == 1
    assert db_session.query(Edital).count() == 1

    # B. Sincronização de todos os órgãos (orgao=None): CEAD já existe (0 novos), CONCURSOS insere 1, FAL falha isolado
    res_all = sync_orgaos_editais(db=db_session, orgao=None, max_items_per_orgao=10)
    assert res_all["status"] == "success"
    assert res_all["portais_processados"] == 3
    assert res_all["novos_editais"] == 1
    assert res_all["portais"]["CEAD"]["novos_editais"] == 0
    assert res_all["portais"]["CONCURSOS"]["novos_editais"] == 1
    assert res_all["portais"]["FAL"]["status"] == "error"

    # Verifica que CONCURSOS entrou como ENCERRADO por ter resultado_final
    ed_conc = db_session.query(Edital).filter_by(orgao_emissor="CONCURSOS").one()
    assert ed_conc.status == StatusEdital.ENCERRADO

    # Verifica auditoria na tabela coletas (concluida vs falhou)
    coletas = db_session.query(Coleta).all()
    status_por_fonte = {(c.fonte, c.status) for c in coletas}
    assert ("CEAD", "concluida") in status_por_fonte
    assert ("CONCURSOS", "concluida") in status_por_fonte
    assert ("FAL", "falhou") in status_por_fonte


def test_post_sync_endpoint_supports_orgao_and_default_all(db_session, monkeypatch):
    """Valida rota POST /api/v1/editais/sync com orgao específico, sem orgao (todos) e com orgao inválido (400)."""
    fake_deg = FakePortalScraper(
        orgao="DEG",
        items=[
            {
                "titulo": "Edital Monitoria DEG 2026",
                "link": "https://deg.unb.br/editais/mon-2026",
                "url_pdf": "https://deg.unb.br/editais/mon-2026.pdf",
                "data_publicacao": "2026-10-01",
            }
        ],
    )
    fake_dpg = FakePortalScraper(
        orgao="DPG",
        items=[
            {
                "titulo": "Edital PIBIC DPG 2026",
                "link": "https://dpg.unb.br/editais/pibic-2026",
                "url_pdf": "https://dpg.unb.br/editais/pibic-2026.pdf",
                "data_publicacao": "2026-10-02",
            }
        ],
    )
    monkeypatch.setattr(
        "app.modules.scraper.SCRAPERS_REGISTRY",
        {"DEG": fake_deg, "DPG": fake_dpg},
    )

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)

        # 1. Filtrando por órgão específico (?orgao=DPG&max_itens=15)
        r_dpg = client.post("/api/v1/editais/sync?orgao=DPG&max_itens=15")
        assert r_dpg.status_code == 200
        body_dpg = r_dpg.json()
        assert body_dpg["status"] == "success"
        assert body_dpg["fonte"] == "DPG"
        assert body_dpg["novos_editais"] == 1

        # 2. Omitindo orgao -> sincroniza todos os órgãos registrados em SCRAPERS_REGISTRY
        r_all = client.post("/api/v1/editais/sync?max_itens=15")
        assert r_all.status_code == 200
        body_all = r_all.json()
        assert body_all["status"] == "success"
        assert body_all["portais_processados"] == 2
        assert body_all["novos_editais"] == 1  # apenas DEG era novo
        assert set(body_all["portais"].keys()) == {"DEG", "DPG"}

        # 3. Órgão inexistente -> HTTP 400
        r_invalid = client.post("/api/v1/editais/sync?orgao=ORGAO_INEXISTENTE")
        assert r_invalid.status_code == 400
    finally:
        app.dependency_overrides.clear()

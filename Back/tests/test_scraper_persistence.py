import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, Edital, EditalDocumento, StatusEdital, TipoDocumento
from app.modules.scraper.pipeline import parse_data_publicacao, run_pipeline, upsert_edital


@pytest.fixture
def db_session():
    """Cria banco SQLite em memória isolado."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


def test_parse_data_publicacao():
    dt1 = parse_data_publicacao("23 de setembro de 2026")
    assert dt1.year == 2026
    assert dt1.month == 9
    assert dt1.day == 23

    dt2 = parse_data_publicacao("15/03/2025")
    assert dt2.year == 2025
    assert dt2.month == 3
    assert dt2.day == 15

    dt3 = parse_data_publicacao("")
    assert dt3.year == 2026


def test_upsert_edital_insert_new(db_session):
    edital_data = {
        "titulo": "Edital Monitoria DEG 01/2026",
        "link": "https://deg.unb.br/editais/monitoria-2026",
        "data_publicacao": "23 de setembro de 2026",
    }
    docs_data = [
        {
            "titulo": "Edital Completo",
            "link": "https://deg.unb.br/docs/edital-01.pdf",
            "tipo": "original",
        }
    ]

    edital = upsert_edital(db=db_session, edital_data=edital_data, documentos_data=docs_data)

    assert edital.id is not None
    assert edital.titulo == "Edital Monitoria DEG 01/2026"
    assert edital.status == StatusEdital.ABERTO
    assert len(edital.documentos) == 1
    assert edital.documentos[0].tipo_documento == TipoDocumento.ORIGINAL


def test_upsert_edital_update_and_idempotence(db_session):
    edital_data = {
        "titulo": "Edital Monitoria DEG 01/2026",
        "link": "https://deg.unb.br/editais/monitoria-2026",
        "data_publicacao": "23 de setembro de 2026",
    }
    docs_data_1 = [
        {
            "titulo": "Edital Completo",
            "link": "https://deg.unb.br/docs/edital-01.pdf",
            "tipo": "original",
        }
    ]

    # Primeira execução: insere
    upsert_edital(db=db_session, edital_data=edital_data, documentos_data=docs_data_1)
    assert db_session.query(Edital).count() == 1
    assert db_session.query(EditalDocumento).count() == 1

    # Segunda execução idêntica: não duplica
    upsert_edital(db=db_session, edital_data=edital_data, documentos_data=docs_data_1)
    assert db_session.query(Edital).count() == 1
    assert db_session.query(EditalDocumento).count() == 1

    # Terceira execução com novo documento (resultado_final): adiciona doc e muda status para ENCERRADO
    docs_data_2 = docs_data_1 + [
        {
            "titulo": "Resultado Final Monitoria",
            "link": "https://deg.unb.br/docs/resultado_final.pdf",
            "tipo": "resultado_final",
        }
    ]
    edital_atualizado = upsert_edital(
        db=db_session,
        edital_data=edital_data,
        documentos_data=docs_data_2,
    )

    assert db_session.query(Edital).count() == 1
    assert db_session.query(EditalDocumento).count() == 2
    assert edital_atualizado.status == StatusEdital.ENCERRADO


def test_run_pipeline_persists_scraped_data(db_session, monkeypatch):
    from app.modules.scraper import deg

    # Mock das funções do scraper
    fake_editais = [
        {
            "titulo": "Edital DEG 01/2026",
            "link": "https://deg.unb.br/editais/01-2026",
            "data_publicacao": "10 de fevereiro de 2026",
        },
        {
            "titulo": "Edital DEG 02/2026",
            "link": "https://deg.unb.br/editais/02-2026",
            "data_publicacao": "15 de março de 2026",
        },
    ]

    def fake_fetch_editais(year=None):
        return fake_editais

    def fake_fetch_documentos(url):
        if "01-2026" in url:
            return [
                {"titulo": "Edital", "link": f"{url}/doc.pdf", "tipo": "original"},
                {"titulo": "Resultado", "link": f"{url}/resultado.pdf", "tipo": "resultado_final"},
            ]
        return [{"titulo": "Edital", "link": f"{url}/doc.pdf", "tipo": "original"}]

    monkeypatch.setattr(deg, "fetch_editais", fake_fetch_editais)
    monkeypatch.setattr(deg, "fetch_documentos", fake_fetch_documentos)

    salvos = run_pipeline(db=db_session, year=2026)

    assert len(salvos) == 2
    assert db_session.query(Edital).count() == 2

    e1 = db_session.query(Edital).filter_by(url_pagina="https://deg.unb.br/editais/01-2026").first()
    assert e1.status == StatusEdital.ENCERRADO
    assert len(e1.documentos) == 2

    e2 = db_session.query(Edital).filter_by(url_pagina="https://deg.unb.br/editais/02-2026").first()
    assert e2.status == StatusEdital.ABERTO
    assert len(e2.documentos) == 1

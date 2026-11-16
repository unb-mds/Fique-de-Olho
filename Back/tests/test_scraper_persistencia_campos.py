"""Testes da persistência dos campos novos do scraper (area, link_inscricao, numero, metadados),
dos títulos de documentos, dos contadores de coletas e dos filtros por campus/área da API."""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, Coleta, Edital, EditalDocumento, StatusEdital, get_db
from app.main import app
from app.modules.scraper import SCRAPERS_REGISTRY
from app.modules.scraper import service as scraper_service
from app.modules.scraper.pipeline import (
    _extrair_metadados,
    inferir_area,
    upsert_edital,
)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()


def _edital_cead(**extra):
    base = {
        "titulo": "Seleções CEAD 2026 - PGD - Termo Aditivo 06",
        "link": "https://cead.unb.br/editais/pgd-aditivo-06/",
        "data_publicacao": "2026-10-08",
        "descricao": "Processo seletivo para PGD.",
        "numero": "006/2026/CEAD",
        "publico_alvo": "Servidor",
        "curso": "Pedagogia",
        "item_id": 33035,
        "ano": 2026,
        "link_inscricao": "https://cead.unb.br/inscricao/pgd-06",
        "identificador_origem": "cead-33035",
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------- campos novos no upsert

def test_upsert_grava_colunas_e_metadados(db):
    edital = upsert_edital(db, _edital_cead(), enable_pdf_enrichment=False)

    assert edital.numero == "006/2026/CEAD"
    assert edital.link_inscricao == "https://cead.unb.br/inscricao/pgd-06"
    assert edital.identificador_origem == "cead-33035"
    # O que não tem coluna própria vai para o JSON
    assert edital.metadados["publico_alvo"] == "Servidor"
    assert edital.metadados["curso"] == "Pedagogia"
    assert edital.metadados["item_id"] == 33035
    # O que já tem coluna não é duplicado dentro do JSON
    for chave in ("titulo", "link", "numero", "link_inscricao", "descricao", "identificador_origem"):
        assert chave not in edital.metadados


def test_metadados_ignora_textos_grandes_e_estruturas_internas():
    extras = _extrair_metadados(
        {
            "titulo": "x",
            "texto_completo": "t" * 10_000,
            "documentos": [{"link": "a"}],
            "nota_longa": "n" * 501,
            "estrutura": {"a": 1},
            "lista_de_dicts": [{"a": 1}],
            "vazio": "",
            "nulo": None,
            "programa": "PIBIC",
            "fluxo_continuo": True,
            "locais": ["Asa Norte", "Gama"],
        }
    )
    assert extras == {"programa": "PIBIC", "fluxo_continuo": True, "locais": ["Asa Norte", "Gama"]}


def test_reprocessar_mescla_metadados_sem_perder_chaves_antigas(db):
    upsert_edital(db, _edital_cead(), enable_pdf_enrichment=False)
    edital = upsert_edital(
        db, _edital_cead(modalidade="EAD", curso="Letras"), enable_pdf_enrichment=False
    )

    assert edital.metadados["modalidade"] == "EAD"  # chave nova
    assert edital.metadados["curso"] == "Letras"  # valor atualizado
    assert edital.metadados["publico_alvo"] == "Servidor"  # chave antiga preservada
    assert db.query(Edital).count() == 1


def test_alteracao_no_dict_de_metadados_e_detectada_pelo_sqlalchemy(db):
    edital = upsert_edital(db, _edital_cead(), enable_pdf_enrichment=False)
    edital.metadados["revisado"] = True  # MutableDict: sem reatribuir
    db.commit()
    db.expire_all()
    assert db.get(Edital, edital.id).metadados["revisado"] is True


# ---------------------------------------------------------------- área

def test_area_informada_pelo_scraper_tem_prioridade(db):
    edital = upsert_edital(
        db,
        _edital_cead(titulo="Edital de Monitoria 01/2026", area="Zootecnia"),
        enable_pdf_enrichment=False,
    )
    assert edital.area == "Zootecnia"


@pytest.mark.parametrize(
    "titulo, esperado",
    [
        ("Edital de Monitoria DEG 01/2026", "Ensino"),
        ("Edital PIBIC/PIBITI 2026/2027", "Pesquisa"),
        ("Edital DAC Nº 24/2026 – Auxílio Alimentação", "Assistência Estudantil"),
        ("Edital PIBEX 2026 - Ações Comunitárias", "Extensão"),
        ("Edital INT Nº 9/2026 - Intercâmbio Europa", "Internacional"),
        ("Concurso Público para Docente", "Gestão de Pessoas"),
        ("Edital sem pista nenhuma", None),
    ],
)
def test_inferir_area_por_palavras_chave(titulo, esperado):
    assert inferir_area(titulo) == esperado


def test_area_fica_vazia_quando_nao_ha_pista(db):
    edital = upsert_edital(
        db, _edital_cead(titulo="Comunicado geral 12/2026"), enable_pdf_enrichment=False
    )
    assert edital.area is None


# ---------------------------------------------------------------- documentos

def test_documento_guarda_titulo_e_nao_duplica_no_reprocessamento(db):
    docs = [
        {"titulo": "Edital de Abertura nº 006/2026", "link": "https://cead.unb.br/a.pdf", "tipo": "original"},
        {"titulo": "Resultado Final Homologado", "link": "https://cead.unb.br/r.pdf", "tipo": "resultado_final"},
    ]
    upsert_edital(db, _edital_cead(), documentos_data=docs, enable_pdf_enrichment=False)
    upsert_edital(db, _edital_cead(), documentos_data=docs, enable_pdf_enrichment=False)

    gravados = db.query(EditalDocumento).order_by(EditalDocumento.id).all()
    assert [d.titulo for d in gravados] == ["Edital de Abertura nº 006/2026", "Resultado Final Homologado"]


def test_banco_recusa_documento_duplicado_para_o_mesmo_edital(db):
    edital = upsert_edital(db, _edital_cead(), enable_pdf_enrichment=False)
    from app.core.database import TipoDocumento

    for _ in range(2):
        db.add(
            EditalDocumento(
                edital_id=edital.id, url_pdf="https://x/a.pdf", tipo_documento=TipoDocumento.ORIGINAL
            )
        )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ---------------------------------------------------------------- coletas

def test_coleta_registra_novos_e_atualizados(db, monkeypatch):
    monkeypatch.setattr(scraper_service, "processar_notificacoes_se_configuradas", lambda d: None)

    def _fake(titulos):
        fake = MagicMock()
        fake.fetch_editais.return_value = [
            {"titulo": t, "link": f"https://deg.unb.br/{i}", "data_publicacao": "2026-10-01"}
            for i, t in enumerate(titulos)
        ]
        return fake

    monkeypatch.setitem(SCRAPERS_REGISTRY, "DEG", _fake(["Edital A", "Edital B"]))
    scraper_service.sync_portal_editais(db, "DEG")

    # 2ª coleta: A mudou de título (atualizado) e B continua igual
    monkeypatch.setitem(SCRAPERS_REGISTRY, "DEG", _fake(["Edital A (retificado)", "Edital B"]))
    scraper_service.sync_portal_editais(db, "DEG")

    primeira, segunda = db.query(Coleta).order_by(Coleta.id).all()
    assert (primeira.editais_encontrados, primeira.novos_editais, primeira.editais_atualizados) == (2, 2, 0)
    assert segunda.status == "concluida"
    assert segunda.novos_editais == 0
    assert segunda.editais_atualizados == 1


# ---------------------------------------------------------------- API: filtros e facetas

@pytest.fixture
def client_api():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    hoje = date.today()
    with Session() as s:
        s.add_all(
            [
                Edital(titulo="Monitoria FGA", url_pagina="https://x/1", campus="FGA", area="Ensino",
                       fim_inscricao=hoje + timedelta(days=5), data_publicacao=datetime(2026, 1, 1),
                       status=StatusEdital.ABERTO, link_inscricao="https://x/insc", numero="01/2026",
                       metadados={"curso": "Engenharia"}),
                Edital(titulo="Monitoria Darcy", url_pagina="https://x/2", campus="Darcy Ribeiro", area="Ensino",
                       fim_inscricao=hoje + timedelta(days=5), data_publicacao=datetime(2026, 1, 2),
                       status=StatusEdital.ABERTO),
                Edital(titulo="PIBIC FGA", url_pagina="https://x/3", campus="FGA", area="Pesquisa",
                       fim_inscricao=hoje - timedelta(days=5), data_publicacao=datetime(2026, 1, 3),
                       status=StatusEdital.ENCERRADO),
                Edital(titulo="Sem área", url_pagina="https://x/4", campus="FUP", area=None,
                       data_publicacao=datetime(2026, 1, 4), status=StatusEdital.ABERTO),
            ]
        )
        s.commit()

    def _override():
        sess = Session()
        try:
            yield sess
        finally:
            sess.close()

    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _titulos(resp):
    assert resp.status_code == 200
    return sorted(e["titulo"] for e in resp.json())


def test_api_filtra_por_area_sem_diferenciar_maiusculas(client_api):
    assert _titulos(client_api.get("/editais/", params={"area": "ensino"})) == ["Monitoria Darcy", "Monitoria FGA"]
    assert _titulos(client_api.get("/editais/", params={"area": "Pesquisa"})) == ["PIBIC FGA"]


def test_api_area_usa_igualdade_exata_e_nao_busca_parcial(client_api):
    assert client_api.get("/editais/", params={"area": "Ens"}).json() == []


def test_api_combina_campus_e_area(client_api):
    assert _titulos(client_api.get("/editais/", params={"campus": "FGA", "area": "Ensino"})) == ["Monitoria FGA"]
    assert client_api.get("/editais/", params={"campus": "FUP", "area": "Ensino"}).json() == []


def test_api_serializa_campos_novos(client_api):
    itens = client_api.get("/editais/", params={"campus": "FGA", "area": "Ensino"}).json()
    assert itens[0]["area"] == "Ensino"
    assert itens[0]["link_inscricao"] == "https://x/insc"
    assert itens[0]["numero"] == "01/2026"
    assert "metadados" not in itens[0]  # só no detalhe

    detalhe = client_api.get(f"/editais/{itens[0]['id']}").json()
    assert detalhe["metadados"] == {"curso": "Engenharia"}


def test_api_filtros_lista_campi_e_areas_com_contagem(client_api):
    corpo = client_api.get("/editais/filtros").json()
    assert {"nome": "FGA", "total": 2} in corpo["campi"]
    assert {"nome": "Ensino", "total": 2} in corpo["areas"]
    assert {"nome": "Pesquisa", "total": 1} in corpo["areas"]
    assert all(a["nome"] for a in corpo["areas"])  # sem área vazia


def test_api_filtros_pode_contar_apenas_abertos(client_api):
    corpo = client_api.get("/editais/filtros", params={"status": "aberto"}).json()
    assert {"nome": "Ensino", "total": 2} in corpo["areas"]
    assert all(a["nome"] != "Pesquisa" for a in corpo["areas"])  # PIBIC está encerrado


# ---------------------------------------------------------------- backfill da área

def test_backfill_area_dry_run_nao_grava_e_apply_nao_sobrescreve(db):
    from app.modules.scraper.backfill_area import backfill_area

    db.add_all(
        [
            Edital(titulo="Edital de Monitoria 01/2026", url_pagina="https://b/1"),
            Edital(titulo="Edital PIBIC 2026", url_pagina="https://b/2", area="Zootecnia"),
            Edital(titulo="Comunicado geral", url_pagina="https://b/3"),
        ]
    )
    db.commit()

    contagem = backfill_area(db, apply=False)
    assert contagem == {"Ensino": 1, None: 1}  # o edital que já tinha área nem entra
    assert db.query(Edital).filter(Edital.area.isnot(None)).count() == 1  # dry-run não gravou

    backfill_area(db, apply=True)
    por_url = {e.url_pagina: e.area for e in db.query(Edital).all()}
    assert por_url == {"https://b/1": "Ensino", "https://b/2": "Zootecnia", "https://b/3": None}

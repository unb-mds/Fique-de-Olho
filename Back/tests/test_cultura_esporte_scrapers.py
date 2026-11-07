"""Testes unitários e de integração para os scrapers de Cultura, Comunicação, Editorial e Esportes:
CEL (Coordenação de Esporte e Lazer), CAL (Casa da Cultura da América Latina / IdA),
EDU (Editora UnB) e UNBTV (Canal Universitário da UnB).
"""

from unittest.mock import MagicMock, patch
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, Edital, StatusEdital, TipoDocumento
from app.modules.scraper.base import BaseScraper
from app.modules.scraper.cel import (
    CELScraper,
    cel_scraper,
    classify_cel_document,
    parse_cel_editais_html,
    parse_deac_editais_html,
)
from app.modules.scraper.cal import (
    CALScraper,
    cal_scraper,
    classify_cal_document,
    parse_ddc_cuc_page,
    parse_ddc_editais_listing,
    parse_ida_article_page,
)
from app.modules.scraper.edu import (
    EDUScraper,
    edu_scraper,
    classify_edu_document,
    parse_edu_editais_page,
    parse_edu_wp_post,
)
from app.modules.scraper.unbtv import (
    UnBTVScraper,
    unbtv_scraper,
    classify_unbtv_document,
    parse_unbtv_editais_page,
    parse_unbtv_wp_post,
)
from app.modules.scraper.service import sync_portal_editais, sync_all_portais, inferir_categoria
from app.modules.scraper.pipeline import upsert_edital


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


# ============================================================================
# 1. CEL (Coordenação de Esporte e Lazer)
# ============================================================================

def test_cel_scraper_contract():
    assert issubclass(CELScraper, BaseScraper)
    assert cel_scraper.orgao_origem == "CEL"


def test_classify_cel_document():
    assert classify_cel_document("Resultado Final Edital AVI", "url.pdf") == "resultado_final"
    assert classify_cel_document("Resultado Provisório Edital 08", "url.pdf") == "resultado_provisorio"
    assert classify_cel_document("Retificação de Cronograma", "url.pdf") == "retificacao"
    assert classify_cel_document("Edital de Abertura", "url.pdf") == "original"


def test_parse_cel_editais_html_grouping():
    sample_html = """
    <div class="elementor-tab-title" id="elementor-tab-title-1642">2025</div>
    <div class="elementor-tab-content" id="elementor-tab-content-1642">
        <ul>
            <li><a href="https://esporte.unb.br/wp-content/uploads/2025/05/Edital_08.pdf">Edital nº 08/2025/DAC – Processo Seletivo para concessão de Auxílio Viagem Individual (AVI)</a></li>
            <li><a href="https://esporte.unb.br/wp-content/uploads/2025/05/Resultado-Provisorio.pdf">Resultado Provisório – Processo Seletivo para concessão de Auxílio Viagem Individual (AVI)</a></li>
            <li><a href="https://esporte.unb.br/wp-content/uploads/2025/05/Resultado-Final.pdf">Resultado Final – Processo Seletivo para concessão de Auxílio Viagem Individual (AVI)</a></li>
            <li><a href="https://docs.google.com/forms/d/e/sample/viewform">Inscrições para concorrer a bolsas</a></li>
            <li><a href="https://esporte.unb.br/wp-content/uploads/2025/07/Edital-APRAFE.pdf">Edital DAC nº 12/2025 – APRAFE Cultura +</a></li>
        </ul>
    </div>
    """
    editais = parse_cel_editais_html(sample_html, reference_year=2025)
    assert len(editais) >= 2

    avi = next(e for e in editais if "08/2025" in e["titulo"])
    assert avi["ano"] == 2025
    assert avi["status"] == "fechado"  # Pois possui Resultado Final
    assert avi["unidade"] == "CEL"
    assert avi["campus"] == "Darcy Ribeiro"
    assert len(avi["documentos"]) == 3
    assert any(d["tipo"] == "resultado_final" for d in avi["documentos"])


def test_parse_deac_editais_html():
    sample_html = """
    <div class="entry-content is-layout-flow"></div>
    <div class="entry-content is-layout-constrained">
        <div class="elementor-tab-title" data-tab="1" id="elementor-tab-title-1211">2026</div>
        <div class="elementor-tab-content" data-tab="1" id="elementor-tab-content-1211">
            <p><b>Chamada Pública Nº 03/2026</b></p>
            <ul>
                <li><a href="https://deac.unb.br/wp-content/uploads/2026/04/CHAMADA-PUBLICA-no-3-DEAC_DAC.pdf">Chamada Pública – para a seleção de bolsistas para Projetos de Extensão de Representação e Esportes Eletrônicos</a></li>
                <li><a href="https://deac.unb.br/wp-content/uploads/2026/04/Resultado-Provisorio.pdf">Resultado Provisório – seleção de bolsistas</a></li>
                <li><a href="https://deac.unb.br/wp-content/uploads/2026/04/Resultado-Final.pdf">Resultado Final – seleção de bolsistas</a></li>
            </ul>
            <p><b>CHAMADA PÚBLICA nº 2 DEAC/DAC</b></p>
            <ul>
                <li><a href="https://deac.unb.br/wp-content/uploads/2026/11/CHAMADA-PUBLICA-no-2.pdf">Edital</a></li>
                <li><a href="https://deac.unb.br/wp-content/uploads/2026/11/Resultado-Provisorio-2.pdf">Resultado Provisório</a></li>
            </ul>
        </div>
    </div>
    """
    editais = parse_deac_editais_html(sample_html, reference_year=2026)
    assert len(editais) == 2
    ed1 = editais[0]
    assert ed1["ano"] == 2026
    assert ed1["status"] == "fechado"
    assert len(ed1["documentos"]) == 3
    ed2 = editais[1]
    assert "CHAMADA PÚBLICA nº 2 DEAC/DAC" in ed2["titulo"]
    assert ed2["status"] == "aberto"
    assert len(ed2["documentos"]) == 2


@patch("app.modules.scraper.cel.httpx.Client.get")
def test_cel_scraper_fetch_editais_success(mock_get):
    resp_cel = MagicMock()
    resp_cel.status_code = 200
    resp_cel.url = "https://esporte.unb.br/editais/"
    resp_cel.text = """
    <div class="elementor-tab-content" id="elementor-tab-content-1641">
        <p><a href="https://esporte.unb.br/wp-content/uploads/2026/01/Edital-Bolsa-Atleta-2026.pdf">Edital Bolsa Atleta Universitária 2026</a></p>
    </div>
    """

    resp_deac = MagicMock()
    resp_deac.status_code = 200
    resp_deac.url = "https://deac.unb.br/editais-dac/"
    resp_deac.text = """
    <div><a href="https://deac.unb.br/wp-content/uploads/2026/05/Edital_19.pdf">Edital DAC Nº 19/2026 – AVI Internacional FISU Cheerleading</a></div>
    """

    mock_get.side_effect = [resp_cel, resp_deac]
    items = cel_scraper.fetch_editais()
    assert len(items) == 2
    assert any("Bolsa Atleta" in it["titulo"] for it in items)
    assert any("Edital DAC" in it["titulo"] for it in items)


@patch("app.modules.scraper.cel.httpx.Client.get")
def test_cel_scraper_network_failure(mock_get):
    mock_get.side_effect = httpx.ConnectError("Falha de rede CEL")
    assert cel_scraper.fetch_editais() == []
    assert cel_scraper.fetch_documentos("https://esporte.unb.br/editais/fake") == []


# ============================================================================
# 2. CAL / IdA (Casa da Cultura da América Latina / Instituto de Artes)
# ============================================================================

def test_cal_scraper_contract():
    assert issubclass(CALScraper, BaseScraper)
    assert cal_scraper.orgao_origem == "CAL"


def test_classify_cal_document():
    assert classify_cal_document("Resultado Definitivo", "doc.pdf") == "resultado_final"
    assert classify_cal_document("Resultado Provisório RP", "doc.pdf") == "resultado_provisorio"
    assert classify_cal_document("Retificação Edital", "doc.pdf") == "retificacao"
    assert classify_cal_document("Edital Rede CUC 2026", "doc.pdf") == "original"


def test_parse_ddc_cuc_page():
    sample_html = """
    <h1>Edital Rede CUC 2026</h1>
    <div>
        <a href="https://ddc.unb.br/wp-content/uploads/2026/06/EditalRedeCUC2026.pdf">Edital Rede CUC 2026 (PDF)</a>
        <a href="https://ddc.unb.br/wp-content/uploads/2026/06/EditalRedeCUC2026_Anexo2.docx">Formulário de Recurso (docx)</a>
        <a href="https://ddc.unb.br/wp-content/uploads/2026/07/EditalRedeCUC2026_RP.pdf">Resultado Provisório (PDF)</a>
        <a href="https://ddc.unb.br/wp-content/uploads/2026/07/SEI_14524717_Despacho.pdf">Resultado Definitivo (PDF)</a>
    </div>
    """
    item = parse_ddc_cuc_page(sample_html, "https://ddc.unb.br/editalredecuc/", "Edital CUC", reference_year=2026)
    assert item["titulo"] == "Edital Rede CUC 2026"
    assert item["ano"] == 2026
    assert item["unidade"] == "CAL"
    assert item["status"] == "fechado"
    assert len(item["documentos"]) == 4
    assert any(d["tipo"] == "resultado_final" for d in item["documentos"])


def test_parse_ida_article_page():
    sample_html = """
    <h2>Edital para assistente de produção cultural | FUNAPE</h2>
    <div class="item-page">
        <p>Inscrições abertas no site da FUNAPE.</p>
        <a href="https://funape.org.br/novo/transparencia/processo_seletivo.php">Formulário de Inscrição FUNAPE</a>
        <a href="https://ida.unb.br/images/Site/Editais/SEI_10768425_Edital_1_2024.pdf">Acesse Aqui o Edital</a>
        <a href="https://ida.unb.br/images/Site/Editais/SEI_10802190_Despacho.pdf">Resultado Final do Edital</a>
    </div>
    """
    item = parse_ida_article_page(sample_html, "https://ida.unb.br/edita/ida/220", "Edital IdA", reference_year=2026)
    assert item["titulo"] == "Edital para assistente de produção cultural | FUNAPE"
    assert item["link_inscricao"] == "https://funape.org.br/novo/transparencia/processo_seletivo.php"
    assert item["status"] == "fechado"
    assert len(item["documentos"]) == 2


@patch("app.modules.scraper.cal.httpx.Client.get")
def test_cal_scraper_resilient_to_cal_500_server_error(mock_get):
    # Simula cal.unb.br retornando HTTP 500
    resp_500 = MagicMock()
    resp_500.status_code = 500

    resp_cuc = MagicMock()
    resp_cuc.status_code = 200
    resp_cuc.url = "https://ddc.unb.br/editalredecuc/"
    resp_cuc.text = "<h1>Edital Rede CUC 2026</h1><a href='https://ddc.unb.br/doc.pdf'>Edital</a>"

    resp_ddc = MagicMock()
    resp_ddc.status_code = 404

    resp_ida = MagicMock()
    resp_ida.status_code = 404

    mock_get.side_effect = [resp_500, resp_cuc, resp_ddc, resp_ida]
    items = cal_scraper.fetch_editais()
    # Deve continuar normalmente sem quebrar e coletar CUC
    assert len(items) >= 1
    assert "Rede CUC 2026" in items[0]["titulo"]


# ============================================================================
# 3. EDU (Editora da Universidade de Brasília)
# ============================================================================

def test_edu_scraper_contract():
    assert issubclass(EDUScraper, BaseScraper)
    assert edu_scraper.orgao_origem == "EDU"


def test_classify_edu_document():
    assert classify_edu_document("Resultado final dos aprovados", "doc.pdf") == "resultado_final"
    assert classify_edu_document("Resultado provisório de recurso", "doc.pdf") == "resultado_provisorio"
    assert classify_edu_document("Termo de Retificação", "doc.pdf") == "retificacao"
    assert classify_edu_document("Edital de Publicação de Livros", "doc.pdf") == "original"
    assert classify_edu_document("Minuta de Contrato", "doc.pdf") == "original"


def test_parse_edu_editais_page():
    sample_html = """
    <div class="elementor-26162">
        <section>EDITAIS ABERTOS</section>
        <section><h2>Edital EDU N.º 01/2026 - Seleção para publicação de livros</h2></section>
        <section>
            <h3>Edital EDU N.º 01/2026</h3>
            <a href="https://editora.unb.br/wp-content/uploads/2026/10/edital-edu-01-2026.pdf">Download</a>
        </section>
        <section>EDITAIS ENCERRADOS</section>
        <section><h2>Edital Nº1/2026/EDU - Processo seletivo para contratação de estagiários</h2></section>
        <section>
            <h3>EDITAL Nº 01/2026/EDU</h3>
            <a href="https://estagio.unb.br/edital-estagio">Acesse</a>
        </section>
    </div>
    """
    editais = parse_edu_editais_page(sample_html, reference_year=2026)
    assert len(editais) == 2

    ed_aberto = editais[0]
    assert "01/2026" in ed_aberto["titulo"]
    assert ed_aberto["status"] == "aberto"
    assert ed_aberto["tipo"] == "Pesquisa"
    assert len(ed_aberto["documentos"]) == 1

    ed_fechado = editais[1]
    assert "estagiários" in ed_fechado["titulo"].lower()
    assert ed_fechado["status"] == "fechado"
    assert ed_fechado["tipo"] == "Estágio"


def test_parse_edu_wp_post():
    post = {
        "id": 1234,
        "date": "2026-06-24T17:33:47",
        "link": "https://editora.unb.br/editora-unb-abre-vagas-para-bolsistas/",
        "title": {"rendered": "Editora UnB abre vagas para bolsistas em projeto de digitalização"},
        "content": {
            "rendered": '<p>Acesse o edital <a href="https://editora.unb.br/edital-bolsa.pdf">Edital Bolsa</a></p>'
        },
    }
    item = parse_edu_wp_post(post, reference_year=2026)
    assert item is not None
    assert "bolsistas" in item["titulo"].lower()
    assert item["tipo"] == "Bolsas / Auxílios"
    assert item["ano"] == 2026
    assert len(item["documentos"]) == 1


# ============================================================================
# 4. UNBTV (Canal Universitário da UnB)
# ============================================================================

def test_unbtv_scraper_contract():
    assert issubclass(UnBTVScraper, BaseScraper)
    assert unbtv_scraper.orgao_origem == "UNBTV"


def test_classify_unbtv_document():
    assert classify_unbtv_document("Edital de Resultado Final", "doc.pdf") == "resultado_final"
    assert classify_unbtv_document("Resultado Preliminar de Análise", "doc.pdf") == "resultado_provisorio"
    assert classify_unbtv_document("Retificação de Edital", "doc.pdf") == "retificacao"
    assert classify_unbtv_document("Edital de Abertura Nº 1/2026", "doc.pdf") == "original"


def test_parse_unbtv_editais_page():
    sample_html = """
    <div class="elementor-column">
        <div class="elementor-widget-wrap">
            <div class="elementor-widget"><h4>PGD UnBTV 2026</h4></div>
            <div class="elementor-widget">
                <a href="https://unbtv.unb.br/wp-content/uploads/Edital-PGD-UnBTV_02_2026.pdf">EDITAL UNBTV Nº 02/2026 - PGD</a>
            </div>
            <div class="elementor-widget">
                <a href="https://unbtv.unb.br/wp-content/uploads/Resultado-Final-Edital-PGD.pdf">RESULTADO FINAL</a>
            </div>
            <div class="elementor-widget"><h4>Estágio 2026</h4></div>
            <div class="elementor-widget">
                <a href="https://unbtv.unb.br/wp-content/uploads/Edital_Abertura_Estagio.pdf">EDITAL DE ABERTURA Nº 1 /2026 – ESTÁGIO</a>
            </div>
        </div>
    </div>
    """
    editais = parse_unbtv_editais_page(sample_html, reference_year=2026)
    assert len(editais) == 2

    pgd = next(e for e in editais if "PGD" in e["titulo"])
    assert pgd["status"] == "fechado"
    assert len(pgd["documentos"]) == 2
    assert any(d["tipo"] == "resultado_final" for d in pgd["documentos"])

    estagio = next(e for e in editais if "ESTÁGIO" in e["titulo"])
    assert estagio["status"] == "aberto"
    assert estagio["tipo"] == "Estágio"
    assert len(estagio["documentos"]) == 1


def test_parse_unbtv_wp_post():
    post = {
        "id": 10871,
        "date": "2025-02-06T10:00:00",
        "link": "https://unbtv.unb.br/2025/02/06/trabalhe-na-unbtv/",
        "title": {"rendered": "Trabalhe na UnBTV"},
        "content": {
            "rendered": '<p>Seleção de estagiários. Formulário em <a href="https://docs.google.com/forms/sample">Inscreva-se</a></p>'
        },
    }
    item = parse_unbtv_wp_post(post, reference_year=2026)
    assert item is not None
    assert item["titulo"] == "Trabalhe na UnBTV"
    assert item["tipo"] == "Estágio"
    assert item["link_inscricao"] == "https://docs.google.com/forms/sample"


# ============================================================================
# 5. Integração com Banco de Dados e Pipeline Periódico
# ============================================================================

def test_sync_portal_editais_cel(test_db):
    sample_items = [
        {
            "titulo": "Edital Bolsa Atleta Universitária 2026",
            "link": "https://esporte.unb.br/editais/bolsa-atleta-2026.pdf",
            "tipo": "Bolsas / Auxílios",
            "tipo_edital": "Bolsa Atleta",
            "programa": "CEL/UnB",
            "campus": "Darcy Ribeiro",
            "data_publicacao": "2026-02-15",
            "status": "aberto",
            "ano": 2026,
            "documentos": [
                {"titulo": "Edital Oficial", "link": "https://esporte.unb.br/editais/bolsa-atleta-2026.pdf", "tipo": "original"}
            ],
        }
    ]
    with patch.object(cel_scraper, "fetch_editais", return_value=sample_items):
        res = sync_portal_editais(test_db, "CEL")
        assert res["status"] == "success"
        assert res["editais_encontrados"] == 1
        assert res["novos_editais"] == 1

        ed = test_db.query(Edital).filter(Edital.url_pagina == "https://esporte.unb.br/editais/bolsa-atleta-2026.pdf").first()
        assert ed is not None
        assert ed.tipo == "Bolsas / Auxílios"
        assert ed.status == StatusEdital.ABERTO
        assert len(ed.documentos) == 1


def test_automatic_status_transition_on_resultado_final(test_db):
    # Publica edital aberto
    edital_data = {
        "titulo": "Edital Ocupação de Galerias CAL 2026",
        "link": "https://ddc.unb.br/edital-cal-2026",
        "tipo": "Extensões",
        "campus": "Darcy Ribeiro",
        "data_publicacao": "2026-03-01",
        "status": "aberto",
        "ano": 2026,
        "documentos": [
            {"titulo": "Edital Abertura", "link": "https://ddc.unb.br/edital.pdf", "tipo": "original"}
        ],
    }
    ed = upsert_edital(test_db, edital_data)
    assert ed.status == StatusEdital.ABERTO

    # Chegada de resultado final altera status para ENCERRADO automaticamente
    edital_data_atualizada = {
        **edital_data,
        "documentos": [
            {"titulo": "Edital Abertura", "link": "https://ddc.unb.br/edital.pdf", "tipo": "original"},
            {"titulo": "Resultado Final e Homologação", "link": "https://ddc.unb.br/resultado-final.pdf", "tipo": "resultado_final"},
        ],
    }
    ed_atualizado = upsert_edital(test_db, edital_data_atualizada)
    assert ed_atualizado.status == StatusEdital.ENCERRADO
    assert len(ed_atualizado.documentos) == 2


def test_sync_all_portais_cultura_esporte(test_db):
    with patch.object(cel_scraper, "fetch_editais", return_value=[]), \
         patch.object(cal_scraper, "fetch_editais", return_value=[]), \
         patch.object(edu_scraper, "fetch_editais", return_value=[]), \
         patch.object(unbtv_scraper, "fetch_editais", return_value=[]):
        res = sync_all_portais(test_db, orgaos=["CEL", "CAL", "EDU", "UNBTV"])
        assert res["status"] == "success"
        assert res["portais_processados"] == 4
        assert "CEL" in res["portais"]
        assert "CAL" in res["portais"]
        assert "EDU" in res["portais"]
        assert "UNBTV" in res["portais"]


def test_inferir_categoria_cultura_esporte():
    assert inferir_categoria("Edital Bolsa Atleta Universitária") == "Bolsas / Auxílios"
    assert inferir_categoria("Chamada Pública para Ocupação de Galeria de Arte") == "Extensões"
    assert inferir_categoria("Edital de Publicação de Livros e Coletâneas") == "Pesquisa"
    assert inferir_categoria("Seleção de Estagiários para UnBTV") == "Estágio"


# ============================================================================
# 6. Testes Live (@pytest.mark.live)
# ============================================================================

@pytest.mark.live
def test_live_cel_scraper():
    items = cel_scraper.fetch_editais()
    assert len(items) > 0
    assert any(it["ano"] >= 2024 for it in items)
    for it in items[:5]:
        assert it["titulo"]
        assert it["link"]
        assert it["unidade"] == "CEL"


@pytest.mark.live
def test_live_cal_scraper():
    items = cal_scraper.fetch_editais()
    assert len(items) > 0
    for it in items:
        assert it["titulo"]
        assert it["link"]
        assert it["unidade"] == "CAL"


@pytest.mark.live
def test_live_edu_scraper():
    items = edu_scraper.fetch_editais()
    assert len(items) > 0
    for it in items:
        assert it["titulo"]
        assert it["link"]
        assert it["unidade"] == "EDU"


@pytest.mark.live
def test_live_unbtv_scraper():
    items = unbtv_scraper.fetch_editais()
    assert len(items) > 0
    for it in items:
        assert it["titulo"]
        assert it["link"]
        assert it["unidade"] == "UNBTV"

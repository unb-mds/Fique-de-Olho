"""Testes unitários automatizados para os scrapers dos 8 novos portais institucionais da UnB."""

from unittest.mock import MagicMock, patch
import pytest

from app.modules.scraper.base import BaseScraper
from app.modules.scraper import (
    BCEScraper,
    DACScraper,
    DACESScraper,
    DEGScraper,
    DEXScraper,
    DPGScraper,
    DPIScraper,
    INTScraper,
    PROICScraper,
    SCRAPERS_REGISTRY,
    bce_scraper,
    dac_scraper,
    daces_scraper,
    deg_scraper,
    dex_scraper,
    dpg_scraper,
    dpi_scraper,
    get_scraper,
    int_scraper,
    proic_scraper,
)


def test_scrapers_registry_contains_all_nine_organs():
    """Garante que todos os 9 órgãos (DEG + 8 novos) estão devidamente registrados."""
    expected_organs = {"DEG", "DPG", "INT", "DEX", "DPI", "DAC", "PROIC", "DACES", "BCE", "CEAD"}
    assert set(SCRAPERS_REGISTRY.keys()) == expected_organs

    for sigla in expected_organs:
        scraper = get_scraper(sigla)
        assert scraper is not None
        assert isinstance(scraper, BaseScraper)
        assert scraper.orgao_origem == sigla

    # Teste case-insensitive do helper
    assert get_scraper("dpg") == dpg_scraper
    assert get_scraper(" dex ") == dex_scraper
    assert get_scraper("INEXISTENTE") is None


# ============================================================================
# 1. DPG (Decanato de Pós-Graduação)
# ============================================================================

def test_dpg_scraper_contract():
    assert issubclass(DPGScraper, BaseScraper)
    assert dpg_scraper.orgao_origem == "DPG"


@patch("app.modules.scraper.dpg.httpx.get")
def test_dpg_scraper_fetch_editais_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.text = """
    <div class="elementor-widget-container">
        <a href="https://dpg.unb.br/wp-content/uploads/2026/03/Edital_04.pdf">Edital DPG Nº 04/2026 – PROGRAMA JOSUÉ DE CASTRO</a>
        <a href="https://dpg.unb.br/wp-content/uploads/2026/03/Edital_05.pdf">Edital DPG Nº 05/2026 – Apoio à Pesquisa</a>
    </div>
    """
    mock_resp.url = "https://dpg.unb.br/editais-abertos/"
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    editais = dpg_scraper.fetch_editais()
    assert len(editais) == 2
    assert "Edital DPG Nº 04/2026" in editais[0]["titulo"]
    assert editais[0]["link"].endswith("Edital_04.pdf")


@patch("app.modules.scraper.dpg.httpx.get")
def test_dpg_scraper_network_failure(mock_get):
    import httpx
    mock_get.side_effect = httpx.ConnectError("Falha de rede DPG")
    assert dpg_scraper.fetch_editais() == []
    assert dpg_scraper.fetch_documentos("https://dpg.unb.br/edital-invalido") == []


# ============================================================================
# 2. INT (Secretaria de Assuntos Internacionais)
# ============================================================================

def test_int_scraper_contract():
    assert issubclass(INTScraper, BaseScraper)
    assert int_scraper.orgao_origem == "INT"


@patch("app.modules.scraper.int_scraper.httpx.get")
def test_int_scraper_fetch_editais_and_docs(mock_get):
    # Mock da listagem
    mock_list_resp = MagicMock()
    mock_list_resp.text = """
    <div class="entry-content">
        <a href="/edital-int-n-9-2026/">Edital INT N 9/2026 - Intercâmbio Europa</a>
    </div>
    """
    mock_list_resp.url = "https://int.unb.br/selecoes-abertas/"
    mock_list_resp.raise_for_status.return_value = None

    # Mock da página interna
    mock_doc_resp = MagicMock()
    mock_doc_resp.text = """
    <div class="entry-content">
        <a href="/arquivos/edital_abertura.pdf">Edital de Abertura</a>
        <a href="/arquivos/resultado_final.pdf">Resultado Final Homologado</a>
    </div>
    """
    mock_doc_resp.url = "https://int.unb.br/edital-int-n-9-2026/"
    mock_doc_resp.raise_for_status.return_value = None

    mock_get.side_effect = [mock_list_resp, mock_doc_resp]

    editais = int_scraper.fetch_editais()
    assert len(editais) == 1
    assert "Edital INT N 9/2026" in editais[0]["titulo"]

    docs = int_scraper.fetch_documentos(editais[0]["link"])
    assert len(docs) == 2
    assert docs[0]["tipo"] == "original"
    assert docs[1]["tipo"] == "resultado_final"


# ============================================================================
# 3. DEX (Decanato de Extensão)
# ============================================================================

def test_dex_scraper_contract():
    assert issubclass(DEXScraper, BaseScraper)
    assert dex_scraper.orgao_origem == "DEX"


@patch("app.modules.scraper.dex.httpx.get")
def test_dex_scraper_fetch_editais(mock_get):
    mock_resp = MagicMock()
    mock_resp.text = """
    <div>
        <a href="/editais?download=2672:edital-dex-pibex">Edital PIBEX 2026 - Ações Comunitárias</a>
        <a href="/ddc/editalcasacoletiva">Edital Casa Coletiva Cultural</a>
    </div>
    """
    mock_resp.url = "https://dex.unb.br/editais"
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    editais = dex_scraper.fetch_editais()
    assert len(editais) == 2
    assert "PIBEX" in editais[0]["titulo"]
    assert "download=2672" in editais[0]["link"]


# ============================================================================
# 4. DPI (Decanato de Pesquisa e Inovação)
# ============================================================================

def test_dpi_scraper_contract():
    assert issubclass(DPIScraper, BaseScraper)
    assert dpi_scraper.orgao_origem == "DPI"


@patch("app.modules.scraper.dpi.httpx.get")
def test_dpi_scraper_fetch_editais(mock_get):
    mock_resp = MagicMock()
    mock_resp.text = """
    <div id="content">
        <a href="/editais/editais2026/167-edital-dpi-dpg-004">EDITAL DPI/DPG - Nº.004/2026 PROGRAMA ISAAC ROITMAN</a>
        <a href="/editais/editais2026/158-edital-003">EDITAL DPI/DEX/DPG/DEG Nº 003/2026</a>
    </div>
    """
    mock_resp.url = "https://dpi.unb.br/editais/editais2026"
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    editais = dpi_scraper.fetch_editais(2026)
    assert len(editais) == 2
    assert "ISAAC ROITMAN" in editais[0]["titulo"]


# ============================================================================
# 5. DAC (Decanato de Assuntos Comunitários)
# ============================================================================

def test_dac_scraper_contract():
    assert issubclass(DACScraper, BaseScraper)
    assert dac_scraper.orgao_origem == "DAC"


@patch("app.modules.scraper.dac.httpx.get")
def test_dac_scraper_fetch_editais(mock_get):
    mock_resp = MagicMock()
    mock_resp.text = """
    <div>
        <a href="https://dds.dac.unb.br/wp-content/uploads/2026/10/Edital_30.pdf">EDITAL Nº 30/2026 – INCLUSÃO NO PROGRAMA MORADIA ESTUDANTIL</a>
        <a href="https://dds.dac.unb.br/wp-content/uploads/2026/10/Edital_29.pdf">EDITAL Nº 29/2026 – INCLUSÃO NO PROGRAMA AUXÍLIO TRANSPORTE</a>
        <a href="https://dds.dac.unb.br/wp-content/uploads/2026/10/Edital_24.pdf">Edital Nº 24/2026 AUXÍLIO ALIMENTAÇÃO</a>
    </div>
    """
    mock_resp.url = "https://dds.dac.unb.br/2026-2/"
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    editais = dac_scraper.fetch_editais()
    assert len(editais) == 3
    assert "MORADIA ESTUDANTIL" in editais[0]["titulo"]
    assert "AUXÍLIO TRANSPORTE" in editais[1]["titulo"]


# ============================================================================
# 6. PROIC (Programa de Iniciação Científica)
# ============================================================================

def test_proic_scraper_contract():
    assert issubclass(PROICScraper, BaseScraper)
    assert proic_scraper.orgao_origem == "PROIC"


@patch("app.modules.scraper.proic.httpx.get")
def test_proic_scraper_fetch_editais(mock_get):
    mock_resp = MagicMock()
    mock_resp.text = """
    <div class="entry-content">
        <a href="https://proic.unb.br/wp-content/uploads/2026/05/edital_pibic_2026.pdf">Edital PIBIC 2026/2027</a>
        <a href="https://proic.unb.br/wp-content/uploads/2026/06/Retificacao-PIBIC.pdf">1ª Retificação Edital PIBIC 2026/2027</a>
        <a href="https://proic.unb.br/wp-content/uploads/2026/08/Resultado_Final_PIBIC.pdf">Resultado Final PIBIC 2026/2027</a>
    </div>
    """
    mock_resp.url = "https://proic.unb.br/editais/"
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    editais = proic_scraper.fetch_editais()
    assert len(editais) == 3
    assert "Edital PIBIC" in editais[0]["titulo"]


# ============================================================================
# 7. DACES (Diretoria de Acessibilidade)
# ============================================================================

def test_daces_scraper_contract():
    assert issubclass(DACESScraper, BaseScraper)
    assert daces_scraper.orgao_origem == "DACES"


@patch("app.modules.scraper.daces.httpx.get")
def test_daces_scraper_fetch_editais(mock_get):
    mock_resp = MagicMock()
    mock_resp.text = """
    <div>
        <a href="https://acessibilidade.unb.br/wp-content/uploads/2026/07/Edital_06.pdf">EDITAL 06/2026 – ABERTURA PTA TUTORIA</a>
        <a href="https://acessibilidade.unb.br/wp-content/uploads/2026/05/Edital_18.pdf">EDITAL N. 18/2026/DACES/DAC – LEDORES E TRANSCRITORES</a>
    </div>
    """
    mock_resp.url = "https://acessibilidade.unb.br/editais-2026/"
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    editais = daces_scraper.fetch_editais(2026)
    assert len(editais) == 2
    assert "PTA TUTORIA" in editais[0]["titulo"]


# ============================================================================
# 8. BCE (Biblioteca Central)
# ============================================================================

def test_bce_scraper_contract():
    assert issubclass(BCEScraper, BaseScraper)
    assert bce_scraper.orgao_origem == "BCE"


@patch("app.modules.scraper.bce.httpx.Client")
def test_bce_scraper_fetch_editais(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [
            {
                "id": 1,
                "title": "Edital DPI/BCE – n. 01/2026",
                "url": "https://repositorioadm.unb.br/editais/edital-dpi-bce-n-01-2026/",
                "metadata": {
                    "data-de-publicacao": {"value": "2026-01-30", "value_as_string": "30 de janeiro de 2026"},
                    "assunto-8": {"value_as_string": "Pesquisa"},
                    "descricao-5": {"value_as_string": "Objeto do edital"},
                },
            },
            {
                "id": 2,
                "title": "Edital DPI/BCE – n. 01/2025",
                "url": "https://repositorioadm.unb.br/editais/edital-dpi-bce-n-01-2025/",
                "metadata": {
                    "data-de-publicacao": {"value": "2025-01-21", "value_as_string": "21 de janeiro de 2025"},
                    "assunto-8": {"value_as_string": "Pesquisa"},
                    "descricao-5": {"value_as_string": "Objeto do edital"},
                },
            },
        ]
    }
    mock_resp.headers = {"x-wp-totalpages": "1"}
    mock_client.get.return_value = mock_resp

    editais = bce_scraper.fetch_editais()
    assert len(editais) == 2
    assert "Edital DPI/BCE – n. 01/2026" in editais[0]["titulo"]

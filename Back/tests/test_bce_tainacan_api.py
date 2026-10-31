"""Testes unitários e de integração para o scraper da BCE (Biblioteca Central) via API REST do Tainacan."""

import re
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
import httpx

from app.modules.scraper import SCRAPERS_REGISTRY, get_scraper
from app.modules.scraper.base import BaseScraper
from app.modules.scraper.bce import (
    BCEScraper,
    bce_scraper,
    BCE_API_ITEMS_URL,
    BCE_API_ATTACHMENTS_URL,
    parse_bce_html,
    _extract_meta_value,
)


MOCK_TAINACAN_ITEMS_RESPONSE: Dict[str, Any] = {
    "items": [
        {
            "id": 33575,
            "title": "Edital de Seleção Simplificada nº 05/2026/BCE",
            "url": "https://repositorioadm.unb.br/editais/edital-de-selecao-simplificada-no-05-2026-bce/",
            "status": "publish",
            "document_type": "attachment",
            "document": 33590,
            "creation_date": "2026-08-06 14:00:00",
            "metadata": {
                "titulo-6": {
                    "id": 12920,
                    "value": "Edital de Seleção Simplificada nº 05/2026/BCE",
                    "value_as_string": "Edital de Seleção Simplificada nº 05/2026/BCE",
                },
                "data-de-publicacao": {
                    "id": 12921,
                    "value": "2026-08-06",
                    "value_as_string": "6 de agosto de 2026",
                },
                "assunto-8": {
                    "id": 12922,
                    "value": [101, 102],
                    "value_as_string": "Bolsa | Processo seletivo",
                },
                "descricao-5": {
                    "id": 12923,
                    "value": "Abertura de processo seletivo simplificado para preenchimento de vaga de bolsista no projeto de marketing.",
                    "value_as_string": "Abertura de processo seletivo simplificado para preenchimento de vaga de bolsista no projeto de marketing.",
                },
                "unidades-de-origem": {
                    "id": 12924,
                    "value": "Biblioteca Central (BCE)",
                    "value_as_string": "Biblioteca Central (BCE)",
                },
                "tipo-7": {
                    "id": 12925,
                    "value": "Edital",
                    "value_as_string": "Edital",
                },
            },
        },
        {
            "id": 21371,
            "title": "Edital Nº 01/2023 DPI/DPG/BCE",
            "url": "https://repositorioadm.unb.br/editais/edital-no-01-2023-dpi-dpg-bce/",
            "status": "publish",
            "document_type": "attachment",
            "document": 21393,
            "creation_date": "2023-02-10 10:00:00",
            "metadata": {
                "titulo-6": {
                    "value": "Edital Nº 01/2023 DPI/DPG/BCE",
                    "value_as_string": "Edital Nº 01/2023 DPI/DPG/BCE",
                },
                "data-de-publicacao": {
                    "value": "2023-02-10",
                    "value_as_string": "10 de fevereiro de 2023",
                },
                "assunto-8": {
                    "value_as_string": "Alto impacto | Auxílio financeiro | Periódicos",
                },
                "descricao-5": {
                    "value_as_string": "Edital conjunto DPI/DPG/BCE para apoio financeiro a publicação de artigos.",
                },
                "unidades-de-origem": {
                    "value_as_string": "Biblioteca Central (BCE)",
                },
            },
        },
        {
            "id": 13620,
            "title": "Edital Nº 01/2018/BCE/DEG",
            "url": "https://repositorioadm.unb.br/editais/edital-no-01-2018-bce-deg/",
            "status": "publish",
            "document_type": "url",
            "document": "https://repositorioadm.unb.br/wp-content/uploads/2025/10/SEI_23106.019623_2018_19.pdf",
            "creation_date": "2018-05-04 11:00:00",
            "metadata": {
                "titulo-6": {
                    "value_as_string": "Edital Nº 01/2018/BCE/DEG",
                },
                "data-de-publicacao": {
                    "value": "2018-05-04",
                    "value_as_string": "4 de maio de 2018",
                },
                "assunto-8": {
                    "value_as_string": "Aquisição | Material bibliográfico",
                },
                "descricao-5": {
                    "value_as_string": "Aquisição de bibliografia básica e complementar para graduação.",
                },
            },
        },
    ]
}

MOCK_ATTACHMENTS_RESPONSE = [
    {
        "id": 33590,
        "title": "Edital-05-2026-BCE",
        "url": "https://repositorioadm.unb.br/wp-content/uploads/tainacan-items/12913/33575/Edital-05-2026-BCE.pdf",
        "mime_type": "application/pdf",
    },
    {
        "id": 33754,
        "title": "SEI_14625436_Edital_para_concessao_de_bolsas_e_auxilios",
        "url": "https://repositorioadm.unb.br/wp-content/uploads/tainacan-items/12913/33575/SEI_14625436_Edital_para_concessao_de_bolsas_e_auxilios.pdf",
        "mime_type": "application/pdf",
    },
]


def test_bce_scraper_contract():
    """Valida se BCEScraper herda de BaseScraper e define o órgão correto."""
    scraper = BCEScraper()
    assert isinstance(scraper, BaseScraper)
    assert scraper.orgao_origem == "BCE"


def test_bce_scraper_registry():
    """Valida se BCE está registrado em SCRAPERS_REGISTRY e acessível por get_scraper()."""
    assert "BCE" in SCRAPERS_REGISTRY
    scraper = get_scraper("BCE")
    assert scraper is not None
    assert scraper.orgao_origem == "BCE"
    assert isinstance(scraper, BCEScraper)


def test_extract_meta_value_helper():
    """Valida a extração de campos com preferência para ISO e strings."""
    meta = {
        "campo_iso": {"value": "2026-08-06", "value_as_string": "6 de agosto de 2026"},
        "campo_texto": {"value": ["1", "2"], "value_as_string": "Bolsa | Processo seletivo"},
        "campo_simples": {"value": "Simples"},
    }
    assert _extract_meta_value(meta, "campo_iso", prefer_iso=True) == "2026-08-06"
    assert _extract_meta_value(meta, "campo_iso", prefer_iso=False) == "6 de agosto de 2026"
    assert _extract_meta_value(meta, "campo_texto") == "Bolsa | Processo seletivo"
    assert _extract_meta_value(meta, "campo_simples") == "Simples"
    assert _extract_meta_value(meta, "inexistente") is None


@patch("app.modules.scraper.bce.httpx.Client")
def test_bce_fetch_editais_with_mock(mock_client_cls):
    """Valida a extração e mapeamento dos metadados ricos retornados pela API Tainacan."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = MOCK_TAINACAN_ITEMS_RESPONSE
    mock_resp.headers = {"x-wp-totalpages": "1"}
    mock_client.get.return_value = mock_resp

    scraper = BCEScraper()
    editais = scraper.fetch_editais()

    assert len(editais) == 3

    # Edital 1 (2026)
    edital_1 = editais[0]
    assert edital_1["titulo"] == "Edital de Seleção Simplificada nº 05/2026/BCE"
    assert edital_1["link"] == "https://repositorioadm.unb.br/editais/edital-de-selecao-simplificada-no-05-2026-bce/"
    assert edital_1["data_publicacao"] == "2026-08-06"
    assert edital_1["assunto"] == "Bolsa | Processo seletivo"
    assert edital_1["objeto"].startswith("Abertura de processo seletivo simplificado")
    assert edital_1["resumo"] == edital_1["objeto"]
    assert edital_1["descricao"] == edital_1["objeto"]
    assert edital_1["ano"] == 2026
    assert edital_1["item_id"] == 33575

    # Edital 3 (Legado 2018 com direct document URL)
    edital_3 = editais[2]
    assert edital_3["titulo"] == "Edital Nº 01/2018/BCE/DEG"
    assert edital_3["data_publicacao"] == "2018-05-04"
    assert edital_3["assunto"] == "Aquisição | Material bibliográfico"
    assert edital_3["ano"] == 2018
    assert edital_3["item_id"] == 13620


@patch("app.modules.scraper.bce.httpx.Client")
def test_bce_fetch_editais_year_filtering(mock_client_cls):
    """Valida o filtro de ano na coleta do Tainacan."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = MOCK_TAINACAN_ITEMS_RESPONSE
    mock_resp.headers = {"x-wp-totalpages": "1"}
    mock_client.get.return_value = mock_resp

    scraper = BCEScraper()
    editais_2026 = scraper.fetch_editais(year=2026)
    assert len(editais_2026) == 1
    assert editais_2026[0]["ano"] == 2026

    editais_2018 = scraper.fetch_editais(year=2018)
    assert len(editais_2018) == 1
    assert editais_2018[0]["ano"] == 2018

    editais_2020 = scraper.fetch_editais(year=2020)
    assert len(editais_2020) == 0


@patch("app.modules.scraper.bce.httpx.Client")
def test_bce_fetch_documentos_attachments_mock(mock_client_cls):
    """Valida a coleta e classificação de anexos a partir do endpoint /attachments."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = MOCK_ATTACHMENTS_RESPONSE
    mock_client.get.return_value = mock_resp

    scraper = BCEScraper()
    # Simula URL no cache apontando para o item 33575
    target_url = "https://repositorioadm.unb.br/editais/edital-de-selecao-simplificada-no-05-2026-bce/"
    scraper._url_to_id_cache[target_url] = 33575

    documentos = scraper.fetch_documentos(target_url)

    assert len(documentos) == 2
    assert any("Edital-05-2026-BCE" in doc["titulo"] for doc in documentos)
    assert any("Edital_para_concessao" in doc["titulo"] for doc in documentos)
    assert all(doc["link"].endswith(".pdf") for doc in documentos)
    assert all("tipo" in doc for doc in documentos)


@patch("app.modules.scraper.bce.httpx.Client")
def test_bce_fetch_documentos_direct_doc_url_mock(mock_client_cls):
    """Valida a coleta quando o item possui URL direta de PDF no campo document (itens legados)."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    # Simula resposta vazia em /attachments
    mock_resp_empty = MagicMock()
    mock_resp_empty.status_code = 200
    mock_resp_empty.json.return_value = []
    mock_client.get.return_value = mock_resp_empty

    scraper = BCEScraper()
    target_url = "https://repositorioadm.unb.br/editais/edital-no-01-2018-bce-deg/"
    scraper._url_to_id_cache[target_url] = 13620
    scraper._url_to_item_cache[target_url] = {
        "id": 13620,
        "document": "https://repositorioadm.unb.br/wp-content/uploads/2025/10/SEI_23106.019623_2018_19.pdf",
        "document_type": "url",
        "title": "Edital Nº 01/2018/BCE/DEG",
    }

    documentos = scraper.fetch_documentos(target_url)

    assert len(documentos) == 1
    assert documentos[0]["link"] == "https://repositorioadm.unb.br/wp-content/uploads/2025/10/SEI_23106.019623_2018_19.pdf"
    assert documentos[0]["tipo"] == "original"


@patch("app.modules.scraper.bce.httpx.Client")
def test_bce_network_failure_fallback(mock_client_cls):
    """Valida resiliência a falhas de rede na API sem propagar exceção não tratada."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_client.get.side_effect = httpx.ConnectTimeout("Timeout de conexão na API Tainacan")

    scraper = BCEScraper()
    editais = scraper.fetch_editais()
    assert editais == []

    docs = scraper.fetch_documentos("https://repositorioadm.unb.br/editais/qualquer-edital/")
    assert docs == []


def test_bce_html_parser_backwards_compatibility():
    """Garante que a função legacy parse_bce_html continua funcional para backward compatibility."""
    html = """
    <div>
        <a href="/editais/edital-01-2026.pdf">Edital nº 01/2026 - Convocação</a>
        <a href="https://repositorioadm.unb.br/editais/chamada-02-2026/">Chamada 02/2026 publicada em 15/04/2026</a>
        <a href="/tutorial">Tutorial</a>
    </div>
    """
    editais = parse_bce_html(html, base_url="https://bce.unb.br")
    assert len(editais) == 2
    assert "Edital nº 01/2026" in editais[0]["titulo"]
    assert editais[0]["link"].endswith(".pdf")
    assert editais[1]["data_publicacao"] == "15/04/2026"


@pytest.mark.live
def test_bce_live_fetch_all_29_editais():
    """Teste de integração ao vivo: consulta o Repositório Administrativo da BCE e valida os 29 editais."""
    scraper = BCEScraper(timeout=20.0)
    editais = scraper.fetch_editais()

    # O repositório oficial da BCE contém exatamente 29 editais
    assert len(editais) >= 29, f"Esperado ao menos 29 editais da BCE, obtido {len(editais)}"

    for edital in editais:
        assert edital["titulo"], "Edital sem título"
        assert edital["link"].startswith("https://repositorioadm.unb.br/editais/"), f"URL inválida: {edital['link']}"
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", edital["data_publicacao"]), f"Data ISO inválida: {edital['data_publicacao']}"
        assert edital["assunto"], f"Assunto não extraído para: {edital['titulo']}"
        assert edital["objeto"], f"Objeto não extraído para: {edital['titulo']}"
        assert edital["resumo"] == edital["objeto"]
        assert edital["ano"] is not None and edital["ano"] >= 2018

    # Testa extração de documentos para um edital recente com attachments
    first_url = editais[0]["link"]
    docs = scraper.fetch_documentos(first_url)
    assert len(docs) >= 1, f"Nenhum documento encontrado para o edital {first_url}"
    assert any(doc["link"].endswith(".pdf") for doc in docs)

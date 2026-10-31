"""Testes unitários e de integração para o scraper do CEAD (Educação a Distância e UAB)."""

from unittest.mock import MagicMock, patch
import pytest
import httpx

from app.modules.scraper.base import BaseScraper
from app.modules.scraper import CEADScraper, cead_scraper, get_scraper, SCRAPERS_REGISTRY


# ============================================================================
# 1. Testes de Contrato e Registro
# ============================================================================

def test_cead_scraper_contract():
    """Valida se o scraper do CEAD obedece ao contrato abstrato BaseScraper."""
    assert issubclass(CEADScraper, BaseScraper)
    scraper = CEADScraper()
    assert scraper.orgao_origem == "CEAD"
    assert cead_scraper.orgao_origem == "CEAD"


def test_cead_scraper_registered():
    """Valida se o CEAD está no catálogo central SCRAPERS_REGISTRY e acessível por get_scraper."""
    assert "CEAD" in SCRAPERS_REGISTRY
    assert SCRAPERS_REGISTRY["CEAD"] == cead_scraper
    assert get_scraper("CEAD") == cead_scraper
    assert get_scraper("cead") == cead_scraper
    assert get_scraper(" Cead ") == cead_scraper


# ============================================================================
# 2. Testes Unitários com Mocks (Isolados / Offline)
# ============================================================================

MOCK_CEAD_PAGE_1 = {
    "items": [
        {
            "id": 33035,
            "title": "Seleções CEAD 2026 - PGD - Termo Aditivo 06",
            "url": "https://cead.unb.br/editais/pgd-aditivo-06/",
            "creation_date": "2026-10-08 14:00:00",
            "metadata": {
                "ano": {"name": "Ano", "value": "2026"},
                "status-do-edital": {"name": "Status", "value": "Em andamento"},
                "data-de-publicacao": {"name": "Publicação", "value": "2026-10-08"},
                "fim-das-inscricoes": {"name": "Fim", "value": "2026-10-20"},
                "descricao-4": {"name": "Objeto", "value": "Processo seletivo para PGD."},
                "curso": {"name": "Curso", "value": "Pedagogia"},
                "publico-alvo-2": {"name": "Público", "value": "Servidor"},
                "numero": {"name": "Número", "value": "006/2026/CEAD"},
            },
        },
        {
            "id": 20100,
            "title": "Seleção UAB 2024 - Tutor Presencial",
            "url": "https://cead.unb.br/editais/uab-tutor-2024/",
            "creation_date": "2024-03-01 10:00:00",
            "metadata": {
                "ano": {"name": "Ano", "value": "2024"},
                "status-do-edital": {"name": "Status", "value": "Encerrado"},
                "data-de-publicacao": {"name": "Publicação", "value": "2024-03-01"},
                "fim-das-inscricoes": {"name": "Fim", "value": "2024-03-15"},
                "descricao-4": {"name": "Objeto", "value": "Seleção de tutores presenciais UAB."},
            },
        },
    ]
}

MOCK_CEAD_ATTACHMENTS = [
    {
        "id": 4001,
        "title": "Edital de Abertura nº 006/2026",
        "url": "https://cead.unb.br/wp-content/uploads/tainacan-items/8428/33035/Edital_006.pdf",
    },
    {
        "id": 4002,
        "title": "Resultado Final Homologado",
        "url": "https://cead.unb.br/wp-content/uploads/tainacan-items/8428/33035/Resultado_Final.pdf",
    },
]


@patch("app.modules.scraper.cead.httpx.Client")
def test_cead_fetch_editais_parsing(mock_client_cls):
    """Testa a extração dos campos estruturados do CEAD a partir da resposta JSON do Tainacan."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"x-wp-totalpages": "1"}
    mock_resp.json.return_value = MOCK_CEAD_PAGE_1
    mock_client.get.return_value = mock_resp

    scraper = CEADScraper()
    editais = scraper.fetch_editais()

    assert len(editais) == 2
    e1 = editais[0]
    assert e1["titulo"] == "Seleções CEAD 2026 - PGD - Termo Aditivo 06"
    assert e1["link"] == "https://cead.unb.br/editais/pgd-aditivo-06/"
    assert e1["data_publicacao"] == "2026-10-08"
    assert e1["inicio_inscricao"] == "2026-10-08"
    assert e1["fim_inscricao"] == "2026-10-20"
    assert e1["status"] == "aberto"
    assert e1["descricao"] == "Processo seletivo para PGD."
    assert e1["ano"] == 2026
    assert e1["curso"] == "Pedagogia"
    assert e1["publico_alvo"] == "Servidor"
    assert e1["numero"] == "006/2026/CEAD"

    e2 = editais[1]
    assert e2["status"] == "fechado"
    assert e2["ano"] == 2024


@patch("app.modules.scraper.cead.httpx.Client")
def test_cead_fetch_editais_filtered_by_year(mock_client_cls):
    """Garante que a filtragem por ano funciona corretamente no CEAD."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"x-wp-totalpages": "1"}
    mock_resp.json.return_value = MOCK_CEAD_PAGE_1
    mock_client.get.return_value = mock_resp

    scraper = CEADScraper()
    editais_2026 = scraper.fetch_editais(year=2026)
    assert len(editais_2026) == 1
    assert editais_2026[0]["ano"] == 2026

    editais_2024 = scraper.fetch_editais(year=2024)
    assert len(editais_2024) == 1
    assert editais_2024[0]["ano"] == 2024

    editais_2020 = scraper.fetch_editais(year=2020)
    assert len(editais_2020) == 0


@patch("app.modules.scraper.cead.httpx.Client")
def test_cead_fetch_documentos_via_api(mock_client_cls):
    """Testa a extração de documentos PDF oficiais via endpoint de anexos do Tainacan."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_resp_att = MagicMock()
    mock_resp_att.status_code = 200
    mock_resp_att.json.return_value = MOCK_CEAD_ATTACHMENTS
    mock_client.get.return_value = mock_resp_att

    scraper = CEADScraper()
    scraper._url_to_id_cache["https://cead.unb.br/editais/pgd-aditivo-06/"] = 33035

    docs = scraper.fetch_documentos("https://cead.unb.br/editais/pgd-aditivo-06/")
    assert len(docs) == 2
    assert docs[0]["link"].endswith(".pdf")
    assert docs[0]["tipo"] == "original"
    assert docs[1]["tipo"] == "resultado_final"


@patch("app.modules.scraper.cead.httpx.Client")
def test_cead_scraper_network_failure_resilience(mock_client_cls):
    """Valida que falhas HTTP não quebram o coletor e retornam lista vazia."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_client.get.side_effect = httpx.ConnectTimeout("Falha de conexão com cead.unb.br")

    scraper = CEADScraper()
    assert scraper.fetch_editais() == []
    assert scraper.fetch_documentos("https://cead.unb.br/editais/inexistente/") == []


# ============================================================================
# 3. Teste de Validação Real (Live Confirmation: Mais de 420 editais)
# ============================================================================

def test_cead_live_fetch_all_420_editais():
    """Validação real nos servidores da UnB: confirma se todos os mais de 420 editais são coletados."""
    scraper = CEADScraper(timeout=20.0)
    editais = scraper.fetch_editais()

    # Confirmação do volume de editais (mínimo de 420 editais da coleção do CEAD)
    assert len(editais) >= 420, f"Esperado >= 420 editais, obtido: {len(editais)}"

    # Verifica integridade estrutural de todos os itens coletados
    for edital in editais:
        assert edital["titulo"], "Edital não pode ter título vazio"
        assert edital["link"].startswith("http"), f"Link inválido: {edital['link']}"
        assert edital["data_publicacao"], f"Data de publicação ausente em {edital['titulo']}"
        assert edital["fim_inscricao"], f"Fim de inscrição ausente em {edital['titulo']}"
        assert edital["status"] in ["aberto", "fechado"], f"Status inválido: {edital['status']}"

    # Valida extração de documentos reais para um edital ativo recente
    edital_exemplo = editais[0]
    docs = scraper.fetch_documentos(edital_exemplo["link"])
    assert isinstance(docs, list)
    if docs:
        assert all(d["link"].startswith("http") for d in docs)
        assert any(d["link"].lower().endswith(".pdf") for d in docs)

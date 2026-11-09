"""Testes automatizados para os scrapers do Portal de Concursos da UnB e DGP Central."""

from unittest.mock import MagicMock, patch
import httpx
import pytest

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.concursos import (
    ConcursosScraper,
    concursos_scraper,
    parse_concursos_category_html,
    parse_concursos_edital_page,
)
from app.modules.scraper.dgp import (
    DGPScraper,
    dgp_scraper,
    parse_capacitacao_eventos_externos_html,
    parse_dgp_article_html,
    parse_estagio_category_html,
)


# ============================================================================
# 1. CONCURSOS.UNB.BR - Testes Unitários e de Integração
# ============================================================================

def test_concursos_scraper_instance_contract():
    """Garante que o ConcursosScraper segue o contrato de BaseScraper."""
    assert isinstance(concursos_scraper, BaseScraper)
    assert concursos_scraper.orgao_origem == "CONCURSOS"


def test_parse_concursos_category_html():
    """Garante a extração correta de links de editais de listagens Joomla de concursos."""
    sample_html = """
    <div id="content">
        <h2>Processos Seletivos Docentes</h2>
        <a href="/index.php/editais-docente/2025/2311-edital-de-abertura-n-015-2025">Edital de Abertura nº 015/2025</a>
        <a href="/index.php/editais-temporario/temporario-2025/2362-edital-de-abertura-n-174-2025">Edital de Abertura nº 174/2025</a>
        <a href="/index.php/efetivos-inicial">Voltar ao Início</a>
    </div>
    """
    links = parse_concursos_category_html(sample_html, base_url="https://concursos.unb.br")
    assert len(links) == 2
    assert links[0]["titulo"] == "Edital de Abertura nº 015/2025"
    assert "2311-edital-de-abertura-n-015-2025" in links[0]["link"]
    assert "2362-edital-de-abertura-n-174-2025" in links[1]["link"]


def test_parse_concursos_edital_page():
    """Garante a extração de descrição, datas, status e documentos de um edital de concurso."""
    sample_html = """
    <div class="item-page">
        <h2>Edital de Abertura nº 015/2025</h2>
        <p>Lotação: Departamento de Economia. Cargo: Professor de Magistério Superior. Área de Conhecimento: Microeconomia. Vaga: 01 (uma) vaga e formação de cadastro reserva.</p>
        <div id="content">
            <a href="/images/phocadownload/docentes/efetivos/2025/015/SEI_12276607_Edital_015.pdf">Edital de Abertura nº 15/2025 (23/01/2025)</a>
            <a href="/images/phocadownload/docentes/efetivos/2025/015/SEI_12695711_Edital_015.pdf">Retificação do Edital de Abertura (13/05/2025)</a>
            <a href="/images/phocadownload/docentes/efetivos/2026/027/final1.pdf">Edital de Resultado Final n. 181/2026</a>
        </div>
    </div>
    """
    page_url = "https://concursos.unb.br/index.php/editais-docente/2025/2311-edital-de-abertura-n-015-2025"
    parsed = parse_concursos_edital_page(sample_html, page_url)

    assert parsed["titulo"] == "Edital de Abertura nº 015/2025"
    assert "Departamento de Economia" in parsed["descricao"]
    assert parsed["data_publicacao"] == "23/01/2025"
    assert parsed["ano"] == 2025
    assert parsed["status"] == "fechado"  # Pois há "Resultado Final"
    assert len(parsed["documentos"]) == 3
    assert any("SEI_12276607" in d["link"] for d in parsed["documentos"])
    assert any("final1.pdf" in d["link"] for d in parsed["documentos"])


@patch("app.modules.scraper.concursos.httpx.Client")
def test_concursos_fetch_editais_with_mock(mock_client_cls):
    """Testa a coleta completa de editais de concurso com requisições mockadas."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    cat_resp = MagicMock()
    cat_resp.status_code = 200
    cat_resp.url = "https://concursos.unb.br/index.php/editais-docente/2025"
    cat_resp.text = """
    <div id="content">
        <a href="/index.php/editais-docente/2025/101-edital-de-abertura-01">Edital de Abertura nº 01/2025</a>
    </div>
    """

    page_resp = MagicMock()
    page_resp.status_code = 200
    page_resp.url = "https://concursos.unb.br/index.php/editais-docente/2025/101-edital-de-abertura-01"
    page_resp.text = """
    <div id="content">
        <h2>Edital de Abertura nº 01/2025</h2>
        <p>Lotação: FGA. Cargo: Professor Adjunto. Vaga: 02 vagas.</p>
        <a href="/images/edital_01.pdf">Edital de Abertura (15/02/2025)</a>
    </div>
    """

    def mock_get(url, **kwargs):
        if "101-edital" in url:
            return page_resp
        return cat_resp

    mock_client.get.side_effect = mock_get

    scraper = ConcursosScraper()
    editais = scraper.fetch_editais(year=2025, max_details=1)

    assert len(editais) == 1
    assert editais[0]["titulo"] == "Edital de Abertura nº 01/2025"
    assert editais[0]["data_publicacao"] == "15/02/2025"
    assert editais[0]["ano"] == 2025
    assert len(editais[0]["documentos"]) == 1


@patch("app.modules.scraper.concursos.httpx.Client")
def test_concursos_network_failure_resilience(mock_client_cls):
    """Garante que falhas de rede no portal de concursos retornam lista vazia sem exceções."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_client.get.side_effect = httpx.ConnectTimeout("Concursos indisponível")

    scraper = ConcursosScraper()
    assert scraper.fetch_editais() == []
    assert scraper.fetch_documentos("https://concursos.unb.br/teste") == []


@pytest.mark.live
def test_concursos_live_connectivity():
    """Teste de extração ao vivo no portal oficial de concursos da UnB."""
    scraper = ConcursosScraper(timeout=15.0)
    # Inspeciona 2 editais reais
    editais = scraper.fetch_editais(max_details=2)
    assert isinstance(editais, list)
    if editais:
        assert editais[0]["titulo"]
        assert editais[0]["link"].startswith("https://concursos.unb.br/")
        assert isinstance(editais[0]["documentos"], list)


# ============================================================================
# 2. DGP CENTRAL & ESTÁGIO UNB - Testes Unitários e de Integração
# ============================================================================

def test_dgp_scraper_instance_contract():
    """Garante que o DGPScraper segue o contrato de BaseScraper."""
    assert isinstance(dgp_scraper, BaseScraper)
    assert dgp_scraper.orgao_origem == "DGP"


def test_parse_estagio_category_html():
    """Garante a extração dos links de seleção de estágio do estagio.unb.br."""
    sample_html = """
    <div id="content">
        <a href="/index.php?option=com_content&view=article&id=334:edital-de-abertura-n-07-2026-ida-ppg&catid=214&Itemid=707">
            Edital de Abertura n. 07/2026 - IDA / PPG
        </a>
        <a href="/index.php?option=com_content&view=article&id=333:edital-de-abertura-n-01-2026-ida&catid=214&Itemid=707">
            Edital de Abertura n. 01/2026 - IDA
        </a>
        <a href="/index.php?option=com_content&view=featured&Itemid=101">Início</a>
    </div>
    """
    links = parse_estagio_category_html(sample_html, base_url="https://estagio.unb.br")
    assert len(links) == 2
    assert "334:edital-de-abertura-n-07-2026" in links[0]["link"]
    assert "333:edital-de-abertura-n-01-2026" in links[1]["link"]


def test_parse_dgp_article_html():
    """Garante a extração de título, PDFs e datas de um artigo de processo seletivo do DGP/Estágio."""
    sample_html = """
    <div class="item-page">
        <h2>Edital de Abertura n. 07/2026 - IDA / PPG</h2>
        <p>Processo seletivo para contratação de estagiários remunerados de nível superior.</p>
        <a href="/images/Processos_2026/Edital_07_2026.pdf">Edital de Abertura (28/10/2026)</a>
        <a href="/images/Processos_2026/EDITAL_DE_CONDICOES_GERAIS.pdf">Edital de Condições Gerais</a>
    </div>
    """
    page_url = "https://estagio.unb.br/index.php?option=com_content&view=article&id=334:edital-de-abertura-n-07-2026-ida-ppg&catid=214&Itemid=707"
    parsed = parse_dgp_article_html(sample_html, page_url, default_tipo="Estágio")

    assert parsed["titulo"] == "Edital de Abertura n. 07/2026 - IDA / PPG"
    assert parsed["tipo_edital"] == "Estágio"
    assert parsed["unidade"] in ["IDA", "IDA / PPG", "PPG"]
    assert parsed["data_publicacao"] == "28/10/2026"
    assert parsed["ano"] == 2026
    assert parsed["status"] == "aberto"
    assert len(parsed["documentos"]) == 2
    assert any("Edital_07_2026.pdf" in d["link"] for d in parsed["documentos"])


def test_parse_capacitacao_eventos_externos_html():
    """Garante a extração de editais de eventos externos da UnB Capacitação."""
    sample_html = """
    <div class="item-page">
        <ul>
            <li>
                <strong>Edital do DGP nº 1/2026:</strong>
                <a href="/images/editais/Edital_DGP_01_2026.pdf">Apoio a Eventos Externos</a>
            </li>
            <li>
                <strong>Edital do DGP nº 1/2025:</strong>
                <a href="/images/editais/Edital_01_2025.pdf">Edital</a>
                <a href="/images/editais/Resultado_01_2025.pdf">Resultado Final</a>
            </li>
        </ul>
    </div>
    """
    editais = parse_capacitacao_eventos_externos_html(
        sample_html, base_url="https://www.capacitacao.unb.br"
    )
    assert len(editais) == 2
    assert editais[0]["ano"] == 2026
    assert editais[0]["tipo_edital"] == "Capacitação / Eventos Externos"
    assert editais[0]["unidade"] == "DGP / PROCAP"
    assert len(editais[0]["documentos"]) == 1
    assert (
        editais[0]["documentos"][0]["link"]
        == "https://www.capacitacao.unb.br/images/editais/Edital_DGP_01_2026.pdf"
    )

    # Segundo edital possui resultado final, então status deve ser fechado
    assert editais[1]["ano"] == 2025
    assert editais[1]["status"] == "fechado"
    assert len(editais[1]["documentos"]) == 2


@patch("app.modules.scraper.dgp.httpx.Client")
def test_dgp_fetch_editais_with_mock(mock_client_cls):
    """Testa a coleta de editais do DGP e Estágio com requisições mockadas."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    cat_resp = MagicMock()
    cat_resp.status_code = 200
    cat_resp.url = "https://estagio.unb.br/index.php?option=com_content&view=category&layout=blog&id=214&Itemid=707"
    cat_resp.text = """
    <div>
        <a href="/index.php?option=com_content&view=article&id=10:edital-de-abertura-01-2026-vrt&catid=214&Itemid=707">
            Edital de Abertura nº 01/2026 - VRT
        </a>
    </div>
    """

    art_resp = MagicMock()
    art_resp.status_code = 200
    art_resp.url = "https://estagio.unb.br/index.php?option=com_content&view=article&id=10:edital-de-abertura-01-2026-vrt&catid=214&Itemid=707"
    art_resp.text = """
    <div class="item-page">
        <h2>Edital de Abertura nº 01/2026 - VRT</h2>
        <a href="/images/edital_vrt_2026.pdf">Edital de Abertura (10/01/2026)</a>
    </div>
    """

    search_resp = MagicMock()
    search_resp.status_code = 200
    search_resp.url = "https://dgp.unb.br/?searchword=edital"
    search_resp.text = "<div class='search-results'></div>"

    cap_resp = MagicMock()
    cap_resp.status_code = 200
    cap_resp.url = "https://www.capacitacao.unb.br/eventos-externos-editais"
    cap_resp.text = """
    <div class="item-page">
        <ul>
            <li>
                <strong>Edital do DGP nº 1/2026:</strong>
                <a href="/images/editais/Edital_DGP_01_2026.pdf">Apoio a Eventos Externos</a>
            </li>
        </ul>
    </div>
    """

    def mock_get(url, **kwargs):
        if "id=10:" in url:
            return art_resp
        if "eventos-externos-editais" in url:
            return cap_resp
        if "dgp.unb.br" in url or "capacitacao.unb.br" in url:
            return search_resp
        return cat_resp

    mock_client.get.side_effect = mock_get

    scraper = DGPScraper()
    editais = scraper.fetch_editais(max_pages=1, max_details=1)

    assert len(editais) == 2
    # Verifica que coletou tanto o processo de estágio quanto o edital de capacitação
    titulos = [e["titulo"] for e in editais]
    assert any("Edital de Abertura nº 01/2026 - VRT" in t for t in titulos)
    assert any("Edital DGP nº 1/2026" in t for t in titulos)


@patch("app.modules.scraper.dgp.httpx.Client")
def test_dgp_network_failure_resilience(mock_client_cls):
    """Garante que falhas de rede no DGP retornam lista vazia sem exceções."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_client.get.side_effect = httpx.ConnectTimeout("DGP indisponível")

    scraper = DGPScraper()
    assert scraper.fetch_editais() == []
    assert scraper.fetch_documentos("https://dgp.unb.br/teste") == []


@pytest.mark.live
def test_dgp_live_connectivity():
    """Teste de extração ao vivo na Coordenadoria de Estágio do DGP da UnB."""
    scraper = DGPScraper(timeout=15.0)
    # Inspeciona 2 editais reais
    editais = scraper.fetch_editais(max_pages=1, max_details=2)
    assert isinstance(editais, list)
    if editais:
        assert editais[0]["titulo"]
        assert editais[0]["link"].startswith("https://")
        assert isinstance(editais[0]["documentos"], list)

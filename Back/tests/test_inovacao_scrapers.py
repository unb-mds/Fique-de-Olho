"""Testes unitários e de integração para os scrapers de Inovação e Fundações (Issue #84 - Parte 3).

Cobre:
7. FINATEC (Fundação de Empreendimentos Científicos e Tecnológicos - finatec.org.br)
8. CDT (Centro de Apoio ao Desenvolvimento Tecnológico - cdt.unb.br)
9. PCTec (Parque Científico e Tecnológico da UnB - pctec.unb.br)
"""

from unittest.mock import MagicMock, patch
import httpx
import pytest

from app.modules.scraper import SCRAPERS_REGISTRY, get_scraper
from app.modules.scraper.base import BaseScraper
from app.modules.scraper.finatec import (
    FinatecScraper,
    classify_finatec_document,
    classify_finatec_edital,
    finatec_scraper,
    parse_finatec_content_html,
    parse_finatec_editais_html,
    parse_finatec_wp_item,
)
from app.modules.scraper.cdt import (
    CDTScraper,
    cdt_scraper,
    classify_cdt_document,
    classify_cdt_edital,
    parse_cdt_article_html,
    parse_cdt_chamadas_html,
)
from app.modules.scraper.pctec import (
    PCTecScraper,
    classify_pctec_document,
    classify_pctec_edital,
    normalize_pctec_url,
    parse_pctec_chamadas_overview_html,
    parse_pctec_edital_page_html,
    pctec_scraper,
)


# ============================================================================
# 1. FINATEC - Testes Unitários e de Integração
# ============================================================================


def test_finatec_scraper_instance_contract():
    """Garante que o FinatecScraper segue o contrato de BaseScraper e está registrado."""
    assert isinstance(finatec_scraper, BaseScraper)
    assert finatec_scraper.orgao_origem == "FINATEC"
    assert get_scraper("finatec") is finatec_scraper
    assert "FINATEC" in SCRAPERS_REGISTRY


def test_classify_finatec_edital_and_documents():
    """Testa a categorização de editais (Bolsista, Estagiário, Celetista, Fomento) e documentos da Finatec."""
    cat_bolsa = classify_finatec_edital(
        "Edital de Bolsista 049/2026 – Doutorado em Educação",
        class_list=["contratacao-edital-bolsista", "local-brasilia", "area_de_atuacao-educacao"],
    )
    assert cat_bolsa["tipo"] == "Bolsas de Pesquisa e P&D"
    assert "Bolsa de Projeto" in cat_bolsa["tipo_edital"]
    assert "Educacao" in cat_bolsa["areas"]
    assert "Brasilia" in cat_bolsa["locais"]

    cat_estagio = classify_finatec_edital(
        "Edital de Estagiário 048/2026 – Administração",
        class_list=["contratacao-edital-estagiario"],
    )
    assert cat_estagio["tipo"] == "Estágio em Projeto"

    cat_clt = classify_finatec_edital(
        "Edital de Celetista 020/2025 – Analista Júnior",
        class_list=["contratacao-edital-celetista"],
    )
    assert cat_clt["tipo"] == "Seleção de Pesquisador / Celetista"

    cat_fomento = classify_finatec_edital("Finatec divulga primeiro edital de Fomento")
    assert cat_fomento["tipo"] == "Fomento e Pesquisa (P&D)"

    assert classify_finatec_document("Comunicado 03 – Resultado Final", "res_final.pdf") == "resultado_final"
    assert classify_finatec_document("Comunicado 02 – Resultado Preliminar", "prelim.pdf") == "resultado_provisorio"
    assert classify_finatec_document("Comunicado 01 – Alteração de Cronograma", "crono.pdf") == "retificacao"
    assert classify_finatec_document("Acesse o Edital de Bolsista 049/2026", "edital.pdf") == "original"


def test_parse_finatec_wp_item():
    """Garante a extração completa de metadados, assunto explícito e PDFs de um item da API WP da Finatec."""
    sample_item = {
        "id": 48025,
        "date": "2026-09-22T11:10:39",
        "link": "https://www.finatec.org.br/vaga/edital-de-estagiario-048-2026/",
        "title": {
            "rendered": "Edital de Estagi&#225;rio 048/2026 &#8211; Gradua&#231;&#227;o em Administra&#231;&#227;o"
        },
        "class_list": [
            "vaga",
            "contratacao-edital-estagiario",
            "local-brasilia",
            "area_de_atuacao-administracao",
        ],
        "content": {
            "rendered": """
            <p><a href="https://www.finatec.org.br/wp-content/uploads/2026/09/Edital-048-2026.pdf">Acesse o Edital de Estagiário 048/2026</a></p>
            <p><a href="https://www.finatec.org.br/wp-content/uploads/2026/10/Comunicado-01-Resultado-Preliminar.pdf">Comunicado 01 – Resultado Preliminar</a></p>
            <div><a href="https://www.finatec.org.br/editais_finatec/admin/login/">INSCREVA-SE</a></div>
            """
        },
    }

    parsed = parse_finatec_wp_item(sample_item)
    assert parsed["titulo"] == "Edital de Estagiário 048/2026 – Graduação em Administração"
    assert parsed["unidade"] == "FINATEC"
    assert parsed["tipo"] == "Estágio em Projeto"
    assert "Seleção Finatec (Estágio em Projeto)" in parsed["assunto"]
    assert parsed["ano"] == 2026
    assert parsed["data_publicacao"] == "2026-09-22"
    assert parsed["status"] == "aberto"
    assert parsed["link_inscricao"] == "https://www.finatec.org.br/editais_finatec/admin/login/"
    assert len(parsed["documentos"]) == 2
    assert parsed["documentos"][0]["tipo"] == "original"
    assert parsed["documentos"][1]["tipo"] == "resultado_provisorio"


def test_parse_finatec_editais_html():
    """Garante a extração de editais da página de arquivo HTML /editais/ da Finatec."""
    sample_html = """
    <main>
        <article class="post category-editais">
            <h2><a href="https://www.finatec.org.br/noticia/edital-conselho-fiscal-2026/">Edital de Convocação 01/2026 – Conselho Fiscal</a></h2>
            <time datetime="2026-05-10T10:00:00">10/05/2026</time>
            <div class="entry-content">
                <a href="https://www.finatec.org.br/wp-content/uploads/2026/05/Edital_Conselho.pdf">Acesse edital completo</a>
            </div>
        </article>
    </main>
    """
    editais = parse_finatec_editais_html(sample_html)
    assert len(editais) == 1
    assert editais[0]["titulo"] == "Edital de Convocação 01/2026 – Conselho Fiscal"
    assert editais[0]["ano"] == 2026
    assert editais[0]["status"] == "aberto"
    assert len(editais[0]["documentos"]) == 1


@patch("app.modules.scraper.finatec.httpx.Client")
def test_finatec_fetch_editais_and_documentos_mock(mock_client_cls):
    """Testa o fluxo de coleta de editais e documentos da Finatec com requisições HTTP mockadas."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    vaga_resp = MagicMock()
    vaga_resp.status_code = 200
    vaga_resp.headers = {"x-wp-totalpages": "1"}
    vaga_resp.json.return_value = [
        {
            "id": 100,
            "date": "2026-08-19T14:16:03",
            "link": "https://www.finatec.org.br/vaga/edital-de-bolsista-047-2026/",
            "title": {"rendered": "Edital de Bolsista 047/2026 – Tecnologia da Informação"},
            "class_list": ["contratacao-edital-bolsista", "local-brasilia"],
            "content": {
                "rendered": '<a href="https://www.finatec.org.br/wp-content/uploads/2026/08/Edital_047.pdf">Edital 047/2026</a>'
            },
        }
    ]

    posts_resp = MagicMock()
    posts_resp.status_code = 200
    posts_resp.json.return_value = [
        {
            "id": 200,
            "date": "2023-09-27T10:00:00",
            "link": "https://www.finatec.org.br/noticia/edital-conselho-2023/",
            "title": {"rendered": "Edital de Convocação 2023"},
            "class_list": ["category-editais"],
            "content": {
                "rendered": '<a href="https://www.finatec.org.br/wp-content/uploads/2023/09/EDITAL-2023.pdf">Edital</a>'
            },
        }
    ]

    def mock_get(url, **kwargs):
        if "/vaga" in url:
            return vaga_resp
        return posts_resp

    mock_client.get.side_effect = mock_get

    scraper = FinatecScraper()
    all_editais = scraper.fetch_editais(max_pages=1, include_posts=True)
    assert len(all_editais) == 2

    only_2026 = scraper.fetch_editais(year=2026, max_pages=1, include_posts=True)
    assert len(only_2026) == 1
    assert only_2026[0]["ano"] == 2026

    docs = scraper.fetch_documentos("https://www.finatec.org.br/vaga/edital-de-bolsista-047-2026/")
    assert len(docs) == 1
    assert "Edital_047.pdf" in docs[0]["link"]


@patch("app.modules.scraper.finatec.httpx.Client")
def test_finatec_network_failure_resilience(mock_client_cls):
    """Garante que falhas de rede na Finatec retornam lista vazia sem propagar exceção."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_client.get.side_effect = httpx.ConnectTimeout("Finatec timeout")

    scraper = FinatecScraper()
    assert scraper.fetch_editais() == []
    assert scraper.fetch_documentos("https://www.finatec.org.br/vaga/inexistente") == []


# ============================================================================
# 2. CDT - Testes Unitários e de Integração
# ============================================================================


def test_cdt_scraper_instance_contract():
    """Garante que o CDTScraper segue o contrato de BaseScraper e está registrado."""
    assert isinstance(cdt_scraper, BaseScraper)
    assert cdt_scraper.orgao_origem == "CDT"
    assert get_scraper("cdt") is cdt_scraper
    assert "CDT" in SCRAPERS_REGISTRY


def test_classify_cdt_edital_and_documents():
    """Testa a classificação de programas e documentos do CDT."""
    c_mulher = classify_cdt_edital("EDITAL CDT Nº 004/2026 – 3ª EDIÇÃO DO PROGRAMA PRISMA MULHER")
    assert c_mulher["programa"] == "PRISMA Mulher"
    assert "Feminino" in c_mulher["tipo"]

    c_prisma = classify_cdt_edital("EDITAL CDT Nº 006/2026 – AUXÍLIO FINANCEIRO PROGRAMA PRISMA III")
    assert c_prisma["programa"] == "Programa PRISMA"

    c_spin = classify_cdt_edital("EDITAL CDT/DPI N.º 005/2026: FÁBRICA DE SPINOFF – 2º CICLO")
    assert c_spin["tipo"] == "Incubação de Startups e Spin-offs"

    c_ej = classify_cdt_edital("Chamada Pública Programa Pró-Júnior - Empresas Juniores")
    assert c_ej["tipo"] == "Empresas Juniores"

    assert classify_cdt_document("Resultado Final", "despacho_final.pdf") == "resultado_final"
    assert classify_cdt_document("Resultado Preliminar da 1ª etapa", "comunicado1.pdf") == "resultado_provisorio"
    assert classify_cdt_document("1ª Retificação do Edital", "ret.pdf") == "retificacao"


def test_parse_cdt_chamadas_html():
    """Garante a extração de chamadas públicas, datas, assunto e PDFs do blog do CDT."""
    sample_html = """
    <div class="blog">
        <h2>02 de Julho de 2026</h2>
        <div class="items-row cols-1 row-0">
            <div class="item" itemprop="blogPost">
                <h2 itemprop="name">
                    <a href="/pt-br/processos-seletivos/2025/416-chamada-publica-2026/1037-edital005-2026">
                        EDITAL CDT/DPI N.º 005/2026: FÁBRICA DE SPINOFF – 2º CICLO
                    </a>
                </h2>
                <span itemprop="introtext">
                    <p>O Centro de Apoio ao Desenvolvimento Tecnológico (CDT) torna público o Edital da Fábrica de Spinoff.</p>
                    <p><a href="/images/CDT/2026/005/Edital_CDTDPI_005_2026_Fabrica_de_Spinoff.pdf">Edital de Abertura</a> - 02/07/2026</p>
                    <p><a href="/images/CDT/2026/005/Retificao_Eital_n_005_2026.pdf">Edital Retificado</a></p>
                </span>
            </div>
        </div>
    </div>
    """
    editais = parse_cdt_chamadas_html(sample_html, base_url="https://cdt.unb.br")
    assert len(editais) == 1
    ed = editais[0]
    assert ed["titulo"] == "EDITAL CDT/DPI N.º 005/2026: FÁBRICA DE SPINOFF – 2º CICLO"
    assert ed["unidade"] == "CDT"
    assert ed["tipo"] == "Incubação de Startups e Spin-offs"
    assert "Multincubadora / Fábrica de Spin-off" in ed["assunto"]
    assert ed["data_publicacao"] == "02/07/2026"
    assert ed["ano"] == 2026
    assert ed["status"] == "aberto"
    assert len(ed["documentos"]) == 2
    assert ed["documentos"][0]["tipo"] == "original"
    assert ed["documentos"][1]["tipo"] == "retificacao"


def test_parse_cdt_article_html():
    """Garante a extração do edital de fluxo contínuo da Multincubadora do CDT."""
    sample_html = """
    <div class="item-page">
        <h2>Edital de fluxo contínuo para incubação de empreendimentos inovadores na Multincubadora da UnB</h2>
        <p>O Centro de Apoio ao Desenvolvimento Tecnológico da UnB torna público o processo de seleção para a Multincubadora de Empresas.</p>
        <a href="/images/CEDES/Documentos/Edital_2024/Edital_incubacao_UnB_2024.pdf">1. Edital de abertura</a>
        <a href="https://forms.office.com/r/AYCyHLRYG8">2. Formulário de inscrição</a>
        <a href="/images/CEDES/Documentos/Edital_2024/SEI_11475122_Comunicado_01.pdf">6. Suspensão do Edital</a>
    </div>
    """
    page_url = "https://cdt.unb.br/pt-br/chamadas/409-chamadas-publicas-2024/683-edital-de-fluxo-continuo"
    parsed = parse_cdt_article_html(sample_html, page_url)
    assert "Multincubadora" in parsed["titulo"]
    assert parsed["tipo"] == "Incubação de Startups e Spin-offs"
    assert parsed["ano"] == 2024
    assert parsed["status"] == "fechado"
    assert parsed["link_inscricao"] == "https://forms.office.com/r/AYCyHLRYG8"
    assert len(parsed["documentos"]) == 2


@patch("app.modules.scraper.cdt.httpx.Client")
def test_cdt_fetch_editais_with_mock(mock_client_cls):
    """Testa a coleta de chamadas do CDT com requisições HTTP mockadas."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    chamadas_resp = MagicMock()
    chamadas_resp.status_code = 200
    chamadas_resp.url = "https://cdt.unb.br/pt-br/chamadas"
    chamadas_resp.text = """
    <div class="blog">
        <div class="item" itemprop="blogPost">
            <h2 itemprop="name">
                <a href="/pt-br/processos-seletivos/2025/416-chamada-publica-2026/1036-edital004-2026">
                    EDITAL CDT Nº 004/2026 – 3ª EDIÇÃO DO PROGRAMA PRISMA MULHER
                </a>
            </h2>
            <p><a href="/images/CDT/2026/004/Edital_CDT_004_2026_Prisma_Mulher.pdf">Edital de Abertura</a></p>
        </div>
    </div>
    """

    inc_resp = MagicMock()
    inc_resp.status_code = 200
    inc_resp.url = "https://cdt.unb.br/pt-br/chamadas/409-chamadas-publicas-2024/683-edital-de-fluxo-continuo"
    inc_resp.text = """
    <div class="item-page">
        <h2>Edital de fluxo contínuo para incubação na Multincubadora 2024</h2>
        <a href="/images/CEDES/Edital_incubacao_2024.pdf">Edital de Abertura</a>
    </div>
    """

    def mock_get(url, **kwargs):
        if "683-edital" in url:
            return inc_resp
        return chamadas_resp

    mock_client.get.side_effect = mock_get

    scraper = CDTScraper()
    editais = scraper.fetch_editais(max_pages=1)
    assert len(editais) == 2
    assert any("PRISMA MULHER" in e["titulo"] for e in editais)
    assert any("Multincubadora" in e["titulo"] for e in editais)


@patch("app.modules.scraper.cdt.httpx.Client")
def test_cdt_network_failure_resilience(mock_client_cls):
    """Garante que falhas de rede no CDT retornam lista vazia sem exceções."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_client.get.side_effect = httpx.ConnectTimeout("CDT indisponível")

    scraper = CDTScraper()
    assert scraper.fetch_editais() == []
    assert scraper.fetch_documentos("https://cdt.unb.br/pt-br/chamadas") == []


# ============================================================================
# 3. PCTEC - Testes Unitários e de Integração
# ============================================================================


def test_pctec_scraper_instance_contract():
    """Garante que o PCTecScraper segue o contrato de BaseScraper e está registrado."""
    assert isinstance(pctec_scraper, BaseScraper)
    assert pctec_scraper.orgao_origem == "PCTEC"
    assert get_scraper("pctec") is pctec_scraper
    assert "PCTEC" in SCRAPERS_REGISTRY


def test_pctec_helpers_and_classification():
    """Testa a normalização de domínio de homologação e classificação de editais do PCTec."""
    homologa_url = "https://pctec.sites.homologa.unb.br/wp-content/uploads/2025/12/Edital.pdf"
    assert normalize_pctec_url(homologa_url) == "https://pctec.unb.br/wp-content/uploads/2025/12/Edital.pdf"

    c_res = classify_pctec_edital("Edital de Seleção Pública do Programa de Residência Tecnológica – Ocean UnB – Nº 02/2026")
    assert c_res["tipo"] == "Residência Tecnológica e Bolsas P&D"

    c_ia = classify_pctec_edital("EDITAL PCTEC/DPI/STI Nº 001/2025 – LABORATÓRIO MULTIUSUÁRIO DE INTELIGÊNCIA ARTIFICIAL")
    assert c_ia["tipo"] == "Infraestrutura de Pesquisa e IA"

    c_ocup = classify_pctec_edital("EDITAL DE FLUXO CONTÍNUO DE CHAMAMENTO PÚBLICO Nº 01/2024")
    assert c_ocup["tipo"] == "Ocupação e Residência de Empresas no Parque"

    assert classify_pctec_document("Edital 31.2015 (Resultado Fase II)", "fase2.pdf") == "resultado_final"
    assert classify_pctec_document("Edital 111.2014 (Resultado de Habilitação)", "hab.pdf") == "resultado_provisorio"
    assert classify_pctec_document("Edital 1/2022 (Retificação II)", "ret2.pdf") == "retificacao"


def test_parse_pctec_chamadas_overview_and_detail_html():
    """Garante a extração de editais abertos, encerrados e históricos da página /chamadas/ do PCTec."""
    sample_overview = """
    <div class="entry-content">
        <h2>Editais abertos</h2>
        <ul>
            <li><a href="https://pctec.unb.br/edital-ocean-02-2026/">Edital de Residência Tecnológica Ocean UnB Nº 02/2026</a></li>
            <li><a href="/edital-uso-continuo-01-2024/">EDITAL DE FLUXO CONTÍNUO DE CHAMAMENTO PÚBLICO Nº 01/2024</a></li>
        </ul>
        <h2>Editais encerrados</h2>
        <p><a href="/edital-1-2022-2/">Edital de Chamamento Público nº 1/2022</a> (fluxo contínuo)</p>
        <p>Edital de Pré-Qualificação nº 31/2015</p>
        <p><a href="/wp-content/uploads/2025/12/Edital_31_2015_Fase_I.pdf">Edital 31.2015 (Resultado Fase I)</a></p>
        <p><a href="https://pctec.sites.homologa.unb.br/wp-content/uploads/2025/12/Edital_31_2015_Fase_II.pdf">Edital 31.2015 (Resultado Fase II)</a></p>
    </div>
    """
    items = parse_pctec_chamadas_overview_html(sample_overview)
    assert len(items) == 4
    assert items[0]["status"] == "aberto"
    assert items[0]["ano"] == 2026
    assert items[1]["status"] == "aberto"
    assert items[2]["status"] == "fechado"
    assert items[2]["ano"] == 2022

    # O 4º item é o histórico de 2015 com 2 PDFs agrupados e URL de homologação corrigida
    assert items[3]["titulo"] == "Edital de Pré-Qualificação nº 31/2015"
    assert items[3]["status"] == "fechado"
    assert items[3]["ano"] == 2015
    assert len(items[3]["documentos"]) == 2
    assert items[3]["documentos"][1]["link"].startswith("https://pctec.unb.br/wp-content/")

    sample_detail = """
    <div class="entry-content">
        <p>A Universidade de Brasília (UnB) torna público o presente Edital de Seleção Pública para ingresso no Programa de Residência Tecnológica em Saúde Digital.</p>
        <a href="https://pctec.unb.br/wp-content/uploads/2026/09/EDITAL-OCEAN-02-2026.pdf">01 – Edital 02/2026</a>
    </div>
    """
    detail = parse_pctec_edital_page_html(
        sample_detail,
        page_url="https://pctec.unb.br/edital-ocean-02-2026/",
        default_title=items[0]["titulo"],
        default_status="aberto",
        data_publicacao="2026-09-02",
    )
    assert detail["ano"] == 2026
    assert detail["status"] == "aberto"
    assert len(detail["documentos"]) == 1
    assert "Residência Tecnológica" in detail["assunto"]


@patch("app.modules.scraper.pctec.httpx.Client")
def test_pctec_fetch_editais_with_mock(mock_client_cls):
    """Testa o fluxo completo do PCTecScraper com chamadas mockadas para a API WP."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    overview_resp = MagicMock()
    overview_resp.status_code = 200
    overview_resp.json.return_value = [
        {
            "id": 11766,
            "slug": "chamadas",
            "date": "2026-01-01T00:00:00",
            "content": {
                "rendered": """
                <h2>Editais abertos</h2>
                <ul>
                    <li><a href="https://pctec.unb.br/edital-ocean-02-2026/">Edital Ocean UnB Nº 02/2026</a></li>
                </ul>
                """
            },
        }
    ]

    detail_resp = MagicMock()
    detail_resp.status_code = 200
    detail_resp.json.return_value = [
        {
            "id": 23816,
            "slug": "edital-ocean-02-2026",
            "date": "2026-09-02T18:29:23",
            "content": {
                "rendered": """
                <p>A Universidade de Brasília torna público o Edital de Seleção Pública do Programa de Residência Tecnológica em Saúde Digital.</p>
                <a href="https://pctec.unb.br/wp-content/uploads/2026/09/EDITAL_02_2026.pdf">01 – Edital 02/2026</a>
                """
            },
        }
    ]

    def mock_get(url, **kwargs):
        params = kwargs.get("params") or {}
        if params.get("slug") == "chamadas":
            return overview_resp
        return detail_resp

    mock_client.get.side_effect = mock_get

    scraper = PCTecScraper()
    editais = scraper.fetch_editais()
    assert len(editais) == 1
    assert editais[0]["titulo"] == "Edital Ocean UnB Nº 02/2026"
    assert editais[0]["ano"] == 2026
    assert len(editais[0]["documentos"]) == 1

    docs = scraper.fetch_documentos("https://pctec.unb.br/edital-ocean-02-2026/")
    assert len(docs) == 1


@patch("app.modules.scraper.pctec.httpx.Client")
def test_pctec_network_failure_resilience(mock_client_cls):
    """Garante que falhas de rede no PCTec retornam lista vazia sem exceções."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_client.get.side_effect = httpx.ConnectTimeout("PCTec indisponível")

    scraper = PCTecScraper()
    assert scraper.fetch_editais() == []
    assert scraper.fetch_documentos("https://pctec.unb.br/chamadas/") == []


# ============================================================================
# 4. Testes ao Vivo (Live Connectivity)
# ============================================================================


@pytest.mark.live
def test_finatec_live_connectivity():
    """Teste ao vivo na API de editais/vagas da FINATEC."""
    editais = finatec_scraper.fetch_editais(max_pages=1, include_posts=False)
    assert isinstance(editais, list)
    assert len(editais) > 0
    assert editais[0]["titulo"]
    assert editais[0]["assunto"]


@pytest.mark.live
def test_cdt_live_connectivity():
    """Teste ao vivo no portal de chamadas públicas do CDT/UnB."""
    editais = cdt_scraper.fetch_editais(max_pages=1)
    assert isinstance(editais, list)
    assert len(editais) > 0
    assert editais[0]["titulo"]
    assert editais[0]["assunto"]


@pytest.mark.live
def test_pctec_live_connectivity():
    """Teste ao vivo no portal de ofertas públicas do PCTec/UnB."""
    editais = pctec_scraper.fetch_editais(max_details=2)
    assert isinstance(editais, list)
    assert len(editais) > 0
    assert editais[0]["titulo"]
    assert editais[0]["assunto"]

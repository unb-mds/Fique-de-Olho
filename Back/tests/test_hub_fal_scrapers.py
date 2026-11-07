"""Testes unitários e de integração para os scrapers de Saúde, Meio Ambiente e Prática Profissional (Issue #84 - Parte 4).

Cobre:
10. HUB (Hospital Universitário de Brasília / Ebserh / HU Brasil - gov.br/hubrasil)
11. FAL (Fazenda Água Limpa da UnB - fal.unb.br e fav.unb.br/estagio)
"""

from unittest.mock import MagicMock, patch
import httpx
import pytest

from app.modules.scraper import SCRAPERS_REGISTRY, get_scraper
from app.modules.scraper.base import BaseScraper
from app.modules.scraper.hub import (
    HUBScraper,
    classify_hub_document,
    classify_hub_edital,
    extract_docs_from_govbr_html,
    extract_enare_fgv_publicacoes,
    extract_plone_tab_urls,
    hub_scraper,
    is_document_url,
    is_hub_relevant_pss,
    normalize_govbr_doc_url,
    parse_hub_page_as_edital,
    parse_ocean_unb_oportunidades_table,
)
from app.modules.scraper.fal import (
    FALScraper,
    classify_fal_document,
    classify_fal_edital,
    detect_fal_area,
    fal_scraper,
    is_fal_document_url,
    is_fal_static_institutional,
    parse_fal_article_html,
    parse_fal_blog_listing_html,
    parse_fav_wp_edital_post,
    sanitize_fal_text,
)


# ============================================================================
# 10. HUB (Hospital Universitário de Brasília / Ebserh)
# ============================================================================


def test_hub_scraper_instance_contract():
    """Garante que HUBScraper segue o contrato de BaseScraper e está registrado."""
    assert isinstance(hub_scraper, BaseScraper)
    assert issubclass(HUBScraper, BaseScraper)
    assert hub_scraper.orgao_origem == "HUB"
    assert get_scraper("hub") is hub_scraper
    assert "HUB" in SCRAPERS_REGISTRY


def test_normalize_govbr_doc_url_and_detection():
    """Garante remoção do sufixo Plone '/view', suporte a Liferay /documents/d/ e guias PIC/PIT."""
    raw_pdf_view = (
        "https://www.gov.br/hubrasil/pt-br/acesso-a-informacao/concursos/"
        "2026/editais/edital-no-2-ebserh-nacional-area-medica.pdf/view"
    )
    assert normalize_govbr_doc_url(raw_pdf_view).endswith("edital-no-2-ebserh-nacional-area-medica.pdf")
    assert is_document_url(raw_pdf_view) is True

    raw_docx = "https://www.gov.br/hubrasil/pt-br/pic-ebserh/anexo_iv_pic2026.docx/view"
    assert normalize_govbr_doc_url(raw_docx).endswith("anexo_iv_pic2026.docx")
    assert is_document_url(raw_docx) is True

    liferay_doc = "https://www.fap.df.gov.br/documents/d/fapdf/edital-09_2025-fapdf-conecta-pdf"
    assert is_document_url(liferay_doc) is True

    guide_jpg = "https://www.gov.br/hubrasil/pt-br/pic-ebserh/pic_guia_orientador.jpg/@@images/image"
    assert is_document_url(guide_jpg) is True
    assert normalize_govbr_doc_url(guide_jpg).endswith("pic_guia_orientador.jpg")

    page_url = "https://www.gov.br/hubrasil/pt-br/hospitais-universitarios/regiao-centro-oeste/hub-unb"
    assert is_document_url(page_url) is False


def test_is_hub_relevant_pss_strict_hospital_filtering():
    """Garante que apenas PSS do HUB-UnB, Sede Brasília ou Rede Nacional são aceitos."""
    assert is_hub_relevant_pss(
        "PSS Nº 005/2026 - EBSERH/HUB - UNB",
        "https://www.gov.br/hubrasil/pt-br/pss/2026/pss-no-005-2026-ebserh-hub-unb",
    )
    assert is_hub_relevant_pss(
        "PSS Nº 002/2026 – HU Brasil/Nacional",
        "https://www.gov.br/hubrasil/pt-br/pss/2026/pss-ndeg-002-2026-hu-brasil-nacional",
    )
    assert is_hub_relevant_pss(
        "PSS 10/2023 - Região Centro Oeste - EBSERH/Sede",
        "https://www.gov.br/hubrasil/pt-br/pss/2023/pss-10-2023-regiao-centro-oeste-sede",
    )

    assert not is_hub_relevant_pss(
        "PSS Nº 001/2026 - EBSERH/HUPES-UFBA",
        "https://www.gov.br/hubrasil/pt-br/pss/2026/pss-no-001-2026-ebserh-hupes-ufba",
    )
    assert not is_hub_relevant_pss(
        "PSS Nº 014/2026 - HU Brasil/HC-UFG",
        "https://www.gov.br/hubrasil/pt-br/pss/2026/pss-no-014-2026-hu-brasil-hc-ufg",
    )
    assert not is_hub_relevant_pss(
        "PSS 01/2023 - Região Centro-Oeste - HU-UFGD",
        "https://www.gov.br/hubrasil/pt-br/pss/2023/pss-01-2023-regiao-centro-oeste-hu-ufgd",
    )


def test_classify_hub_edital_and_documents():
    """Testa a categorização de editais (ENARE, PIC, PIT, PSS, Concurso, Estágio, Saúde Digital, Agências)."""
    cat_res = classify_hub_edital("Exame Nacional de Residência (ENARE 2026) — COREME e COREMU HUB-UnB")
    assert "Residência Médica e Multiprofissional" in cat_res["tipo"]

    cat_coreme = classify_hub_edital("Residência Médica (COREME / ENARE 2026) — Seleção Unificada HUB-UnB")
    assert cat_coreme["tipo"] == "Residência Médica (COREME)"

    cat_coremu = classify_hub_edital("Residência Multiprofissional em Saúde (COREMU / ENARE 2026) — HUB-UnB")
    assert cat_coremu["tipo"] == "Residência Multiprofissional em Saúde (COREMU)"

    cat_ext = classify_hub_edital(
        "Fluxo Contínuo de Submissão — Atividades e Projetos de Extensão Universitária no HUB-UnB",
        url="https://www.gov.br/hubrasil/pt-br/hospitais-universitarios/regiao-centro-oeste/hub-unb/ensino-e-pesquisa/ensino/graduacao/extensao/sobre-a-extensao",
    )
    assert cat_ext["tipo"] == "Extensão Hospitalar e Universitária"

    cat_pic = classify_hub_edital("Programa de Iniciação Científica PIC/HUBRASIL HUB-UnB 2026")
    assert "Iniciação Científica em Saúde (PIC)" == cat_pic["tipo"]

    cat_pit = classify_hub_edital("Programa de Iniciação Tecnológica PIT/HUBRASIL HUB-UnB 2026")
    assert "Iniciação Tecnológica em Saúde (PIT)" == cat_pit["tipo"]

    cat_pss = classify_hub_edital("PSS Nº 005/2026 - EBSERH/HUB - UNB")
    assert "Processo Seletivo Simplificado (PSS)" == cat_pss["tipo"]

    cat_conc = classify_hub_edital("Concurso Público Nacional Ebserh/HUB-UnB — Edição 2026")
    assert "Concurso Público Efetivo" == cat_conc["tipo"]

    cat_est = classify_hub_edital("Programa de Estágio Ebserh/HUB-UnB — 2021")
    assert "Estágio Hospitalar" == cat_est["tipo"]

    cat_pesq = classify_hub_edital("Concurso de Inovação em Saúde Digital — HUB-UnB")
    assert "Pesquisa, Inovação e Saúde Digital" == cat_pesq["tipo"]

    assert classify_hub_document("Resultado definitivo - Edital nº 01/2026", "res_def.pdf") == "resultado_final"
    assert classify_hub_document("Resultado Definitivo dos Pedidos de Isenção da Taxa", "isencao.pdf") == "resultado_provisorio"
    assert classify_hub_document("Resultado Definitivo da Heteroidentificação", "hetero.pdf") == "resultado_provisorio"
    assert classify_hub_document("Resultado Preliminar da Homologação das Inscrições", "homolog_prelim.pdf") == "resultado_provisorio"
    assert classify_hub_document("Edital nº 03/2026 - Prorrogração das Inscrições", "edital_03.pdf") == "retificacao"
    assert classify_hub_document("Edital de abertura", "edital_01_2026_pic.pdf") == "original"


def test_extract_enare_fgv_rsc_publicacoes():
    """Garante extração de publicações do payload Next.js RSC do portal ENARE/FGV."""
    rsc_html = (
        '<script>self.__next_f.push([1,"5:[\\"$\\",\\"div\\",null,{\\"publicacoes\\":['
        '{\\"titulo\\":\\"Edital ENARE Nº 03/2026 - Residência Médica\\",\\"urlDocumento\\":\\"/docs/edital_med.pdf\\",'
        '\\"dataPublicacao\\":\\"2026-06-03\\",\\"tipoDocumento\\":\\"edital\\",\\"destinatarios\\":[\\"medica-acesso-direto\\"]},'
        '{\\"titulo\\":\\"Resultado da Prova Objetiva - Multiprofissional\\",\\"urlDocumento\\":\\"/docs/res_multi.pdf\\",'
        '\\"dataPublicacao\\":\\"2026-10-20\\",\\"tipoDocumento\\":\\"resultado\\",\\"destinatarios\\":[\\"multi-uniprofissional\\"]}'
        ']}]"])</script>'
    )
    pubs = extract_enare_fgv_publicacoes(rsc_html, base_url="https://enare2026.conhecimento.fgv.br/publicacoes/")
    assert len(pubs) == 2
    assert pubs[0]["link"] == "https://enare2026.conhecimento.fgv.br/docs/edital_med.pdf"
    assert pubs[0]["tipo"] == "original"
    assert "medica-acesso-direto" in pubs[0]["destinatarios"]
    assert pubs[1]["tipo"] == "resultado_provisorio"
    assert "multi-uniprofissional" in pubs[1]["destinatarios"]


def test_parse_hub_page_pic_pit_guides_and_plain_urls():
    """Verifica extração de abas Plone, PDFs /view, guias PIC/PIT, URLs em texto puro e link_inscricao."""
    tab_html = """
    <div id="content-core">
        <div class="tab-content" data-url="https://www.gov.br/hubrasil/pt-br/pic-ebserh/pic-ebserh">
            Aguarde. Carregando conteúdo da aba...
        </div>
    </div>
    """
    tabs = extract_plone_tab_urls(tab_html, "https://www.gov.br/hubrasil/pt-br/pic-ebserh")
    assert tabs == ["https://www.gov.br/hubrasil/pt-br/pic-ebserh/pic-ebserh"]

    edital_html = """
    <html>
      <body>
        <h1 class="documentFirstHeading">PIC/HU BRASIL/HUB-UnB 2026</h1>
        <span class="documentPublished">Publicado em 14/05/2026</span>
        <div id="content-core">
          <p>O Hospital Universitário de Brasília torna público o edital de seleção de bolsistas de Iniciação Científica.</p>
          <p>Período de inscrições: 14/05/2026 a 20/12/2026.</p>
          <a href="https://redcap.ebserh.gov.br/surveys/?s=PIC2026">Formulário de Inscrição REDCap</a>
          <a href="https://www.gov.br/hubrasil/pt-br/pic/edital_01_2026_pic.pdf/view">Edital de abertura, formato, pdf, 310kb</a>
          <a href="https://www.gov.br/hubrasil/pt-br/pic/resultado_preliminar_pic_2026.pdf">Resultado preliminar da análise dos projetos</a>
          <a href="https://www.gov.br/hubrasil/pt-br/pic/pic_guia_aluno.jpg/view">Guia de Inscrição para o Aluno</a>
          <p>Documento complementar em texto: https://cdt.unb.br/images/CDT/2025/fabrica_spinoff.pdf</p>
        </div>
      </body>
    </html>
    """
    parsed = parse_hub_page_as_edital(
        edital_html,
        "https://www.gov.br/hubrasil/pt-br/hospitais-universitarios/regiao-centro-oeste/hub-unb/pic-2026",
    )
    assert parsed["unidade"] == "HUB-UnB"
    assert parsed["ano"] == 2026
    assert parsed["data_publicacao"] == "14/05/2026"
    assert parsed["inicio_inscricao"] == "2026-05-14"
    assert parsed["fim_inscricao"] == "2026-12-20"
    assert parsed["link_inscricao"] == "https://redcap.ebserh.gov.br/surveys/?s=PIC2026"
    assert parsed["status"] == "aberto"
    assert parsed["tipo"] == "Iniciação Científica em Saúde (PIC)"
    assert len(parsed["documentos"]) == 4
    assert any(d["link"].endswith("pic_guia_aluno.jpg") for d in parsed["documentos"])
    assert any(d["link"].endswith("fabrica_spinoff.pdf") for d in parsed["documentos"])


def test_parse_ocean_unb_oportunidades_table():
    """Garante extração individualizada dos editais na tabela de 'Editais e oportunidades' do Ocean UnB no HUB."""
    html_table = """
    <div id="content-core">
      <table>
        <tr>
          <th>Edital</th>
          <th>Período de Inscrições</th>
          <th>Situação</th>
        </tr>
        <tr>
          <td><a href="https://pctec.unb.br/edital-de-selecao-publica-do-programa-de-residencia-tecnologica-em-saude-digital-ocean-unb-no-02-2026/">Edital de Seleção Pública do Programa de Residência Tecnológica em Saúde Digital - Ocean UnB - Nº 02/2026</a></td>
          <td>02/09/2026 a 25/09/2026</td>
          <td>Encerrado</td>
        </tr>
        <tr>
          <td><a href="https://pctec.unb.br/edital-de-selecao-de-bolsistas-para-compor-equipe-tic/">Edital de Seleção de Bolsistas para Compor Equipe TIC 53</a></td>
          <td>01/04/2025 a 15/04/2025</td>
          <td>Encerrado</td>
        </tr>
      </table>
    </div>
    """
    rows = parse_ocean_unb_oportunidades_table(
        html_table,
        "https://www.gov.br/hubrasil/pt-br/hospitais-universitarios/regiao-centro-oeste/hub-unb/ensino-e-pesquisa/pesquisa/projeto-residencia-em-tic-53-1/editais-e-oportunidades",
    )
    assert len(rows) == 2
    assert "Nº 02/2026" in rows[0]["titulo"]
    assert rows[0]["inicio_inscricao"] == "2026-09-02"
    assert rows[0]["fim_inscricao"] == "2026-09-25"
    assert rows[0]["status"] == "fechado"
    assert "pctec.unb.br" in rows[0]["link"]
    assert "Equipe TIC 53" in rows[1]["titulo"]
    assert rows[1]["ano"] == 2025


@patch("app.modules.scraper.hub.httpx.Client")
def test_hub_scraper_extracts_all_11_pesquisa_editais_subpages_mock(mock_client_cls):
    """Garante que TODAS as 11 subpáginas de pesquisa/editais (de Concurso de Inovação até NIH) são extraídas."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    subpages = [
        ("concurso-de-inovacao-em-saude-digital", "Concurso de Inovação em Saúde Digital"),
        ("rede-hu", "Rede HU+"),
        ("cnpq", "CNPq"),
        ("mulheres-na-ciencia", "Mulheres na Ciência"),
        ("fap-df", "FAP/DF"),
        ("finep", "FINEP"),
        ("capes", "CAPES"),
        ("editais-do-centro-de-apoio-ao-desenvolvimento-tecnologico-cdt-unb", "Editais do Centro de Apoio ao Desenvolvimento Tecnológico (CDT - UnB)"),
        ("proadi-sus", "PROADI-SUS"),
        ("oportunidades-de-financiamento-internacional-de-projetos-de-pd-i", "Oportunidades de Financiamento Internacional de projetos de PD&I"),
        ("nih", "NIH | National Institutes of Health"),
    ]
    base_editais = "https://www.gov.br/hubrasil/pt-br/hospitais-universitarios/regiao-centro-oeste/hub-unb/ensino-e-pesquisa/pesquisa/editais"
    links_html = "".join(
        f'<a href="{base_editais}/{slug}">{label}</a>' for slug, label in subpages
    )

    def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.url = url
        u = url.rstrip("/")
        if u == base_editais:
            resp.status_code = 200
            resp.text = f'<div id="content-core">{links_html}</div>'
            return resp
        for slug, label in subpages:
            if u.endswith(f"/pesquisa/editais/{slug}"):
                resp.status_code = 200
                extra = ""
                if slug == "fap-df":
                    extra = '<a href="https://www.fap.df.gov.br/documents/d/fapdf/edital-conecta-pdf">Edital FAPDF Conecta</a>'
                elif slug == "nih":
                    extra = '<a href="https://grants.nih.gov/grants/guide/index.html">Portal de Chamadas NIH</a>'
                resp.text = (
                    f'<h1 class="documentFirstHeading">{label}</h1>'
                    f'<span class="documentPublished">Publicado em 10/03/2026</span>'
                    f'<div id="content-core"><p>Chamadas e fomento de PD&I aplicáveis a pesquisadores do HUB-UnB ({label}).</p>{extra}</div>'
                )
                return resp
        resp.status_code = 404
        resp.text = ""
        return resp

    mock_client.get.side_effect = fake_get
    scraper = HUBScraper()
    editais = scraper.fetch_editais(year=2026, max_pss_years=0)
    urls_coletadas = {e["link"].rstrip("/") for e in editais}
    for slug, _ in subpages:
        assert f"{base_editais}/{slug}" in urls_coletadas

    fap_item = next(e for e in editais if e["link"].endswith("/fap-df"))
    assert len(fap_item["documentos"]) == 1
    assert "fap.df.gov.br/documents/d/" in fap_item["documentos"][0]["link"]


@patch("app.modules.scraper.hub.httpx.Client")
def test_hub_scraper_fetch_editais_and_docs_mock(mock_client_cls):
    """Testa coleta ponta a ponta do HUBScraper com abas Plone e subpastas de PSS mockadas."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    responses = {
        "pic-ebserh": (
            '<div id="content-core"><div data-url="https://www.gov.br/hubrasil/pt-br/hospitais-universitarios/regiao-centro-oeste/hub-unb/ensino-e-pesquisa/pesquisa/pic-ebserh/aba"></div></div>'
        ),
        "pic-ebserh/aba": (
            '<div id="content-core"><a href="https://www.gov.br/hubrasil/pt-br/hospitais-universitarios/regiao-centro-oeste/hub-unb/ensino-e-pesquisa/pesquisa/pic-ebserh/pic-2026">Edição PIC 2026</a></div>'
        ),
        "pic-ebserh/pic-2026": (
            '<h1 class="documentFirstHeading">PIC HUB-UnB 2026</h1>'
            '<div id="content-core"><p>Seleção de bolsistas de iniciação científica no Hospital Universitário de Brasília.</p>'
            '<a href="https://www.gov.br/hubrasil/pt-br/pic/edital_pic_2026.pdf/view">Edital Nº 01/2026</a></div>'
        ),
        "processo-seletivo-simplificado-pss/2026": (
            '<div id="content-core">'
            '<a href="https://www.gov.br/hubrasil/pt-br/acesso-a-informacao/agentes-publicos/concursos-e-selecoes/selecoes/processos-seletivos/processo-seletivo-simplificado-pss/2026/pss-001-ufba">PSS Nº 001/2026 - EBSERH/HUPES-UFBA</a>'
            '<a href="https://www.gov.br/hubrasil/pt-br/acesso-a-informacao/agentes-publicos/concursos-e-selecoes/selecoes/processos-seletivos/processo-seletivo-simplificado-pss/2026/pss-005-hub-unb">PSS Nº 005/2026 - EBSERH/HUB - UNB</a>'
            "</div>"
        ),
        "pss-005-hub-unb": (
            '<h1 class="documentFirstHeading">PSS Nº 005/2026 - EBSERH/HUB - UNB</h1>'
            '<div id="content-core"><a href="https://www.gov.br/hubrasil/pt-br/pss/2026/pss-005-hub-unb/edital-normativo">Edital Normativo</a></div>'
        ),
        "pss-005-hub-unb/edital-normativo": (
            '<div id="content-core"><a href="https://www.gov.br/hubrasil/pt-br/pss/2026/edital_pss_005_2026.pdf/view">Edital Normativo PSS 005/2026</a></div>'
        ),
    }

    def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.url = url
        for key, html in responses.items():
            if url.rstrip("/").endswith(key):
                resp.status_code = 200
                resp.text = html
                return resp
        resp.status_code = 404
        resp.text = ""
        return resp

    mock_client.get.side_effect = fake_get

    scraper = HUBScraper()
    editais = scraper.fetch_editais(year=2026, max_pss_years=1)
    titles = [e["titulo"] for e in editais]
    assert any("Edição PIC 2026" in t for t in titles)
    assert any("PSS Nº 005/2026 - EBSERH/HUB - UNB" in t for t in titles)
    assert not any("UFBA" in t for t in titles)

    pss_edital = next(e for e in editais if "PSS Nº 005/2026" in e["titulo"])
    assert len(pss_edital["documentos"]) == 1
    assert pss_edital["documentos"][0]["link"].endswith("edital_pss_005_2026.pdf")


@patch("app.modules.scraper.hub.httpx.Client")
def test_hub_scraper_concursos_child_hospital_filtering(mock_client_cls):
    """Garante captura de Concursos Nacionais aninhados (2023) e exclusão de concursos de outros HUs (ex: HU-UNIFAP 2022)."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    responses = {
        "concursos/2023": (
            '<div id="content-core">'
            '<a href="https://www.gov.br/hubrasil/pt-br/acesso-a-informacao/agentes-publicos/concursos-e-selecoes/concursos/2023/concurso-no-01-2023-ebserh-nacional">Concurso Nº 01/2023-EBSERH/NACIONAL</a>'
            "</div>"
        ),
        "concurso-no-01-2023-ebserh-nacional": (
            '<h1 class="documentFirstHeading">Concurso Nº 01/2023-EBSERH/NACIONAL</h1>'
            '<div id="content-core">'
            '<a href="https://www.gov.br/hubrasil/pt-br/concursos/2023/concurso-no-01-2023-ebserh-nacional/editais-normativos">Editais Normativos</a>'
            "</div>"
        ),
        "concurso-no-01-2023-ebserh-nacional/editais-normativos": (
            '<div id="content-core"><a href="https://www.gov.br/hubrasil/pt-br/concursos/2023/edital_01_2023_nacional.pdf/view">Edital Normativo 01/2023</a></div>'
        ),
        "concursos/2022": (
            '<div id="content-core">'
            '<a href="https://www.gov.br/hubrasil/pt-br/acesso-a-informacao/agentes-publicos/concursos-e-selecoes/concursos/2022/concurso-no-1-2022-ebserh-hu-unifap">Concurso nº 1/2022 - EBSERH/ HU-UNIFAP</a>'
            "</div>"
        ),
    }

    def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.url = url
        for key, html in responses.items():
            if url.rstrip("/").endswith(key):
                resp.status_code = 200
                resp.text = html
                return resp
        resp.status_code = 404
        resp.text = ""
        return resp

    mock_client.get.side_effect = fake_get
    scraper = HUBScraper()
    editais = scraper.fetch_editais()
    titles = [e["titulo"] for e in editais]
    assert any("Concurso Nº 01/2023-EBSERH/NACIONAL" in t for t in titles)
    assert not any("UNIFAP" in t or "Edição 2022" in t for t in titles)
    conc_2023 = next(e for e in editais if "Concurso Nº 01/2023" in e["titulo"])
    assert len(conc_2023["documentos"]) == 1


@patch("app.modules.scraper.hub.httpx.Client")
def test_hub_scraper_network_failure(mock_client_cls):
    """Garante resiliência em falhas de rede no HUBScraper."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_client.get.side_effect = httpx.ConnectTimeout("Timeout no Gov.br")

    scraper = HUBScraper()
    assert scraper.fetch_editais(max_pss_years=1) == []
    assert scraper.fetch_documentos("https://www.gov.br/hubrasil/pt-br/invalido") == []


# ============================================================================
# 11. FAL (Fazenda Água Limpa da UnB)
# ============================================================================


def test_fal_scraper_instance_contract():
    """Garante que FALScraper segue o contrato de BaseScraper e está registrado."""
    assert isinstance(fal_scraper, BaseScraper)
    assert issubclass(FALScraper, BaseScraper)
    assert fal_scraper.orgao_origem == "FAL"
    assert get_scraper("fal") is fal_scraper
    assert "FAL" in SCRAPERS_REGISTRY


def test_fal_institutional_filter_and_spam_sanitization():
    """Garante exclusão de páginas institucionais estáticas e limpeza de spam externo."""
    assert is_fal_static_institutional("Histórico", "/index.php?option=com_content&view=article&id=3:historico")
    assert is_fal_static_institutional("Restaurante Universitário", "/index.php?id=16:restaurante-universitario")
    assert is_fal_static_institutional("SUA DOAÇÃO FAZ A DIFERENÇA!", "/index.php?id=75:faca-sua-doacao")
    assert is_fal_static_institutional(".", "/index.php?id=61:projetos")

    assert not is_fal_static_institutional(
        "Laboratório de Produção de Suínos - LABSUI",
        "/index.php?option=com_content&view=article&id=81:labsui&catid=2",
    )
    assert not is_fal_static_institutional(
        "Cadastro de Projetos",
        "/index.php?option=com_content&view=article&id=33:cadastros-de-projetos&catid=2",
    )
    assert not is_fal_static_institutional(
        "Iniciação científica",
        "/index.php?option=com_content&view=article&id=73:iniciacao-cientifica-2&catid=2",
    )

    dirty_text = (
        "O Laboratório de Produção de Suínos recebe estudantes para estágio prático. "
        "Confira também casinos online Portugal para jogar agora. "
        "As atividades envolvem manejo nutricional e reprodutivo."
    )
    cleaned = sanitize_fal_text(dirty_text)
    assert "casinos online" not in cleaned.lower()
    assert "Laboratório de Produção de Suínos" in cleaned
    assert "manejo nutricional" in cleaned
    assert sanitize_fal_text("Produc\u0327a\u0303o Agri\u0301cola") == "Produção Agrícola"


def test_classify_fal_edital_and_area_detection():
    """Testa classificação por tipo e área temática da Fazenda Água Limpa."""
    cat_estagio = classify_fal_edital(
        "Laboratório de Produção de Suínos - LABSUI",
        texto="Oportunidade de estágio prático para Medicina Veterinária e Agronomia.",
    )
    assert cat_estagio["tipo"] == "Estágio e Prática Profissional em Campo"
    assert cat_estagio["area"] == "Medicina Veterinária e Produção Animal"
    assert cat_estagio["fluxo_continuo"] == "sim"

    cat_cad = classify_fal_edital(
        "Cadastro de Projetos — FAL/UnB",
        url="https://fal.unb.br/index.php?id=33:cadastros-de-projetos",
    )
    assert cat_cad["tipo"] == "Submissão e Cadastro de Projetos de Campo"
    assert cat_cad["fluxo_continuo"] == "sim"

    cat_ext = classify_fal_edital(
        "Projeto Beija FAL — FAL/UnB",
        texto="Ecoturismo científico e conservação florestal no Cerrado.",
    )
    assert cat_ext["tipo"] == "Extensão Rural e Educação Ambiental"
    assert cat_ext["area"] == "Engenharia Florestal e Conservação Ambiental"

    assert detect_fal_area("Laboratório de Hidráulica Agrícola") == "Agronomia e Ciências Agrárias"
    assert classify_fal_document("Regulamento de Estágio Obrigatório", "regulamento.pdf") == "original"


def test_parse_fal_blog_and_article_enrichment():
    """Garante extração de datas no cabeçalho Joomla e enriquecimento de títulos genéricos."""
    blog_html = """
    <div class="blog">
        <h2>19 de Outubro de 2020</h2>
        <div class="items-row">
            <h2><a href="/index.php?option=com_content&view=article&id=73:iniciacao-cientifica-2&catid=2">Iniciação científica</a></h2>
        </div>
        <h2>17 de Abril de 2017</h2>
        <div class="items-row">
            <h2><a href="/index.php?option=com_content&view=article&id=18:missao&catid=2">Missão</a></h2>
        </div>
    </div>
    """
    listing = parse_fal_blog_listing_html(blog_html)
    assert len(listing) == 1
    assert listing[0]["titulo"] == "Iniciação científica"
    assert listing[0]["header_date"] == "19 de Outubro de 2020"

    article_html = """
    <div class="item-page">
        <div itemprop="articleBody">
            <p>Título do projeto: Dinâmica regenerativa de espécies nativas do Cerrado após manejo florestal.</p>
            <p>Coordenação: Departamento de Engenharia Florestal da Universidade de Brasília.</p>
            <p><a href="https://sigaa.unb.br/sigaa/public/extensao">Inscreva-se via SIGAA</a></p>
            <p><a href="https://fal.unb.br/arquivos/plano_trabalho_ic.pdf">Plano de Trabalho PDF</a></p>
            <p><a href="https://spam-bet-example.com/casino">casinos online</a></p>
        </div>
    </div>
    """
    parsed = parse_fal_article_html(
        article_html,
        "https://fal.unb.br/index.php?option=com_content&view=article&id=73:iniciacao-cientifica-2&catid=2",
        default_title="Iniciação científica",
        header_date="19 de Outubro de 2020",
    )
    assert "Iniciação científica na FAL/UnB — Dinâmica regenerativa" in parsed["titulo"]
    assert parsed["unidade"] == "FAL"
    assert parsed["campus"] == "Fazenda Água Limpa"
    assert parsed["data_publicacao"] == "19/10/2020"
    assert parsed["ano"] == 2020
    assert parsed["status"] == "fechado"
    assert parsed["link_inscricao"] == "https://sigaa.unb.br/sigaa/public/extensao"
    assert len(parsed["documentos"]) == 1
    assert parsed["documentos"][0]["link"] == "https://fal.unb.br/arquivos/plano_trabalho_ic.pdf"


@patch("app.modules.scraper.fal.httpx.Client")
def test_fal_scraper_fetch_editais_and_docs_mock(mock_client_cls):
    """Testa o fluxo completo de coleta do FALScraper com respostas HTTP simuladas."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    blog_page_0 = """
    <div class="blog">
        <h2>19 de Maio de 2022</h2>
        <h2><a href="/index.php?option=com_content&view=article&id=81:labsui&catid=2">Laboratório de Produção de Suínos - LABSUI</a></h2>
    </div>
    """
    article_labsui = """
    <div itemprop="articleBody">
        <p>O LABSUI oferece oportunidades permanentes de estágio e aulas práticas em suinocultura na Fazenda Água Limpa.</p>
    </div>
    """
    fav_estagio_html = """
    <div class="entry-content">
        <p>Orientações e fluxo contínuo para formalização de Termo de Compromisso de Estágio (TCE) via SIGAA.</p>
        <a href="https://fav.unb.br/images/Documentos/Agronomia/regulamento_de_estagio_obrigatorio_-_agronomia.pdf">Regulamento de Estágio Obrigatório</a>
    </div>
    """

    def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.url = url
        resp.status_code = 200
        if "limitstart=0" in url:
            resp.text = blog_page_0
        elif "limitstart=" in url:
            resp.text = '<div class="blog"></div>'
        elif "id=81:labsui" in url:
            resp.text = article_labsui
        elif "fav.unb.br/estagio" in url:
            resp.text = fav_estagio_html
        else:
            resp.status_code = 404
            resp.text = ""
        return resp

    mock_client.get.side_effect = fake_get

    scraper = FALScraper()
    editais = scraper.fetch_editais()
    assert len(editais) == 2
    assert any("LABSUI" in e["titulo"] for e in editais)
    assert any("FAV/FAL" in e["titulo"] for e in editais)

    for ed in editais:
        assert ed["status"] == "aberto"
        assert ed["assunto"]

    docs = scraper.fetch_documentos("https://fav.unb.br/estagio/")
    assert len(docs) == 1
    assert docs[0]["link"].endswith(".pdf")


def test_fal_fav_wp_api_and_phocadownload_parsing():
    """Garante parse de editais WordPress FAV/FAL, enriquecimento de título genérico e suporte a PhocaDownload."""
    phoca_url = "https://fal.unb.br/index.php?option=com_phocadownload&view=file&id=12:termo-de-compromisso"
    assert is_fal_document_url(phoca_url) is True

    trunc_html = (
        '<div class="entry-content">'
        '<a href="https://fav.unb.br/doc/reg_estagio.pdf">REGULAMENTO DE ESTÁGIO OBRIGATÓRI</a>'
        '<a href="https://fal.unb.br/index.php?option=com_phocadownload&view=file&id=12:termo-de-compromisso">Clique aqui</a>'
        "</div>"
    )
    trunc_parsed = parse_fal_article_html(trunc_html, "https://fav.unb.br/estagio/")
    assert len(trunc_parsed["documentos"]) == 2
    assert trunc_parsed["documentos"][0]["titulo"] == "Regulamento de Estágio Obrigatório"
    assert trunc_parsed["documentos"][1]["titulo"] == "Termo De Compromisso"

    marca_post = {
        "date": "2026-05-08T10:15:00",
        "link": "https://fav.unb.br/acesse-aqui-o-edital/",
        "title": {"rendered": "Acesse aqui o Edital"},
        "content": {
            "rendered": (
                "<p>Seleção de estudantes de Agronomia para mobilidade regional.</p>"
                '<p><a href="https://fav.unb.br/wp-content/uploads/2026/05/Edital-010-2026-FAV-MARCA.pdf">'
                "EDITAL FAV/MARCA N°010/2026</a></p>"
            )
        },
    }
    parsed_marca = parse_fav_wp_edital_post(marca_post)
    assert parsed_marca is not None
    assert "EDITAL FAV/MARCA N°010/2026" in parsed_marca["titulo"]
    assert parsed_marca["tipo"] == "Ensino e Mobilidade Acadêmica em Ciências Agrárias"
    assert parsed_marca["data_publicacao"] == "08/05/2026"
    assert len(parsed_marca["documentos"]) == 1

    saude_animal_post = {
        "date": "2026-11-04T09:00:00",
        "link": "https://fav.unb.br/edital-01-2026-mestrado-e-doutorado-em-saude-animal/",
        "title": {"rendered": "Edital 01/2026: Mestrado e Doutorado em Saúde Animal!"},
        "content": {
            "rendered": (
                "<p>O Programa de Pós-Graduação em Saúde Animal publica edital de seleção 2026.</p>"
                '<p><a href="https://saudeanimal.unb.br/processo-seletivo">Página de Inscrição</a></p>'
            )
        },
    }
    parsed_sa = parse_fav_wp_edital_post(saude_animal_post)
    assert parsed_sa is not None
    assert parsed_sa["area"] == "Medicina Veterinária e Produção Animal"
    assert parsed_sa["link_inscricao"] == "https://saudeanimal.unb.br/processo-seletivo"

    unrelated_post = {
        "date": "2026-08-10T14:00:00",
        "link": "https://fav.unb.br/homenagem-aos-docentes/",
        "title": {"rendered": "Homenagem aos Docentes da FAV"},
        "content": {"rendered": "<p>Solenidade realizada no auditório com menção a edital histórico.</p>"},
    }
    assert parse_fav_wp_edital_post(unrelated_post) is None


@patch("app.modules.scraper.fal.httpx.Client")
def test_fal_scraper_network_failure(mock_client_cls):
    """Garante resiliência em falhas de rede no FALScraper."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_client.get.side_effect = httpx.ConnectError("Servidor FAL indisponível")

    scraper = FALScraper()
    assert scraper.fetch_editais() == []
    assert scraper.fetch_documentos("https://fal.unb.br/artigo") == []


# ============================================================================
# Testes ao Vivo (Live Connectivity)
# ============================================================================


@pytest.mark.live
def test_hub_live_connectivity():
    """Teste ao vivo no portal oficial do HUB-UnB / Ebserh (Gov.br)."""
    scraper = HUBScraper(timeout=10.0)
    editais = scraper.fetch_editais(max_pss_years=1)
    assert isinstance(editais, list)
    if editais:
        assert editais[0]["titulo"]
        assert editais[0]["assunto"]
        assert "HUB-UnB" in editais[0]["unidade"]


@pytest.mark.live
def test_fal_live_connectivity():
    """Teste ao vivo no portal oficial da Fazenda Água Limpa (FAL/UnB)."""
    scraper = FALScraper(timeout=10.0)
    editais = scraper.fetch_editais(max_pages=1)
    assert isinstance(editais, list)
    if editais:
        assert editais[0]["titulo"]
        assert editais[0]["assunto"]
        assert editais[0]["unidade"] == "FAL"

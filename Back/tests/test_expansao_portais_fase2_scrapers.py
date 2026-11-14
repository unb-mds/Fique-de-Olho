"""
Testes unitários (com mocks HTTP) e de integração para os 6 scrapers da Fase 2
da Issue #84 (portais 16 a 21):
16. FUP (`FUPScraper` / `"FUP"`)
17. FACE (`FACEScraper` / `"FACE"`)
18. DIREITO (`DireitoScraper` / `"DIREITO"`)
19. DAF / SIPAC (`DAFScraper` / `"DAF"`)
20. PRC (`PRCScraper` / `"PRC"`)
21. DOU (`DOUScraper` / `"DOU"`)
"""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, Edital
from app.modules.scraper import (
    DAFScraper,
    DOUScraper,
    DireitoScraper,
    FACEScraper,
    FUPScraper,
    PPGContScraper,
    PPGGIPPScraper,
    PRCScraper,
    SCRAPERS_REGISTRY,
    daf_scraper,
    direito_scraper,
    dou_scraper,
    face_scraper,
    fup_scraper,
    get_scraper,
    ppgcont_scraper,
    ppggipp_scraper,
    prc_scraper,
    run_periodic_pipeline,
)
from app.modules.scraper.service import sync_all_portais


# ==============================================================================
# 0. Registro Centralizado (`SCRAPERS_REGISTRY` e `get_scraper`)
# ==============================================================================


def test_fase2_scrapers_registered_in_registry():
    """Verifica se os 8 novos scrapers (6 da Issue #84 + PPGCONT e PPGGIPP) estão registrados."""
    expected = {
        "FUP": (FUPScraper, fup_scraper),
        "FACE": (FACEScraper, face_scraper),
        "DIREITO": (DireitoScraper, direito_scraper),
        "DAF": (DAFScraper, daf_scraper),
        "PRC": (PRCScraper, prc_scraper),
        "DOU": (DOUScraper, dou_scraper),
        "PPGCONT": (PPGContScraper, ppgcont_scraper),
        "PPGGIPP": (PPGGIPPScraper, ppggipp_scraper),
    }

    assert len(SCRAPERS_REGISTRY) >= 33

    for key, (cls, singleton) in expected.items():
        assert key in SCRAPERS_REGISTRY
        scraper = get_scraper(key)
        assert scraper is singleton
        assert isinstance(scraper, cls)
        assert scraper.orgao_origem == key
        assert get_scraper(f"  {key.lower()} ") is singleton

    assert get_scraper("PPGIPP") is ppggipp_scraper
    assert get_scraper("ppgipp") is ppggipp_scraper


# ==============================================================================
# 16. FUP (`FUPScraper`)
# ==============================================================================


@patch("app.modules.scraper.fup.httpx.Client")
def test_fup_fetch_editais_and_year_filter_mock(mock_client_cls):
    """Valida a coleta combinada (WP API + HTML Grid + Fomento/PIBEX), campus Planaltina e filtro por ano na FUP."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    wp_cat_resp = MagicMock()
    wp_cat_resp.status_code = 200
    wp_cat_resp.json.return_value = [
        {
            "id": 15511,
            "date": "2026-10-20T10:00:00",
            "slug": "resultado-final-edital-no-005-2026",
            "link": "https://fup.unb.br/resultado-final-edital-no-005-2026/",
            "title": {
                "rendered": "RESULTADO FINAL - EDITAL Nº 005/2026 | APOIO À PARTICIPAÇÃO DE ESTUDANTES EM EVENTOS"
            },
            "excerpt": {"rendered": "<p>Resultado final do auxílio a eventos da FUP.</p>"},
            "content": {
                "rendered": """
                <div class="entry-content">
                    <p>Inscrições de 01/09/2026 a 15/09/2026.</p>
                    <a href="https://fup.unb.br/wp-content/uploads/2026/09/Edital_005_2026_FUP.pdf">Edital de Abertura</a>
                    <a href="https://fup.unb.br/wp-content/uploads/2026/10/Resultado_Final_005_2026.pdf">Resultado Final</a>
                    <a href="https://fup.unb.br/wp-content/uploads/2024/02/Regimento_Interno_FUP.pdf">Regimento Interno</a>
                </div>
                """
            },
        }
    ]

    wp_search_resp = MagicMock()
    wp_search_resp.status_code = 200
    wp_search_resp.json.return_value = [
        {
            "id": 14900,
            "date": "2026-06-12T12:00:00",
            "slug": "selecao-de-bolsistas-fup-de-bracos-abertos",
            "link": "https://fup.unb.br/selecao-de-bolsistas-fup-de-bracos-abertos/",
            "title": {"rendered": "Edital para Seleção de Bolsistas – Projeto FUP DE BRAÇOS ABERTOS"},
            "excerpt": {"rendered": "<p>Seleção de bolsistas de extensão FUP de Braços Abertos 2025/2026.</p>"},
            "content": {
                "rendered": """
                <p>Confira o edital: <a href="https://drive.google.com/file/d/1tCrChthDP-LshXWM86kWksmDYs2Qj0rh/view?usp=sharing">EDITAL</a></p>
                """
            },
        }
    ]

    html_grid_resp = MagicMock()
    html_grid_resp.status_code = 200
    html_grid_resp.text = """
    <html><body>
      <div class="jet-listing-grid__item">
        <h4><a href="https://fup.unb.br/edital-monitoria-2025/">Edital de Monitoria FUP 01/2025</a></h4>
        <p>Publicado em 10/03/2025</p>
      </div>
    </body></html>
    """

    fomento_resp = MagicMock()
    fomento_resp.status_code = 200
    fomento_resp.text = """
    <html><body><main>
      <p><a href="https://drive.google.com/file/d/1lJEkymFM3hHLoBOl3epeaX1Uj88Pqs7D/view?usp=sharing">
        EDITAL FUP Nº 006/2026 | MULHERES PESQUISADORAS
      </a></p>
      <p><a href="https://drive.google.com/file/d/1NfRG79CCUBiNPcqQv1S_m90D5f0XM8R1/view?usp=sharing">
        Resultado Provisório: Aqui
      </a></p>
      <p><a href="https://drive.google.com/file/d/1_Hh3Uq8lEpqFgE4mxykdF3Y72tSWoSSQ/view?usp=sharing">
        Resultado Final: Aqui
      </a></p>
    </main></body></html>
    """

    pibex_resp = MagicMock()
    pibex_resp.status_code = 200
    pibex_resp.text = "<html><body><main></main></body></html>"

    mock_client.get.side_effect = [
        wp_cat_resp,
        wp_search_resp,
        html_grid_resp,
        fomento_resp,
        pibex_resp,
    ]

    scraper = FUPScraper()
    all_editais = scraper.fetch_editais()

    assert len(all_editais) == 4
    assert all(ed["orgao_origem"] == "FUP" for ed in all_editais)
    assert all(ed["campus"] == "Planaltina" for ed in all_editais)

    ed_005 = next(ed for ed in all_editais if "005/2026" in ed["titulo"])
    assert ed_005["inicio_inscricao"] == "2026-09-01"
    assert ed_005["fim_inscricao"] == "2026-09-15"
    assert ed_005["status"] == "fechado"
    # O Regimento Interno do rodapé deve ter sido filtrado
    assert len(ed_005["documentos"]) == 2
    tipos_005 = {d["tipo_documento"] for d in ed_005["documentos"]}
    assert "original" in tipos_005
    assert "resultado_final" in tipos_005

    ed_006 = next(ed for ed in all_editais if "006/2026" in ed["titulo"])
    assert len(ed_006["documentos"]) == 3
    tipos_006 = {d["tipo_documento"] for d in ed_006["documentos"]}
    assert {"original", "resultado_provisorio", "resultado_final"} == tipos_006

    # Testa filtro por ano
    scraper.clear_cache()
    mock_client.get.side_effect = [
        wp_cat_resp,
        wp_search_resp,
        html_grid_resp,
        fomento_resp,
        pibex_resp,
    ]
    editais_2025 = scraper.fetch_editais(year=2025)
    assert len(editais_2025) == 1
    assert "01/2025" in editais_2025[0]["titulo"]


@patch("app.modules.scraper.fup.httpx.Client")
def test_fup_fetch_documentos_and_error_resilience(mock_client_cls):
    """Valida fetch_documentos e resiliência a falhas HTTP (500/timeout) na FUP."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    detail_resp = MagicMock()
    detail_resp.status_code = 200
    detail_resp.text = """
    <div class="entry-content">
      <a href="https://fup.unb.br/wp-content/uploads/2026/05/Edital_Abertura.pdf">Edital de Abertura</a>
      <a href="https://fup.unb.br/wp-content/uploads/2026/05/Retificacao_01.pdf">Retificação 01</a>
    </div>
    """
    mock_client.get.return_value = detail_resp

    scraper = FUPScraper()
    docs = scraper.fetch_documentos("https://fup.unb.br/edital-teste/")
    assert len(docs) == 2
    assert docs[0]["tipo_documento"] == "original"
    assert docs[1]["tipo_documento"] == "retificacao"

    # Simula falha HTTP / Timeout em fetch_editais
    scraper.clear_cache()
    mock_client.get.side_effect = httpx.TimeoutException("Timeout FUP")
    assert scraper.fetch_editais() == []


# ==============================================================================
# 17. FACE (`FACEScraper`)
# ==============================================================================


@patch("app.modules.scraper.face.httpx.Client")
def test_face_fetch_editais_semantic_filter_mock(mock_client_cls):
    """Valida que o FACEScraper captura editais reais e descarta notícias irrelevantes (memoriais/atas)."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    resp_editais_page = MagicMock()
    resp_editais_page.status_code = 200
    resp_editais_page.text = """
    <html><body><main>
      <p><a href="https://face.unb.br/wp-content/uploads/2026/08/Edital-FACE-01_2026-_SEI_14685226.pdf">
        EDITAL / FACE / DIREÇÃO Nº 01/2026
      </a></p>
      <p><a href="https://face.unb.br/wp-content/uploads/2026/09/Resultado-Preliminar-FACE-01-2026.pdf">
        Resultado Preliminar - Edital 01/2026
      </a></p>
    </main></body></html>
    """

    resp_extensao = MagicMock(status_code=200, text="<html><body></body></html>")
    resp_noticias = MagicMock(status_code=200, text="<html><body></body></html>")

    resp_wp_posts = MagicMock()
    resp_wp_posts.status_code = 200
    resp_wp_posts.json.return_value = [
        {
            "id": 9101,
            "date": "2026-08-19T10:00:00",
            "slug": "defesa-de-memorial-prof-joao",
            "link": "https://face.unb.br/defesa-de-memorial-prof-joao/",
            "title": {"rendered": "Defesa de Memorial - Prof. João"},
            "excerpt": {"rendered": "<p>Convidamos para a defesa de memorial para promoção a titular.</p>"},
            "content": {"rendered": "<p>Defesa pública de memorial.</p>"},
        },
        {
            "id": 9102,
            "date": "2025-11-10T10:00:00",
            "slug": "edital-monitoria-face-2025",
            "link": "https://face.unb.br/edital-monitoria-face-2025/",
            "title": {"rendered": "Edital de Monitoria e Seleção de Bolsistas FACE 02/2025"},
            "excerpt": {"rendered": "<p>Seleção de monitores da FACE.</p>"},
            "content": {
                "rendered": """
                <p>Inscrições de 10/11/2025 a 20/11/2025.</p>
                <a href="https://face.unb.br/wp-content/uploads/2025/11/Edital_Monitoria_02_2025.pdf">Baixar Edital</a>
                """
            },
        },
    ]

    resp_wp_pages = MagicMock(status_code=200)
    resp_wp_pages.json.return_value = []

    resp_wp_media = MagicMock(status_code=200)
    resp_wp_media.json.return_value = []

    mock_client.get.side_effect = [
        resp_editais_page,
        resp_extensao,
        resp_noticias,
        resp_wp_posts,
        resp_wp_pages,
        resp_wp_media,
    ]

    scraper = FACEScraper(max_pages=1)
    editais = scraper.fetch_editais()

    assert len(editais) == 2
    assert not any("Memorial" in ed["titulo"] for ed in editais)

    ed_dir = next(ed for ed in editais if "01/2026" in ed["titulo"])
    assert ed_dir["orgao_origem"] == "FACE"
    assert ed_dir["campus"] == "Darcy Ribeiro"
    assert len(ed_dir["documentos"]) == 2
    assert {d["tipo_documento"] for d in ed_dir["documentos"]} == {"original", "resultado_provisorio"}

    ed_mon = next(ed for ed in editais if "02/2025" in ed["titulo"])
    assert ed_mon["categoria"] == "Monitoria"
    assert ed_mon["inicio_inscricao"] == "2025-11-10"
    assert ed_mon["fim_inscricao"] == "2025-11-20"


# ==============================================================================
# 18. DIREITO (`DireitoScraper`)
# ==============================================================================


@patch("app.modules.scraper.direito.httpx.Client")
def test_direito_fetch_editais_sections_and_grouping_mock(mock_client_cls):
    """Valida a coleta nas seções de Editais, Monitoria, Grupos de Pesquisa e NPJ da Faculdade de Direito."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    resp_editais = MagicMock(status_code=200)
    resp_editais.text = """
    <html><body><main>
      <a href="https://direito.unb.br/wp-content/uploads/2026/10/SEI_15017462_Edital_001_2026.pdf">
        Edital Nº 01/2026 – PROCESSO SELETIVO SIMPLIFICADO
      </a>
      <a href="https://direito.unb.br/wp-content/uploads/2026/11/Resultado-Provisorio.pdf">
        Edital Nº 01/2026 – RESULTADO PROVISÓRIO DO PROCESSO SELETIVO SIMPLIFICADO
      </a>
      <a href="https://direito.unb.br/wp-content/uploads/2026/11/Edital-de-Resultado-Final.pdf">
        Edital N° 01/2026 – RESULTADO FINAL DO PROCESSO SELETIVO SIMPLIFICADO
      </a>
    </main></body></html>
    """

    resp_monitoria = MagicMock(status_code=200)
    resp_monitoria.text = """
    <html><body><main>
      <a href="https://direito.unb.br/wp-content/uploads/2026/08/EDITAL-DE-MONITORIA-DE-GRADUACAO-2026-2.pdf">
        EDITAL DE MONITORIA DE GRADUAÇÃO 2026-2
      </a>
      <a href="https://direito.unb.br/wp-content/uploads/2026/09/RESULTADO-DA-MONITORIA-DE-GRADUACAO-2026.2-FD.pdf">
        RESULTADO DA MONITORIA DE GRADUAÇÃO 2026.2 FD
      </a>
      <a href="https://direito.unb.br/wp-content/uploads/2023/12/resolucao_monitoria_08_1990.pdf">
        Resolução Monitoria 1990
      </a>
    </main></body></html>
    """

    resp_pesquisa = MagicMock(status_code=200)
    resp_pesquisa.text = """
    <html><body><main>
      <a href="https://direito.unb.br/wp-content/uploads/2024/03/JURAPP-Edital.pdf">
        JURAPP – Edital de Seleção Grupo de Pesquisa
      </a>
    </main></body></html>
    """

    empty_page = MagicMock(status_code=200, text="<html><body></body></html>")
    empty_api = MagicMock(status_code=200)
    empty_api.json.return_value = []

    mock_client.get.side_effect = [
        resp_editais,
        resp_monitoria,
        resp_pesquisa,
        empty_page,  # extensao
        empty_page,  # pet
        empty_page,  # npj
        empty_page,  # pibic
        empty_api,   # wp posts
        empty_api,   # wp media
    ]

    scraper = DireitoScraper()
    editais = scraper.fetch_editais()

    assert len(editais) == 3
    ed_01 = next(ed for ed in editais if "01/2026" in ed["titulo"])
    assert len(ed_01["documentos"]) == 3
    assert {d["tipo_documento"] for d in ed_01["documentos"]} == {
        "original",
        "resultado_provisorio",
        "resultado_final",
    }
    assert ed_01["status"] == "fechado"

    ed_mon = next(ed for ed in editais if "MONITORIA" in ed["titulo"])
    assert ed_mon["categoria"] == "Monitoria"
    assert len(ed_mon["documentos"]) == 2

    # Filtro por ano (2024 -> JURAPP)
    scraper.clear_cache()
    mock_client.get.side_effect = [
        resp_editais,
        resp_monitoria,
        resp_pesquisa,
        empty_page,
        empty_page,
        empty_page,
        empty_page,
        empty_api,
        empty_api,
    ]
    ed_2024 = scraper.fetch_editais(year=2024)
    assert len(ed_2024) == 1
    assert "JURAPP" in ed_2024[0]["titulo"]


# ==============================================================================
# 19. DAF / SIPAC (`DAFScraper`)
# ==============================================================================


@patch("app.modules.scraper.daf.httpx.Client")
def test_daf_and_sipac_public_fetch_editais_mock(mock_client_cls):
    """Valida a coleta de editais internos DAF, pregões eletrônicos DAF e tabelas públicas do SIPAC."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    resp_daf_internos = MagicMock(status_code=200)
    resp_daf_internos.text = """
    <html><body><div class="item-page">
      <p><a href="/images/Editais/2026/EDITAL_DAF_03_2026.pdf">Edital DAF nº 03/2026 – Seleção de Pesquisadores</a></p>
      <p><a href="/images/Editais/2026/RETIFICACAO_01_EDITAL_03_2026.pdf">1ª Retificação – Edital DAF nº 03/2026</a></p>
      <p><a href="/images/Editais/2026/RESULTADO_FINAL_EDITAL_03_2026.pdf">Resultado Final – Edital DAF nº 03/2026</a></p>
    </div></body></html>
    """

    resp_daf_pregoes = MagicMock(status_code=200)
    resp_daf_pregoes.text = """
    <html><body><div class="item-page">
      <p><a href="https://images//licitacoes2025/PE_90001_2025.pdf">Pregão Eletrônico 90001/2025</a></p>
      <p><a href="/images/licitacoes2025/DOU_PE_90001_2025.pdf">Publicação DOU</a></p>
    </div></body></html>
    """

    resp_sig_andamento = MagicMock(status_code=200)
    resp_sig_andamento.text = """
    <html><body>
      <table>
        <tr><th>Licitação</th><th>Valor Est.</th><th>Valor Lic.</th><th>Status</th></tr>
        <tr><td colspan="4">Não há editais disponíveis para consulta.</td></tr>
      </table>
    </body></html>
    """

    resp_sig_atas = MagicMock(status_code=200)
    resp_sig_atas.text = """
    <html><body>
      <table>
        <tr><th>Licitação</th><th>Valor Est.</th><th>Valor Lic.</th><th>Status</th><th>Localização</th><th>Vigência</th><th>Descrição</th><th>Arquivo</th></tr>
        <tr>
          <td>PR 90011/2026</td>
          <td>R$ 34.724,06</td>
          <td>R$ 27.944,75</td>
          <td>JULGADO - HOMOLOGADO</td>
          <td>-</td>
          <td>2026-04-29 00:00:00.0 - 2027-04-29 00:00:00.0</td>
          <td>AQUISIÇÃO DE MATERIAIS DE EXPEDIENTE.</td>
          <td>
            <a href="/public/listaEditais.do?view=visualiza&aba=p-editais-atas&idArquivo=398">Ver</a>
            <a href="verEdital.do?idArquivo=398">Baixar</a>
          </td>
        </tr>
      </table>
    </body></html>
    """

    mock_client.get.side_effect = [
        resp_daf_internos,
        resp_daf_pregoes,
        resp_sig_andamento,
        resp_sig_atas,
    ]

    scraper = DAFScraper()
    editais = scraper.fetch_editais()

    assert len(editais) == 3

    ed_interno = next(ed for ed in editais if "03/2026" in ed["titulo"])
    assert len(ed_interno["documentos"]) == 3
    assert {d["tipo_documento"] for d in ed_interno["documentos"]} == {
        "original",
        "retificacao",
        "resultado_final",
    }

    ed_pregao = next(ed for ed in editais if "90001/2025" in ed["titulo"])
    # URL malformada "https://images//..." deve ser corrigida para https://daf.unb.br/images/...
    assert ed_pregao["url_pdf"] == "https://daf.unb.br/images/licitacoes2025/PE_90001_2025.pdf"
    assert len(ed_pregao["documentos"]) == 2

    ed_sipac = next(ed for ed in editais if "PR 90011/2026" in ed["titulo"])
    assert ed_sipac["ano"] == 2026
    assert ed_sipac["status"] == "fechado"
    assert ed_sipac["inicio_inscricao"] == "2026-04-29"
    assert ed_sipac["fim_inscricao"] == "2027-04-29"
    assert len(ed_sipac["documentos"]) >= 1


@patch("app.modules.scraper.daf.httpx.Client")
def test_daf_sipac_sso_redirect_isolation(mock_client_cls):
    """Garante que um redirecionamento SSO (302) ou 403 no SIPAC não interrompe a coleta do DAF."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    resp_daf = MagicMock(
        status_code=200,
        text='<div class="item-page"><a href="/images/Editais/2026/EDITAL_DAF_01_2026.pdf">EDITAL DAF N. 01/2026</a></div>',
    )
    resp_pregoes = MagicMock(status_code=200, text="<html></html>")
    resp_sso = MagicMock(
        status_code=302,
        headers={"location": "https://autenticacao.unb.br/sso-server/login?service=https://sig.unb.br/sipac/"},
    )
    resp_403 = MagicMock(status_code=403, text="Forbidden")

    mock_client.get.side_effect = [resp_daf, resp_pregoes, resp_sso, resp_403]

    scraper = DAFScraper()
    editais = scraper.fetch_editais()
    assert len(editais) == 1
    assert editais[0]["titulo"] == "EDITAL DAF N. 01/2026"


# ==============================================================================
# 20. PRC (`PRCScraper`)
# ==============================================================================


@patch("app.modules.scraper.prc.httpx.Client")
def test_prc_fetch_editais_and_grouping_mock(mock_client_cls):
    """Valida a coleta de editais da Prefeitura (prefeitura.unb.br e prc.unb.br) e filtro de páginas estáticas."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    resp_pref_editais = MagicMock(status_code=200)
    resp_pref_editais.text = """
    <html><body><main>
      <p><a href="https://estagio.unb.br/images/Processo_seletivo/Processos_seletivos_2026/Edital_01_2026_PRC/Edital_de_abertura_PRC1.pdf">
        EDITAL DE ABERTURA
      </a></p>
      <p><a href="https://prefeitura.unb.br/wp-content/uploads/2026/04/NOTA-INFORMATIVA-07-Edital-Estagio-PRC-12026.pdf">
        NOTA INFORMATIVA 07 – RESULTADO PROVISÓRIO RELATIVO AS ENTREVISTAS
      </a></p>
      <p><a href="https://prefeitura.unb.br/wp-content/uploads/2026/04/NOTA-INFORMATIVA-08-Edital-Estagio-PRC-12026-1.pdf">
        NOTA INFORMATIVA 08 – RESULTADO FINAL
      </a></p>
      <p><a href="https://prefeitura.unb.br/wp-content/uploads/2026/09/SEI_14792334_Edital_01_2026.pdf">
        EDITAL 01/2026 – PRC/COPS – DESTINAÇÃO DE MATERIAL LENHOSO
      </a></p>
      <p><a href="https://unb.br/images/Documentos/Estatuto_e_Regimento_Geral_UnB.pdf">Estatuto e Regimento</a></p>
    </main></body></html>
    """

    resp_pref_licitacoes = MagicMock(status_code=200, text="<html><body></body></html>")
    resp_wp_posts = MagicMock(status_code=200)
    resp_wp_posts.json.return_value = [
        {
            "id": 18613,
            "date": "2026-04-13T10:00:00",
            "link": "https://prefeitura.unb.br/2026/04/13/acao-de-combate-ao-escorpiao-e-pragas-na-unb/",
            "title": {"rendered": "Ação de Combate as Pragas na UnB"},
            "excerpt": {"rendered": "<p>Dedetização no campus.</p>"},
            "content": {"rendered": "<p>Cronograma de dedetização.</p>"},
        }
    ]
    resp_joomla_news = MagicMock(status_code=200)
    resp_joomla_news.text = """
    <html><body>
      <a href="/index.php?option=com_content&view=article&id=401:edital-permissao-de-uso-cantina-2025">
        Edital de Permissão de Uso de Espaço Físico - Cantina e Quiosque 02/2025
      </a>
      <a href="/index.php?option=com_content&view=article&id=10:quem-somos">Quem Somos</a>
    </body></html>
    """
    resp_joomla_search = MagicMock(status_code=200, text="<html><body></body></html>")

    mock_client.get.side_effect = [
        resp_pref_editais,
        resp_pref_licitacoes,
        resp_wp_posts,
        resp_joomla_news,
        resp_joomla_search,
    ]

    scraper = PRCScraper()
    editais = scraper.fetch_editais()

    assert len(editais) == 3
    assert all(ed["orgao_origem"] == "PRC" for ed in editais)

    ed_estagio = next(ed for ed in editais if "Processo Seletivo" in ed["titulo"])
    assert len(ed_estagio["documentos"]) == 3
    assert {d["tipo_documento"] for d in ed_estagio["documentos"]} == {
        "original",
        "resultado_provisorio",
        "resultado_final",
    }

    ed_lenhoso = next(ed for ed in editais if "MATERIAL LENHOSO" in ed["titulo"])
    assert ed_lenhoso["ano"] == 2026

    ed_cantina = next(ed for ed in editais if "Cantina" in ed["titulo"])
    assert ed_cantina["ano"] == 2025
    assert ed_cantina["categoria"] == "Permissão de Uso / Concessão de Espaço"


# ==============================================================================
# 21. DOU (`DOUScraper`)
# ==============================================================================


@patch("app.modules.scraper.dou.httpx.Client")
def test_dou_fetch_editais_portlet_json_mock(mock_client_cls):
    """Valida a extração de publicações da Seção 3 do DOU para a Fundação Universidade de Brasília."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    portlet_payload = {
        "jsonArray": [
            {
                "pubName": "DO3",
                "urlTitle": "edital-n-15/2026-concurso-publico-unb-744311999",
                "numberPage": "65",
                "subTitulo": "",
                "titulo": "",
                "title": "EDITAL Nº 15/2026 - ABERTURA DE PROCESSO SELETIVO SIMPLIFICADO",
                "pubDate": "13/11/2026",
                "content": "A FUNDAÇÃO UNIVERSIDADE DE BRASÍLIA (FUB) torna pública a abertura de inscrições...",
                "editionNumber": "214",
                "hierarchyLevelSize": 2,
                "artType": "Edital",
                "hierarchyStr": "Ministério da Educação/Fundação Universidade de Brasília",
                "hierarchyList": ["Ministério da Educação", "Fundação Universidade de Brasília"],
            },
            {
                "pubName": "DO3",
                "urlTitle": "extrato-de-contrato-n-577/2026-uasg-154040-744311639",
                "numberPage": "67",
                "title": "EXTRATO DE CONTRATO Nº 577/2026 - UASG 154040",
                "pubDate": "13/11/2026",
                "content": "Contratante: FUNDAÇÃO UNIVERSIDADE DE BRASÍLIA - FUB/DF. Objeto: Contratação...",
                "editionNumber": "214",
                "artType": "Extrato de Contrato",
                "hierarchyStr": "Ministério da Educação/Fundação Universidade de Brasília",
            },
            {
                "pubName": "DO3",
                "urlTitle": "extrato-outro-orgao-123456",
                "numberPage": "10",
                "title": "EDITAL DE OUTRA AUTARQUIA",
                "pubDate": "13/11/2026",
                "content": "Órgão sem relação com a universidade.",
                "editionNumber": "214",
                "artType": "Edital",
                "hierarchyStr": "Ministério da Economia/Instituto Nacional",
            },
        ]
    }

    resp_dou = MagicMock(status_code=200)
    resp_dou.text = f"""
    <html><body>
      <script id="_br_com_seatecnologia_in_buscadou_BuscaDouPortlet_params" type="application/json">
        {json.dumps(portlet_payload)}
      </script>
    </body></html>
    """
    mock_client.get.return_value = resp_dou

    scraper = DOUScraper()
    editais = scraper.fetch_editais()

    # Deve retornar apenas os 2 itens da Fundação Universidade de Brasília
    assert len(editais) == 2
    assert all(ed["orgao_origem"] == "DOU" for ed in editais)
    assert all(ed["data_publicacao"] == "2026-11-13" for ed in editais)
    assert all(ed["ano"] == 2026 for ed in editais)

    ed_abertura = next(ed for ed in editais if "EDITAL Nº 15/2026" in ed["titulo"])
    assert ed_abertura["identificador_origem"] == "dou-s3-744311999"
    assert ed_abertura["link"] == "https://www.in.gov.br/web/dou/-/edital-n-15/2026-concurso-publico-unb-744311999"
    assert ed_abertura["status"] == "aberto"
    assert len(ed_abertura["documentos"]) == 1

    ed_extrato = next(ed for ed in editais if "577/2026" in ed["titulo"])
    assert ed_extrato["status"] == "fechado"


@pytest.mark.parametrize("status_code", [403, 429, 500, 503])
@patch("app.modules.scraper.dou.httpx.Client")
def test_dou_waf_403_and_5xx_resilience(mock_client_cls, status_code):
    """Garante que bloqueios WAF (403) ou erros 5xx no DOU retornam [] sem lançar exceção."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    resp_err = MagicMock(status_code=status_code, text="Forbidden / Error")
    mock_client.get.return_value = resp_err

    scraper = DOUScraper()
    assert scraper.fetch_editais() == []


@patch("app.modules.scraper.dou.httpx.Client")
def test_dou_timeout_and_empty_html_resilience(mock_client_cls):
    """Garante resiliência do DOUScraper contra timeouts de rede e HTML vazio."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_client.get.side_effect = httpx.TimeoutException("Read timeout on in.gov.br")
    scraper = DOUScraper()
    assert scraper.fetch_editais() == []

    scraper.clear_cache()
    mock_client.get.side_effect = None
    mock_client.get.return_value = MagicMock(status_code=200, text="<html><body></body></html>")
    assert scraper.fetch_editais() == []


@patch("app.modules.scraper.dou.httpx.Client")
def test_dou_html_fallback_and_fetch_documentos(mock_client_cls):
    """Valida o fallback HTML para links /web/dou/-/ e fetch_documentos no DOUScraper."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    resp_search = MagicMock(status_code=200)
    resp_search.text = """
    <html><body>
      <div class="resultado-item">
        <a href="/web/dou/-/aviso-de-licitacao-pregao-90025-2026-744500111">
          AVISO DE LICITAÇÃO - PREGÃO ELETRÔNICO Nº 90025/2026 - UASG 154040
        </a>
        <span>Publicado em 12/11/2026 - Fundação Universidade de Brasília</span>
      </div>
    </body></html>
    """
    mock_client.get.return_value = resp_search

    scraper = DOUScraper()
    editais = scraper.fetch_editais(year=2026)
    assert len(editais) == 1
    assert editais[0]["identificador_origem"] == "dou-s3-744500111"
    assert editais[0]["data_publicacao"] == "2026-11-12"

    # Testa fetch_documentos em URL nova de detalhe do DOU
    resp_detail = MagicMock(status_code=200)
    resp_detail.text = """
    <html><body>
      <a href="/leiturajornal?data=12-11-2026&secao=DO3">Ícone Diário Completo</a>
    </body></html>
    """
    mock_client.get.return_value = resp_detail
    docs = scraper.fetch_documentos("https://www.in.gov.br/web/dou/-/outro-item-999")
    assert len(docs) == 1
    assert "leiturajornal" in docs[0]["url_pdf"]


def test_fetch_documentos_direct_pdf_and_detail_across_scrapers():
    """Valida fetch_documentos para links diretos PDF e páginas HTML em FACE, DIREITO, DAF e PRC."""
    for scraper, base in (
        (FACEScraper(), "https://face.unb.br"),
        (DireitoScraper(), "https://direito.unb.br"),
        (DAFScraper(), "https://daf.unb.br"),
        (PRCScraper(), "https://prefeitura.unb.br"),
        (PPGContScraper(), "https://ppgcont.unb.br"),
        (PPGGIPPScraper(), "https://ppggipp.unb.br"),
    ):
        assert scraper.fetch_documentos("") == []
        pdf_url = f"{base}/arquivos/Resultado_Final_Edital_01_2026.pdf"
        docs = scraper.fetch_documentos(pdf_url)
        assert len(docs) == 1
        assert docs[0]["url_pdf"] == pdf_url
        assert docs[0]["tipo_documento"] == "resultado_final"


# ==============================================================================
# 22. PPGCONT (`PPGContScraper`) e 23. PPGGIPP (`PPGGIPPScraper`)
# ==============================================================================


@patch("app.modules.scraper.ppgcont.httpx.Client")
def test_ppgcont_fetch_editais_and_grouping_mock(mock_client_cls):
    """Valida a coleta de editais internos, processo seletivo e WP API no PPGCont."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    resp_internos = MagicMock(status_code=200)
    resp_internos.text = """
    <html><body><main>
      <a href="/wp-content/uploads/2026/09/Edital-apoio-docente.pdf">Edital Nº 03/2026 – Auxílio para fomento a docentes do PPGCont</a>
      <a href="/wp-content/uploads/2026/10/ADENDO_AO_EDITAL_03_2026.pdf">Adendo do Edital – prorrogação do prazo do item 4.3</a>
      <a href="/wp-content/uploads/2026/05/EDITAL_INTERNO_FAPDF_n_003_2026.pdf">Edital Interno FAPDF</a>
      <a href="/wp-content/uploads/2026/05/Resultado-FAP-DF-1.pdf">Resultado final</a>
    </main></body></html>
    """

    resp_aluno_regular = MagicMock(status_code=200)
    resp_aluno_regular.text = """
    <html><body>
      <a href="https://ppgcont.unb.br/processo-seletivo-2027-ingresso-em-2027/">Processo Seletivo 2027</a>
    </body></html>
    """

    resp_ps_2027 = MagicMock(status_code=200)
    resp_ps_2027.text = """
    <html><body>
      <h1>Processo Seletivo 2027 (Ingresso em 2027)</h1>
      <a href="/wp-content/uploads/2026/09/Edital_Aluno_Regular_2027_final.pdf">Edital Aluno Regular 2027</a>
      <a href="/wp-content/uploads/2026/09/Retificacao_Edital_07_2026.pdf">Retificação do Edital – Aluno Regular 2027</a>
      <a href="/wp-content/uploads/2026/10/Homologacao_Mestrado_Doutorado.pdf">Homologação das inscrições – Mestrado e Doutorado</a>
    </body></html>
    """

    resp_wp_empty = MagicMock(status_code=200)
    resp_wp_empty.json.return_value = []
    resp_wp_empty.headers = {"X-WP-TotalPages": "1"}

    mock_client.get.side_effect = [
        resp_internos,
        resp_aluno_regular,
        resp_ps_2027,
        resp_wp_empty,
        resp_wp_empty,
    ]

    scraper = PPGContScraper(max_pages=1)
    editais = scraper.fetch_editais()
    assert len(editais) == 3

    ed_fomento = next(ed for ed in editais if "03/2026" in ed["titulo"])
    assert len(ed_fomento["documentos"]) == 2
    assert {d["tipo_documento"] for d in ed_fomento["documentos"]} == {"original", "retificacao"}

    ed_fapdf = next(ed for ed in editais if "FAPDF" in ed["titulo"])
    assert len(ed_fapdf["documentos"]) == 2
    assert ed_fapdf["status"] == "fechado"

    ed_ps = next(ed for ed in editais if "2027" in ed["titulo"])
    assert len(ed_ps["documentos"]) == 3


@patch("app.modules.scraper.ppggipp.httpx.Client")
def test_ppggipp_fetch_editais_and_grouping_mock(mock_client_cls):
    """Valida a coleta e agrupamento por ano (ordem direta e reversa) no PPGGIPP."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    resp_editais = MagicMock(status_code=200)
    resp_editais.text = """
    <html><body><div class="item-page">
      <p>2026</p>
      <p>CHAMADA PÚBLICA SIMPLIFICADA PPG/GIPP/FACE/UNB Nº 01/2026</p>
      <p><a href="/images/PPGGIPP/Edital_01_-_Seleo_Simplificada.pdf">Seleção de candidatos às vagas do Programa</a></p>
      <p><a href="/images/PPGGIPP/SEI_14747135_Edital_01_1.pdf">Resultado</a></p>
      <p>2024</p>
      <p><a href="/images/documentos/Convocao_para_matrcula_em_2_chamada.pdf">Convocação para matrícula em 2ª chamada</a></p>
      <p><a href="/images/documentos/Retificao_do_Edital_n_02_2024.pdf">Retificação do Edital nº 02/2024 - PPGGIPP - PROCAP</a></p>
      <p><a href="/images/documentos/SEI_UNB_-_11510945_-_Edital_1.pdf">Edital nº 02/2024 - PPGGIPP - PROCAP</a></p>
      <p><a href="https://unb.br/images/Documentos/Estatuto_e_Regimento_Geral_UnB.pdf">Estatuto e Regimento</a></p>
    </div></body></html>
    """
    mock_client.get.return_value = resp_editais

    scraper = PPGGIPPScraper()
    editais = scraper.fetch_editais()
    assert len(editais) == 2

    ed_2026 = next(ed for ed in editais if ed["ano"] == 2026)
    assert "01/2026" in ed_2026["titulo"]
    assert len(ed_2026["documentos"]) == 2

    ed_2024 = next(ed for ed in editais if ed["ano"] == 2024)
    assert "02/2024" in ed_2024["titulo"]
    assert len(ed_2024["documentos"]) == 3
    assert ed_2024["url_pdf"].endswith("SEI_UNB_-_11510945_-_Edital_1.pdf")

    # Filtro por ano
    only_2026 = scraper.fetch_editais(year=2026)
    assert len(only_2026) == 1
    assert only_2026[0]["ano"] == 2026


# ==============================================================================
# Integração com `run_periodic_pipeline` e `sync_all_portais`
# ==============================================================================


def test_periodic_pipeline_and_sync_all_with_fase2_scrapers():
    """
    Valida que `run_periodic_pipeline` e `sync_all_portais` executam os 6 novos portais
    com sucesso e isolam falhas individuais (ex.: bloqueio 403 no DOU).
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    sample_item = lambda orgao, slug: {
        "identificador_origem": f"{orgao.lower()}-{slug}",
        "titulo": f"Edital {orgao} 01/2026",
        "link": f"https://{orgao.lower()}.unb.br/edital-01-2026",
        "url_pagina": f"https://{orgao.lower()}.unb.br/edital-01-2026",
        "url_pdf": f"https://{orgao.lower()}.unb.br/edital-01-2026.pdf",
        "orgao_origem": orgao,
        "orgao_emissor": orgao,
        "campus": "Planaltina" if orgao == "FUP" else "Darcy Ribeiro",
        "tipo": f"Edital {orgao}",
        "categoria": f"Edital {orgao}",
        "assunto": f"Edital {orgao}",
        "resumo": f"Resumo do edital {orgao}",
        "descricao": f"Resumo do edital {orgao}",
        "status": "aberto",
        "data_publicacao": "2026-09-01",
        "ano": 2026,
        "documentos": [
            {
                "titulo": "Edital de Abertura",
                "link": f"https://{orgao.lower()}.unb.br/edital-01-2026.pdf",
                "url_pdf": f"https://{orgao.lower()}.unb.br/edital-01-2026.pdf",
                "tipo": "original",
                "tipo_documento": "original",
            }
        ],
    }

    with (
        patch.object(fup_scraper, "fetch_editais", return_value=[sample_item("FUP", "1")]),
        patch.object(face_scraper, "fetch_editais", return_value=[sample_item("FACE", "1")]),
        patch.object(direito_scraper, "fetch_editais", return_value=[sample_item("DIREITO", "1")]),
        patch.object(daf_scraper, "fetch_editais", return_value=[sample_item("DAF", "1")]),
        patch.object(prc_scraper, "fetch_editais", return_value=[sample_item("PRC", "1")]),
        patch.object(dou_scraper, "fetch_editais", return_value=[]),  # Simula DOU bloqueado (403 -> [])
    ):
        report = run_periodic_pipeline(
            db,
            orgaos=["FUP", "FACE", "DIREITO", "DAF", "PRC", "DOU"],
            year=2026,
        )

        assert set(report.keys()) == {"FUP", "FACE", "DIREITO", "DAF", "PRC", "DOU"}
        assert sum(len(v) for v in report.values()) == 5
        assert len(report["DOU"]) == 0
        assert db.query(Edital).count() == 5

        # Verifica sync_all_portais
        sync_res = sync_all_portais(
            db,
            year=2026,
            orgaos=["FUP", "FACE", "DIREITO", "DAF", "PRC", "DOU"],
        )
        assert sync_res["status"] == "success"
        assert sync_res["portais_processados"] == 6
        assert sync_res["editais_encontrados"] == 5
        assert set(sync_res["portais"].keys()) == {"FUP", "FACE", "DIREITO", "DAF", "PRC", "DOU"}

    db.close()
    engine.dispose()


# ==============================================================================
# Testes de Integração ao Vivo (`@pytest.mark.live`)
# ==============================================================================


@pytest.mark.live
@pytest.mark.parametrize("orgao", ["FUP", "FACE", "DIREITO", "DAF", "PRC", "DOU", "PPGCONT", "PPGGIPP"])
def test_live_fase2_scrapers_fetch_editais(orgao):
    """Consulta ao vivo os 8 portais (6 da Fase 2 + PPGCONT e PPGGIPP) e valida o contrato."""
    scraper = get_scraper(orgao)
    assert scraper is not None
    editais = scraper.fetch_editais()
    assert isinstance(editais, list)
    if orgao != "DOU":
        assert len(editais) >= 1, f"Esperado ao menos 1 edital para {orgao}"
    for ed in editais:
        assert ed["titulo"]
        assert ed["url_pagina"]
        assert ed["orgao_origem"] == orgao
        assert isinstance(ed["documentos"], list)

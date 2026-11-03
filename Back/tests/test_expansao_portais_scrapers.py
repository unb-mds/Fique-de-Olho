"""Testes unitários e de integração para os scrapers da expansão de portais da UnB (Issue #84).

Cobre os 4 primeiros portais citados na issue:
1. CEAD (Centro de Educação a Distância) - via Tainacan API
2. SIGAA (Processos Seletivos Públicos dos PPGs e Graduação)
3. Cebraspe (Vestibulares, PAS e Seleções UnB)
4. UnB Idiomas (Editais de proficiência, línguas e bolsas de estudo)
"""

from unittest.mock import MagicMock, patch
import pytest
import httpx

from app.modules.scraper import (
    SCRAPERS_REGISTRY,
    get_scraper,
    cead_scraper,
    sigaa_scraper,
    cebraspe_scraper,
    unb_idiomas_scraper,
    SIGAAScraper,
    CebraspeScraper,
    UnBIdiomasScraper,
    CEADScraper,
)
from app.modules.scraper.base import BaseScraper
from app.modules.scraper.sigaa import parse_sigaa_html, parse_sigaa_ppg_processos_html
from app.modules.scraper.cebraspe import is_unb_event, build_cebraspe_document_url
from app.modules.scraper.unb_idiomas import is_edital_title_or_slug, clean_title


# ============================================================================
# 1. CEAD - Verificação de Conformidade
# ============================================================================

def test_cead_scraper_verified_and_registered():
    """Garante que o scraper do CEAD já está implementado e registrado no catálogo."""
    assert "CEAD" in SCRAPERS_REGISTRY
    scraper = get_scraper("CEAD")
    assert scraper is not None
    assert isinstance(scraper, BaseScraper)
    assert isinstance(scraper, CEADScraper)
    assert scraper.orgao_origem == "CEAD"


# ============================================================================
# 2. SIGAA - Testes do Coletor de Processos Seletivos
# ============================================================================

def test_sigaa_scraper_contract():
    """Valida o contrato e registro do scraper do SIGAA."""
    assert issubclass(SIGAAScraper, BaseScraper)
    assert sigaa_scraper.orgao_origem == "SIGAA"
    assert get_scraper("SIGAA") == sigaa_scraper


def test_sigaa_parse_ppg_processos_html():
    """Valida a extração de editais de mestrado/doutorado na página pública de processos do PPG."""
    sample_ppg_html = """
    <table>
        <tbody>
            <tr>
                <td class="centro" width="120px">Período</td>
                <td class="esquerda">Processos Seletivos</td>
            </tr>
            <tr>
                <td class="centro" width="120px">03/11/2026 à 27/11/2026</td>
                <td class="esquerda">
                    <a href="#" onclick="if(typeof jsfcljs == 'function'){jsfcljs(document.getElementById('form'),{'id':'23223'},'_blank');}return false">
                        <span class="destaqueProcessoeletivo">Edital 02 - DOUTORADO - PPGCA</span>
                        <span class="data destaqueProcessoeletivo">(03/11/2026 : 27/11/2026)</span>
                    </a>
                </td>
            </tr>
        </tbody>
    </table>
    """
    editais = parse_sigaa_ppg_processos_html(sample_ppg_html, "Ciências Animais", "909")
    assert len(editais) == 1
    assert editais[0]["titulo"] == "Edital 02 - DOUTORADO - PPGCA"
    assert editais[0]["programa"] == "Ciências Animais"
    assert editais[0]["inicio_inscricao"] == "03/11/2026"
    assert editais[0]["fim_inscricao"] == "27/11/2026"
    assert editais[0]["status"] == "aberto"
    assert editais[0]["processo_id"] == "23223"


def test_sigaa_parse_html_com_tabela_de_editais():
    """Valida a extração de dados tabulares de processos seletivos do SIGAA."""
    sample_html = """
    <table class="listagem">
        <thead>
            <tr>
                <th>Curso / Programa</th>
                <th>Processo Seletivo</th>
                <th>Período de Inscrição</th>
                <th>Arquivos</th>
            </tr>
        </thead>
        <tbody>
            <tr class="linhaPar">
                <td>Programa de Pós-Graduação em Computação Aplicada</td>
                <td>
                    <a href="/sigaa/public/processo_seletivo/detalhes.jsf?id=101">
                        Edital PPGA nº 01/2026 – Mestrado e Doutorado
                    </a>
                </td>
                <td>01/03/2026 a 31/03/2026</td>
                <td>
                    <a href="/sigaa/verArquivo?idArquivo=5544&key=abc">Edital de Abertura (PDF)</a>
                </td>
            </tr>
            <tr class="linhaImpar">
                <td>Programa de Pós-Graduação em Bioética</td>
                <td>
                    <a href="/sigaa/public/processo_seletivo/detalhes.jsf?id=102">
                        Seleção Simplificada 02/2026 – Aluno Especial
                    </a>
                </td>
                <td>15/04/2026 até 25/04/2026</td>
                <td>
                    <a href="https://sigaa.unb.br/arquivos/edital_bioetica_2026.pdf">Edital Bioética</a>
                </td>
            </tr>
        </tbody>
    </table>
    """
    editais = parse_sigaa_html(sample_html, base_url="https://sigaa.unb.br")
    assert len(editais) == 2

    ed1 = editais[0]
    assert "Edital PPGA nº 01/2026" in ed1["titulo"]
    assert ed1["link"] == "https://sigaa.unb.br/sigaa/public/processo_seletivo/detalhes.jsf?id=101"
    assert ed1["inicio_inscricao"] == "01/03/2026"
    assert ed1["fim_inscricao"] == "31/03/2026"
    assert ed1["ano"] == 2026
    assert len(ed1["documentos"]) == 1
    assert "verArquivo" in ed1["documentos"][0]["link"]

    ed2 = editais[1]
    assert "Seleção Simplificada 02/2026" in ed2["titulo"]
    assert ed2["inicio_inscricao"] == "15/04/2026"
    assert ed2["fim_inscricao"] == "25/04/2026"
    assert ed2["ano"] == 2026


@patch("app.modules.scraper.sigaa.httpx.Client")
def test_sigaa_fetch_documentos_mock(mock_client_cls):
    """Valida a extração de documentos PDF em uma página de processo seletivo do SIGAA."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = "https://sigaa.unb.br/sigaa/public/processo_seletivo/detalhes.jsf?id=101"
    mock_resp.text = """
    <div>
        <h2>Arquivos do Processo</h2>
        <a href="/sigaa/verArquivo?id=1&key=abc">Edital de Abertura</a>
        <a href="/sigaa/arquivos/retificacao_01.pdf">Retificação nº 01</a>
    </div>
    """
    mock_client.get.return_value = mock_resp

    scraper = SIGAAScraper()
    docs = scraper.fetch_documentos("https://sigaa.unb.br/sigaa/public/processo_seletivo/detalhes.jsf?id=101")
    assert len(docs) == 2
    assert any("verArquivo" in d["link"] for d in docs)
    assert any("retificacao" in d["link"] for d in docs)


@patch("app.modules.scraper.sigaa.httpx.Client")
def test_sigaa_network_failure_resilience(mock_client_cls):
    """Garante que falhas de rede no SIGAA retornam lista vazia sem levantar exceções."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_client.get.side_effect = httpx.ConnectTimeout("SIGAA indisponível")

    scraper = SIGAAScraper()
    assert scraper.fetch_editais() == []
    assert scraper.fetch_documentos("https://sigaa.unb.br/teste") == []


@pytest.mark.live
def test_sigaa_live_connectivity():
    """Teste de conexão e extração ao vivo com o SIGAA UnB nos PPGs."""
    scraper = SIGAAScraper(timeout=15.0)
    # Consulta os primeiros 5 programas para validar em tempo real
    editais = scraper.fetch_editais(max_programs=5)
    assert isinstance(editais, list)
    if editais:
        assert editais[0]["titulo"]
        assert editais[0]["programa"]
        assert editais[0]["link"].startswith("https://sigaa.unb.br/")


# ============================================================================
# 3. CEBRASPE - Testes do Coletor de Vestibulares e PAS
# ============================================================================

def test_cebraspe_scraper_contract():
    """Valida o contrato e registro do scraper do Cebraspe."""
    assert issubclass(CebraspeScraper, BaseScraper)
    assert cebraspe_scraper.orgao_origem == "CEBRASPE"
    assert get_scraper("CEBRASPE") == cebraspe_scraper


def test_cebraspe_is_unb_event_filtering():
    """Valida o filtro seletivo de eventos da UnB no Cebraspe."""
    # Eventos da UnB válidos
    assert is_unb_event({"eventoNomeAbreviado": "VESTUNB 26", "eventoURL": "VESTUNB_26"}) is True
    assert is_unb_event({"eventoNomeAbreviado": "PAS 2026 ETAPA 3", "eventoURL": "PAS_26_3"}) is True
    assert is_unb_event({"eventoNomeAbreviado": "UNB 26 2 TF DCS", "eventoURL": "UNB_26_2_TF_DCS"}) is True
    assert is_unb_event({"eventoNomeAbreviado": "ACESSO ENEM UNB 2026", "eventoURL": "UNB_26_ACESSOENEM"}) is True
    assert is_unb_event({"eventoNomeAbreviado": "EDUCAMPO 26", "eventoURL": "EDUCAMPO_26"}) is True

    # Eventos externos que não pertencem à UnB
    assert is_unb_event({"eventoNomeAbreviado": "UFAC 26 MEDICINA", "eventoURL": "UFAC_26_MEDICINA"}) is False
    assert is_unb_event({"eventoNomeAbreviado": "UERR 26 VESTIBULAR", "eventoURL": "UERR_26"}) is False
    assert is_unb_event({"eventoNomeAbreviado": "UNCISAL 2026", "eventoURL": "UNCISAL_26"}) is False


def test_build_cebraspe_document_url():
    """Valida a construção da URL canônica no CDN do Cebraspe."""
    # Caso 1: GUID direto
    guid_arq = {"nomeArquivo": "documento_com_guid.pdf", "isGuid": True}
    url_guid = build_cebraspe_document_url(guid_arq, "VESTUNB_26")
    assert url_guid == "https://cdn.cebraspe.org.br/documento_com_guid.pdf"

    # Caso 2: Padrão vestibulares
    std_arq = {"nomeArquivo": "Ed_1_Abertura.pdf", "isGuid": False, "tipoExtensaoArquivo": "_.pdf"}
    url_std = build_cebraspe_document_url(std_arq, "VESTUNB_26", tipo_evento="vestibulares")
    assert url_std == "https://cdn.cebraspe.org.br/vestibulares/VESTUNB_26/arquivos/Ed_1_Abertura.pdf"


@patch("app.modules.scraper.cebraspe.httpx.Client")
def test_cebraspe_fetch_editais_mock(mock_client_cls):
    """Valida a coleta e formatação dos eventos da UnB a partir do JSON do Cebraspe."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "faseEvento": "Inscrições Abertas",
            "eventos": [
                {
                    "idEvento": 3380,
                    "eventoNomeAbreviado": "VESTUNB 27",
                    "eventoNomeCompleto": "Vestibular Tradicional da Universidade de Brasília 2027",
                    "eventoURL": "VESTUNB_27",
                    "eventoAno": 2027,
                    "eventoTotalVagas": "2100",
                },
                {
                    "idEvento": 9999,
                    "eventoNomeAbreviado": "UFAC 26 MEDICINA",
                    "eventoURL": "UFAC_26",
                    "eventoAno": 2026,
                },
            ],
        },
        {
            "faseEvento": "Encerrados",
            "eventos": [
                {
                    "idEvento": 3239,
                    "eventoNomeAbreviado": "VESTUNB 26",
                    "eventoURL": "VESTUNB_26",
                    "eventoAno": 2026,
                    "eventoTotalVagas": "2102",
                }
            ],
        },
    ]
    mock_client.get.return_value = mock_resp

    scraper = CebraspeScraper()
    editais = scraper.fetch_editais()

    # UFAC deve ser filtrado; VESTUNB 27 e VESTUNB 26 devem ser coletados
    assert len(editais) == 2
    assert editais[0]["identificador"] == "VESTUNB_27"
    assert editais[0]["status"] == "aberto"
    assert editais[0]["ano"] == 2027
    assert editais[0]["vagas"] == "2100"

    assert editais[1]["identificador"] == "VESTUNB_26"
    assert editais[1]["status"] == "fechado"
    assert editais[1]["ano"] == 2026


@patch("app.modules.scraper.cebraspe.httpx.Client")
def test_cebraspe_fetch_documentos_mock(mock_client_cls):
    """Valida a coleta e classificação dos PDFs oficiais anexos ao processo do Cebraspe."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "idEvento": 3239,
        "eventoTipo": "vestibulares",
        "arquivosEdital": [
            {
                "nomeArquivo": "Ed_1_VestUnB_2026_Abertura.pdf",
                "descricaoArquivo": "Edital nº 1 – Abertura",
                "isGuid": False,
                "dataArquivoObj": "2025-08-05T14:20:00",
            },
            {
                "nomeArquivo": "Ed_2_Retificacao.pdf",
                "descricaoArquivo": "Edital nº 2 – Retificação do Quadro de Vagas",
                "isGuid": False,
                "dataArquivoObj": "2025-08-11T15:10:00",
            },
        ],
    }
    mock_client.get.return_value = mock_resp

    scraper = CebraspeScraper()
    docs = scraper.fetch_documentos("https://www.cebraspe.org.br/concursos/VESTUNB_26")

    assert len(docs) == 2
    assert docs[0]["titulo"] == "Edital nº 1 – Abertura"
    assert docs[0]["tipo"] == "original"
    assert docs[0]["link"] == "https://cdn.cebraspe.org.br/vestibulares/VESTUNB_26/arquivos/Ed_1_VestUnB_2026_Abertura.pdf"

    assert docs[1]["titulo"] == "Edital nº 2 – Retificação do Quadro de Vagas"
    assert docs[1]["tipo"] == "retificacao"


@pytest.mark.live
def test_cebraspe_live_fetch_unb_editais():
    """Teste de integração ao vivo: consulta a API do Cebraspe e valida a extração dos editais da UnB."""
    scraper = CebraspeScraper(timeout=20.0)
    editais = scraper.fetch_editais()

    # O Cebraspe possui mais de 40 processos seletivos e vestibulares históricos e ativos da UnB
    assert len(editais) >= 20, f"Esperado ao menos 20 processos seletivos da UnB no Cebraspe, obtido {len(editais)}"

    for ed in editais[:10]:
        assert ed["titulo"], "Edital sem título"
        assert ed["link"].startswith("https://www.cebraspe.org.br/concursos/"), f"URL inválida: {ed['link']}"
        assert ed["identificador"], "Sem identificador do evento"
        assert ed["status"] in ["aberto", "fechado"]

    # Testa busca de documentos reais de um processo seletivo da UnB
    vest_ed = next((e for e in editais if "VESTUNB_26" in e["identificador"]), editais[0])
    docs = scraper.fetch_documentos(vest_ed["link"])
    assert len(docs) >= 1, f"Nenhum documento retornado para {vest_ed['link']}"
    assert any(d["link"].endswith(".pdf") for d in docs)


# ============================================================================
# 4. UNB IDIOMAS - Testes do Coletor de Proficiência e Bolsas
# ============================================================================

def test_unb_idiomas_scraper_contract():
    """Valida o contrato e registro do scraper do UnB Idiomas."""
    assert issubclass(UnBIdiomasScraper, BaseScraper)
    assert unb_idiomas_scraper.orgao_origem == "UNB_IDIOMAS"
    assert get_scraper("UNB_IDIOMAS") == unb_idiomas_scraper


def test_unb_idiomas_helpers():
    """Valida funções auxiliares de filtro e limpeza de títulos do UnB Idiomas."""
    assert is_edital_title_or_slug("Edital Competência Leitora 2.2026", "edital-competencia") is True
    assert is_edital_title_or_slug("Regras Bolsistas 2.2026", "regras-bolsistas") is True
    assert is_edital_title_or_slug("Notícia sem relação", "noticia-evento") is False

    assert clean_title("EDITAL 2.2026 &#8211; EXAME") == "EDITAL 2.2026 – EXAME"


@patch("app.modules.scraper.unb_idiomas.httpx.Client")
def test_unb_idiomas_fetch_editais_mock(mock_client_cls):
    """Valida a coleta e filtragem de editais e chamadas a partir das APIs do UnB Idiomas."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    # Mock da API de mídia
    mock_resp_media = MagicMock()
    mock_resp_media.status_code = 200
    mock_resp_media.json.return_value = [
        {
            "id": 101,
            "title": {"rendered": "Edital-Competencia-Leitora-2.2026"},
            "slug": "edital-competencia-leitora-2-2026",
            "source_url": "https://unbidiomas.unb.br/wp-content/uploads/2026/09/Edital-Competencia-Leitora-2.2026.pdf",
            "date": "2026-09-08T15:20:56",
        },
        {
            "id": 102,
            "title": {"rendered": "Regras-Bolsistas-2.2026"},
            "slug": "regras-bolsistas-2-2026",
            "source_url": "https://unbidiomas.unb.br/wp-content/uploads/2026/07/Regras-Bolsistas-2.2026.pdf",
            "date": "2026-07-17T13:43:54",
        },
        {
            "id": 103,
            "title": {"rendered": "Banner Propaganda Curso"},
            "slug": "banner-curso",
            "source_url": "https://unbidiomas.unb.br/wp-content/uploads/2026/01/banner.pdf",
            "date": "2026-01-01T10:00:00",
        },
    ]

    # Mock da API de posts
    mock_resp_posts = MagicMock()
    mock_resp_posts.status_code = 200
    mock_resp_posts.json.return_value = [
        {
            "id": 201,
            "title": {"rendered": "EDITAL 2.2026 &#8211; EXAME DE COMPETÊNCIA LEITORA"},
            "link": "https://unbidiomas.unb.br/2026/09/08/edital-1-2026-exame/",
            "date": "2026-09-08T14:08:36",
        }
    ]

    mock_client.get.side_effect = [mock_resp_media, mock_resp_posts]

    scraper = UnBIdiomasScraper()
    editais = scraper.fetch_editais()

    # O banner deve ser descartado, mantendo 2 documentos PDF e 1 post
    assert len(editais) == 3
    assert any("Competencia-Leitora" in ed["titulo"] for ed in editais)
    assert any("Regras-Bolsistas" in ed["titulo"] for ed in editais)
    assert all(ed["ano"] == 2026 for ed in editais)


@patch("app.modules.scraper.unb_idiomas.httpx.Client")
def test_unb_idiomas_fetch_documentos_mock(mock_client_cls):
    """Valida a extração de PDFs diretamente e a partir de posts informativos."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_resp_post = MagicMock()
    mock_resp_post.status_code = 200
    mock_resp_post.url = "https://unbidiomas.unb.br/2026/09/08/edital-1-2026-exame/"
    mock_resp_post.text = """
    <div class="entry-content">
        <p>Confira o documento:</p>
        <a href="https://unbidiomas.unb.br/wp-content/uploads/2026/09/Edital-Oficial.pdf">Baixar Edital</a>
    </div>
    """
    mock_client.get.return_value = mock_resp_post

    scraper = UnBIdiomasScraper()

    # Caso 1: URL já é um PDF
    docs_pdf = scraper.fetch_documentos("https://unbidiomas.unb.br/wp-content/uploads/2026/09/Edital-Competencia-Leitora-2.2026.pdf")
    assert len(docs_pdf) == 1
    assert docs_pdf[0]["link"].endswith(".pdf")

    # Caso 2: URL de post informativo
    docs_post = scraper.fetch_documentos("https://unbidiomas.unb.br/2026/09/08/edital-1-2026-exame/")
    assert len(docs_post) == 1
    assert docs_post[0]["link"] == "https://unbidiomas.unb.br/wp-content/uploads/2026/09/Edital-Oficial.pdf"


@pytest.mark.live
def test_unb_idiomas_live_fetch_editais():
    """Teste de integração ao vivo: consulta a API do UnB Idiomas e valida a extração dos editais reais."""
    scraper = UnBIdiomasScraper(timeout=20.0)
    editais = scraper.fetch_editais()

    assert len(editais) >= 5, f"Esperado ao menos 5 editais/chamadas no UnB Idiomas, obtido {len(editais)}"

    for ed in editais:
        assert ed["titulo"], "Edital sem título"
        assert ed["link"].startswith("https://unbidiomas.unb.br/"), f"URL inválida: {ed['link']}"
        assert ed["data_publicacao"], "Sem data de publicação"
        assert ed["ano"] is not None

    # Valida documento associado
    first_link = editais[0]["link"]
    docs = scraper.fetch_documentos(first_link)
    assert len(docs) >= 1
    assert any(d["link"].endswith(".pdf") for d in docs)

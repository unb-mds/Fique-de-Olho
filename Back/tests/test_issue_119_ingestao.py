"""Testes da Issue #119 — falhas de ingestão/scraper (Google Drive, resumos vagos, títulos etapa+órgão, FUP/PRC)."""

import httpx
import pytest

from app.modules.scraper import pdf as pdf_mod
from app.modules.scraper.fup import FUPScraper
from app.modules.scraper.parser import is_vague_title, reconstruir_titulo_edital
from app.modules.scraper.pdf import is_google_drive_url, normalize_google_drive_url
from app.modules.scraper.pipeline import _is_likely_pdf_url, _select_candidate_pdf_url
from app.modules.scraper.prc import PRCScraper
from app.modules.scraper.summarizer import _resumo_heuristico, is_generic_summary

DRIVE_ID = "1AbC_dEf-GhIjKlMnOpQrStUvWxYz012"
DRIVE_DIRECT = f"https://drive.google.com/uc?export=download&id={DRIVE_ID}"


# ---------------------------------------------------------------------------
# 1. Google Drive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        f"https://drive.google.com/file/d/{DRIVE_ID}/view",
        f"https://drive.google.com/file/d/{DRIVE_ID}/view?usp=sharing",
        f"https://drive.google.com/open?id={DRIVE_ID}",
        f"https://drive.google.com/open?usp=sharing&id={DRIVE_ID}",
    ],
)
def test_drive_url_e_convertida_para_download_direto(url):
    assert is_google_drive_url(url) is True
    assert normalize_google_drive_url(url) == DRIVE_DIRECT


def test_url_nao_drive_nao_e_alterada():
    url = "https://deg.unb.br/images/edital.pdf"
    assert is_google_drive_url(url) is False
    assert normalize_google_drive_url(url) == url
    assert is_google_drive_url(None) is False
    assert is_google_drive_url("https://drive.google.com/drive/folders/abc") is False


def test_download_pdf_usa_link_direto_do_drive(monkeypatch):
    chamadas = []

    def fake_get(url, **kwargs):
        chamadas.append(url)
        return httpx.Response(200, content=b"%PDF-1.4 fake", request=httpx.Request("GET", url))

    monkeypatch.setattr(pdf_mod.httpx, "get", fake_get)
    conteudo = pdf_mod.download_pdf(f"https://drive.google.com/file/d/{DRIVE_ID}/view")

    assert chamadas == [DRIVE_DIRECT]
    assert conteudo == b"%PDF-1.4 fake"


def test_extract_pdf_de_url_do_drive_extrai_documento(monkeypatch):
    monkeypatch.setattr(pdf_mod.httpx, "get", lambda url, **kw: httpx.Response(200, content=b"x", request=httpx.Request("GET", url)))
    capturado = {}

    def fake_extract(data, source_name="memory"):
        capturado["source"] = source_name
        return pdf_mod.PDFDocumentExtraction(source=source_name, num_pages=1, full_text="EDITAL FUP")

    monkeypatch.setattr(pdf_mod, "extract_pdf_from_bytes", fake_extract)
    doc = pdf_mod.extract_pdf(f"https://drive.google.com/open?id={DRIVE_ID}")

    assert doc.full_text == "EDITAL FUP"


def test_pipeline_reconhece_drive_como_pdf_candidato():
    view = f"https://drive.google.com/file/d/{DRIVE_ID}/view"
    assert _is_likely_pdf_url(view) is True
    assert _is_likely_pdf_url(f"https://drive.google.com/open?id={DRIVE_ID}") is True
    assert _select_candidate_pdf_url({"url_pdf": view}, [], "https://fup.unb.br/x") == view


# ---------------------------------------------------------------------------
# 2. Resumos vagos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rotulo", ["AQUI", "Aqui.", "Clique aqui", "Download", "Saiba mais"])
def test_resumo_heuristico_nunca_devolve_rotulo_generico(rotulo):
    assert is_generic_summary(rotulo, "Edital FUP Nº 10/2026 - Extensão") is True
    resumo = _resumo_heuristico("Edital FUP Nº 10/2026 - Extensão", None, None, rotulo)
    assert resumo is None


def test_resumo_heuristico_ainda_usa_objeto_do_pdf_quando_resumo_e_aqui():
    texto = "1. DO OBJETO\nSelecionar projetos de extensão universitária da FUP para estudantes de graduação.\n2. DOS REQUISITOS\n"
    resumo = _resumo_heuristico("Edital FUP Nº 10/2026", texto, None, "AQUI")
    assert resumo is not None and resumo.startswith("Selecionar projetos de extensão")


def test_resumo_heuristico_preserva_resumo_informativo_curto_diferente_do_titulo():
    resumo = _resumo_heuristico("Edital FUP Nº 10/2026", None, None, "Inscrições até 20/11 pelo SIGAA.")
    assert resumo == "Inscrições até 20/11 pelo SIGAA."


# ---------------------------------------------------------------------------
# 3. Títulos 'Etapa + Órgão'
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "titulo",
    [
        "Resultado Provisório - FUP",
        "Resultado Final – PRC",
        "Retificação - DEG",
        "Convocação - FUP",
        "RESULTADO PRELIMINAR - CEAD",
    ],
)
def test_titulo_etapa_mais_orgao_e_vago(titulo):
    assert is_vague_title(titulo) is True


@pytest.mark.parametrize(
    "titulo",
    [
        "Resultado Provisório - FUP - Edital Nº 10/2026",
        "Resultado Final do PIBIC 2024/2025",
        "Resultado Final - Monitoria FUP",
    ],
)
def test_titulo_etapa_com_numero_ou_programa_nao_e_vago(titulo):
    assert is_vague_title(titulo) is False


def test_titulo_etapa_orgao_e_reconstruido_pelo_texto_do_pdf():
    texto = (
        "UNIVERSIDADE DE BRASÍLIA\n"
        "EDITAL FUP Nº 10/2026 - SELEÇÃO DE PROJETOS DE EXTENSÃO\n"
        "1. DO OBJETO\nSelecionar projetos de extensão.\n"
    )
    titulo = reconstruir_titulo_edital("Resultado Provisório - FUP", texto_extraido=texto, orgao_emissor="FUP")
    assert titulo.startswith("Resultado Provisório")
    assert "10/2026" in titulo
    assert not is_vague_title(titulo)


# ---------------------------------------------------------------------------
# 4. FUP e PRC
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("resumo", ["AQUI", "aqui.", "Clique aqui", ""])
def test_fup_nunca_gera_resumo_aqui(resumo):
    item = FUPScraper()._build_edital_dict(
        identificador_origem="fup-x",
        titulo="Edital FUP Nº 10/2026 - Extensão",
        url_pagina="https://fup.unb.br/editais/x",
        data_publicacao="2026-11-01",
        ano=2026,
        resumo=resumo,
    )
    assert item["resumo"] == "Edital FUP Nº 10/2026 - Extensão"
    assert item["descricao"] == item["resumo"]


def test_fup_resumo_e_titulo_aqui_resulta_em_resumo_vazio():
    item = FUPScraper()._build_edital_dict(
        identificador_origem="fup-y",
        titulo="AQUI",
        url_pagina="https://fup.unb.br/editais/y",
        data_publicacao="2026-11-01",
        ano=2026,
        resumo="AQUI",
    )
    assert item["resumo"] == ""


def _prc_com_redirect_para_home(monkeypatch):
    """PRC cujo host prc.unb.br responde 301 para a home genérica www.unb.br (que tem um PDF qualquer)."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "prc.unb.br":
            return httpx.Response(301, headers={"Location": "https://www.unb.br/"})
        return httpx.Response(200, html='<a href="https://www.unb.br/docs/Edital_geral.pdf">Edital geral</a>')

    scraper = PRCScraper()
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        scraper, "_get_client", lambda timeout=None: httpx.Client(transport=transport, follow_redirects=True)
    )
    return scraper


def test_prc_redirect_301_para_home_generica_nao_gera_documentos(monkeypatch):
    scraper = _prc_com_redirect_para_home(monkeypatch)
    docs = scraper.fetch_documentos("https://prc.unb.br/index.php?option=com_content&view=article&id=10")
    assert docs == []


def test_prc_is_generic_home_redirect():
    class R:
        def __init__(self, url):
            self.url = url

    assert PRCScraper._is_generic_home_redirect("https://prc.unb.br/x", R("https://www.unb.br/")) is True
    assert PRCScraper._is_generic_home_redirect("https://prc.unb.br/x", R("https://unb.br")) is True
    # Redireciona para documento/página real -> não é home genérica
    assert PRCScraper._is_generic_home_redirect("https://prc.unb.br/x", R("https://prefeitura.unb.br/editais/")) is False
    assert PRCScraper._is_generic_home_redirect("https://prc.unb.br/x", R("https://www.unb.br/docs/e.pdf")) is False
    assert PRCScraper._is_generic_home_redirect("https://prc.unb.br/x", R("https://prc.unb.br/y")) is False

"""Testes unitários para a interface BaseScraper e a implementação DEGScraper."""

from unittest.mock import MagicMock, patch
import pytest

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import DEGScraper, deg_scraper, fetch_editais, fetch_documentos


class IncompleteScraper(BaseScraper):
    """Subclasse incompleta para teste de validação de interface abstrata."""
    pass


class DummyDPGScraper(BaseScraper):
    """Subclasse concreta simulando um scraper para o Decanato de Pós-Graduação (DPG)."""

    @property
    def orgao_origem(self) -> str:
        return "DPG"

    def fetch_editais(self, year=None):
        return [
            {
                "titulo": "Edital DPG Mestrado 01/2026",
                "link": "https://dpg.unb.br/editais/01-2026",
                "data_publicacao": "10/03/2026",
            }
        ]

    def fetch_documentos(self, edital_url: str):
        return [
            {
                "titulo": "Edital Completo",
                "link": f"{edital_url}/edital.pdf",
                "tipo": "original",
            }
        ]


def test_base_scraper_cannot_be_instantiated_directly():
    """Garante que BaseScraper é puramente abstrata e não pode ser instanciada."""
    with pytest.raises(TypeError) as exc:
        BaseScraper()  # type: ignore
    assert "Can't instantiate abstract class BaseScraper" in str(exc.value)


def test_incomplete_subclass_cannot_be_instantiated():
    """Garante que subclasses que não implementam os métodos abstratos lançam TypeError."""
    with pytest.raises(TypeError):
        IncompleteScraper()  # type: ignore


def test_concrete_subclass_implementation():
    """Garante que uma implementação concreta de BaseScraper atende ao contrato de dados."""
    scraper = DummyDPGScraper()
    assert isinstance(scraper, BaseScraper)
    assert scraper.orgao_origem == "DPG"

    editais = scraper.fetch_editais(2026)
    assert len(editais) == 1
    assert editais[0]["titulo"] == "Edital DPG Mestrado 01/2026"

    docs = scraper.fetch_documentos("https://dpg.unb.br/editais/01-2026")
    assert len(docs) == 1
    assert docs[0]["tipo"] == "original"


def test_deg_scraper_inherits_from_base_scraper():
    """Verifica herança e conformidade do DEGScraper com a BaseScraper."""
    assert issubclass(DEGScraper, BaseScraper)
    assert isinstance(deg_scraper, BaseScraper)
    assert deg_scraper.orgao_origem == "DEG"


@patch("app.modules.scraper.deg.httpx.get")
def test_deg_scraper_fetch_editais(mock_get):
    """Verifica se deg_scraper.fetch_editais delega e extrai a listagem corretamente."""
    mock_html = """
    <h6><a href="/edital-01-2026">Edital DEG 01/2026</a></h6>
    <span>Publicado em: 15 de janeiro de 2026</span>
    """
    mock_resp = MagicMock()
    mock_resp.text = mock_html
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    editais = deg_scraper.fetch_editais(year=2026)
    assert len(editais) == 1
    assert editais[0]["titulo"] == "Edital DEG 01/2026"
    assert "edital-01-2026" in editais[0]["link"]


@patch("app.modules.scraper.deg.httpx.get")
def test_deg_scraper_fetch_documentos(mock_get):
    """Verifica se deg_scraper.fetch_documentos extrai e classifica documentos do edital."""
    mock_html = """
    <div class="entry-content">
        <a href="/arquivos/resultado_final.pdf">Resultado Final Homologado</a>
        <a href="/arquivos/edital_abertura.pdf">Edital de Abertura Original</a>
    </div>
    """
    mock_resp = MagicMock()
    mock_resp.text = mock_html
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    docs = deg_scraper.fetch_documentos("https://deg.unb.br/edital-01-2026")
    assert len(docs) == 2
    tipos = [d["tipo"] for d in docs]
    assert "resultado_final" in tipos
    assert "original" in tipos


@patch("app.modules.scraper.base.download_pdf")
def test_base_scraper_download_documento(mock_download):
    """Verifica se o método download_documento compartilhado utiliza download_pdf."""
    mock_download.return_value = b"%PDF-1.4 mock content"
    scraper = DummyDPGScraper()

    content = scraper.download_documento("https://dpg.unb.br/edital.pdf")
    assert content == b"%PDF-1.4 mock content"
    mock_download.assert_called_once_with("https://dpg.unb.br/edital.pdf", timeout=15.0)


def test_legacy_module_functions_compatibility():
    """Garante retrocompatibilidade das funções legadas em nível de módulo de deg.py."""
    assert callable(fetch_editais)
    assert callable(fetch_documentos)

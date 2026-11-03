"""Scraper para o Portal de Concursos da UnB (Docentes Efetivos, Temporários e Técnicos)."""

from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional
import unicodedata
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

logger = logging.getLogger(__name__)

CONCURSOS_BASE_URL = "https://concursos.unb.br"
DEFAULT_TIMEOUT = 15.0
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Fique-de-Olho/1.0"

DATE_PATTERN = re.compile(r"\((\d{1,2}/\d{1,2}/\d{4})\)")
DATE_GENERAL_PATTERN = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")


def parse_concursos_edital_page(html: str, page_url: str) -> Dict[str, Any]:
    """Extrai informações e documentos de uma página de edital do Portal de Concursos."""
    soup = BeautifulSoup(html, "html.parser")

    # Extrai o título principal do edital
    h1_or_h2 = soup.find(["h1", "h2"], class_=lambda c: c and ("title" in c or "header" in c)) or soup.find("h2")
    titulo = h1_or_h2.get_text(" ", strip=True) if h1_or_h2 else ""
    if not titulo and soup.title:
        titulo = soup.title.string.replace("UnB Concurso -", "").strip()

    titulo = re.sub(r"\s+", " ", titulo).strip()

    content = (
        soup.find("div", class_="item-page")
        or soup.find("div", itemprop="articleBody")
        or soup.find("div", id="content")
        or soup.find("main")
        or soup
    )

    # Extração de descrição (Lotação, Cargo, Área, Vagas)
    raw_text = unicodedata.normalize("NFC", content.get_text(" ", strip=True))
    raw_text = re.sub(r"\s+", " ", raw_text)
    descricao = ""
    desc_match = re.search(r"(Lota[cç][aã]o:.*?Vaga:.*?(?:\.|$))", raw_text)
    if desc_match:
        descricao = desc_match.group(1).strip()
    else:
        # Fallback de busca de cargo e lotação por blocos de parágrafo
        snippets = []
        for p in content.find_all(["p", "div", "li"]):
            t = p.get_text(" ", strip=True)
            if any(k in t for k in ["Lotação", "Cargo", "Área de Conhecimento", "Vaga", "Lotaçao"]):
                if t not in snippets and len(t) < 300:
                    snippets.append(t)
        descricao = " | ".join(snippets[:3]) if snippets else ""

    documentos: List[Dict[str, Any]] = []
    seen_docs = set()
    data_pub = ""
    has_final = False

    for a in content.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)
        if not href or href.startswith("#") or "javascript:" in href:
            continue

        if any(ext in href.lower() for ext in [".pdf", "phocadownload", "verarquivo", ".doc"]):
            full_link = urljoin(page_url, href)
            if full_link not in seen_docs:
                seen_docs.add(full_link)
                m = DATE_PATTERN.search(text) or DATE_GENERAL_PATTERN.search(text)
                doc_date = m.group(1) if m else ""
                if not data_pub and doc_date:
                    data_pub = doc_date

                lower_text = text.lower()
                if any(k in lower_text for k in ["resultado final", "homologação", "homologacao", "encerrado"]):
                    has_final = True

                documentos.append({
                    "titulo": text or "Documento Oficial do Concurso",
                    "link": full_link,
                    "data": doc_date,
                    "tipo": classify_document(text, full_link),
                })

    # Determinação do ano
    ano: Optional[int] = None
    year_match = re.search(r"/(\d{4})/", page_url) or re.search(r"/(\d{4})$", page_url)
    if year_match:
        ano = int(year_match.group(1))
    elif data_pub and len(data_pub) >= 10:
        ano = int(data_pub[-4:])
    else:
        m_title_year = re.search(r"\b(20\d{2})\b", titulo)
        if m_title_year:
            ano = int(m_title_year.group(1))

    # Status
    status = "fechado" if has_final else "aberto"

    return {
        "titulo": titulo,
        "descricao": descricao,
        "link": page_url,
        "data_publicacao": data_pub,
        "status": status,
        "ano": ano,
        "documentos": documentos,
    }


def parse_concursos_category_html(html: str, base_url: str = CONCURSOS_BASE_URL) -> List[Dict[str, str]]:
    """Extrai os links para páginas de editais individuais a partir de uma listagem do Joomla."""
    soup = BeautifulSoup(html, "html.parser")
    edital_links: List[Dict[str, str]] = []
    seen = set()

    content = soup.find("div", id="content") or soup.find("main") or soup
    for a in content.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)
        if "edital-de-abertura" in href or "editais-docente" in href or "editais-temporario" in href:
            full_url = urljoin(base_url, href)
            if full_url not in seen and not full_url.endswith("-inicial"):
                seen.add(full_url)
                edital_links.append({
                    "titulo": text,
                    "link": full_url,
                })

    return edital_links


class ConcursosScraper(BaseScraper):
    """Implementação do scraper para o Portal de Concursos da UnB."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout

    @property
    def orgao_origem(self) -> str:
        return "CONCURSOS"

    def fetch_editais(
        self,
        year: Optional[int] = None,
        max_details: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Consulta os editais de concursos públicos e seleções docentes da UnB.

        Args:
            year: Ano de referência para filtragem (opcional).
            max_details: Limite de páginas individuais para inspeção profunda de PDFs.

        Returns:
            Lista de editais padronizados com metadados e documentos anexos.
        """
        editais: List[Dict[str, Any]] = []
        seen_urls = set()

        # Determina os anos a consultar
        current_year = datetime.now(timezone.utc).year
        if year is not None:
            years_to_check = [year]
        else:
            years_to_check = [current_year, current_year - 1, current_year - 2]

        category_urls = [
            f"{CONCURSOS_BASE_URL}/index.php/efetivos-inicial",
            f"{CONCURSOS_BASE_URL}/index.php/temporarios-inicial",
            f"{CONCURSOS_BASE_URL}/index.php/tecnicos",
        ]
        for y in years_to_check:
            category_urls.append(f"{CONCURSOS_BASE_URL}/index.php/editais-docente/{y}")
            category_urls.append(f"{CONCURSOS_BASE_URL}/index.php/editais-temporario/temporario-{y}")

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                edital_targets: List[Dict[str, str]] = []

                # 1. Mapeia os links dos editais a partir das categorias
                for cat_url in category_urls:
                    try:
                        resp = client.get(cat_url)
                        if resp.status_code == 200:
                            items = parse_concursos_category_html(resp.text, base_url=str(resp.url))
                            for it in items:
                                if it["link"] not in seen_urls:
                                    seen_urls.add(it["link"])
                                    edital_targets.append(it)
                    except httpx.HTTPError as exc:
                        logger.warning(f"Erro ao consultar listagem de concursos em {cat_url}: {exc}")
                        continue

                # 2. Inspeciona cada página de edital para coletar anexos e metadados
                targets_to_inspect = edital_targets[:max_details] if max_details is not None else edital_targets
                for target in targets_to_inspect:
                    link = target["link"]
                    try:
                        resp = client.get(link)
                        if resp.status_code == 200:
                            parsed = parse_concursos_edital_page(resp.text, link)
                            if not parsed["titulo"] and target.get("titulo"):
                                parsed["titulo"] = target["titulo"]

                            if year is not None and parsed.get("ano") is not None and parsed["ano"] != year:
                                continue

                            editais.append(parsed)
                    except httpx.HTTPError as exc:
                        logger.warning(f"Erro ao inspecionar edital de concurso em {link}: {exc}")
                        continue

        except Exception as exc:
            logger.error(f"Erro geral no scraper de Concursos da UnB: {exc}")
            return editais

        return editais

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai todos os documentos e anexos PDF de uma página de edital de concurso."""
        if edital_url.lower().endswith(".pdf") or "phocadownload" in edital_url.lower():
            return [{"titulo": "Documento Oficial Concurso", "link": edital_url, "tipo": classify_document(edital_url, edital_url)}]

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                resp = client.get(edital_url)
                if resp.status_code == 200:
                    parsed = parse_concursos_edital_page(resp.text, str(resp.url))
                    return parsed.get("documentos", [])
        except Exception as exc:
            logger.error(f"Erro ao extrair documentos de {edital_url} em Concursos: {exc}")

        return []


concursos_scraper = ConcursosScraper()

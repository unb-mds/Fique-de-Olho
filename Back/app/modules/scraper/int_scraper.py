"""Scraper para a Secretaria de Assuntos Internacionais da UnB (INT)."""

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

INT_BASE_URL = "https://int.unb.br"
INT_SELECOES_URL = "https://int.unb.br/selecoes-abertas/"
DEFAULT_TIMEOUT = 12.0
USER_AGENT = "Fique-de-Olho/1.0"

DATE_PATTERN = re.compile(
    r"\b(\d{1,2}\s+de\s+[A-Za-zÀ-ÿ]+\s+de\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})\b",
    re.IGNORECASE,
)


def parse_int_html(html: str, base_url: str = INT_BASE_URL) -> List[Dict[str, Any]]:
    """Extrai editais da listagem de seleções abertas da INT."""
    soup = BeautifulSoup(html, "html.parser")
    editais: List[Dict[str, Any]] = []
    seen = set()

    content = soup.select_one(".entry-content, article, main") or soup

    for a in content.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)

        if not text or len(text) < 5:
            continue

        if any(ign in text.lower() for ign in ["pular para", "governo", "regimento", "cookies"]):
            continue

        full_url = urljoin(base_url, href)

        if not any(k in text.lower() or k in href.lower() for k in ["edital", "selecao", "seleção", "chamada"]):
            continue

        if full_url in seen:
            continue
        seen.add(full_url)

        date_match = DATE_PATTERN.search(text)
        data_pub = date_match.group(0) if date_match else ""

        editais.append({
            "titulo": text,
            "link": full_url,
            "data_publicacao": data_pub,
        })

    return editais


class INTScraper(BaseScraper):
    """Implementação do scraper para a Secretaria de Assuntos Internacionais (INT)."""

    @property
    def orgao_origem(self) -> str:
        return "INT"

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Extrai as seleções abertas de internacionalização."""
        try:
            resp = httpx.get(
                INT_SELECOES_URL,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            return parse_int_html(resp.text, base_url=str(resp.url))
        except httpx.HTTPError:
            return []

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai anexos e editais em PDF vinculados à página de seleção da INT."""
        if edital_url.lower().endswith(".pdf"):
            return [{"titulo": "Edital Oficial INT", "link": edital_url, "tipo": classify_document(edital_url, edital_url)}]

        try:
            resp = httpx.get(
                edital_url,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        documentos: List[Dict[str, Any]] = []
        for a in soup.find_all("a", href=True):
            h = a["href"].strip()
            if ".pdf" in h.lower():
                full_h = urljoin(str(resp.url), h)
                t = a.get_text(" ", strip=True) or "Documento Anexo"
                documentos.append({
                    "titulo": t,
                    "link": full_h,
                    "tipo": classify_document(t, full_h),
                })
        return documentos


int_scraper = INTScraper()

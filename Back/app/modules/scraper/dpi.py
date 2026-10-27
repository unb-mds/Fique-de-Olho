"""Scraper para o Decanato de Pesquisa e Inovação da UnB (DPI)."""

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

DPI_BASE_URL = "https://dpi.unb.br"
DEFAULT_TIMEOUT = 12.0
USER_AGENT = "Fique-de-Olho/1.0"

DATE_PATTERN = re.compile(
    r"\b(\d{1,2}\s+de\s+[A-Za-zÀ-ÿ]+\s+de\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})\b",
    re.IGNORECASE,
)


def build_dpi_url(year: Optional[int] = None) -> str:
    y = year or 2026
    return f"{DPI_BASE_URL}/editais/editais{y}"


def parse_dpi_html(html: str, base_url: str = DPI_BASE_URL) -> List[Dict[str, Any]]:
    """Extrai editais e chamadas de pesquisa do portal DPI."""
    soup = BeautifulSoup(html, "html.parser")
    editais: List[Dict[str, Any]] = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)

        if not text or len(text) < 4:
            continue

        if any(ign in text.lower() for ign in ["pular para", "governo", "regimento", "manual"]):
            continue

        full_url = urljoin(base_url, href)

        is_edital = any(k in text.lower() for k in ["edital", "chamada", "fomento", "pesquisa"]) or "edital" in href.lower()
        if not is_edital:
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


class DPIScraper(BaseScraper):
    """Implementação do scraper para o Decanato de Pesquisa e Inovação (DPI)."""

    @property
    def orgao_origem(self) -> str:
        return "DPI"

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Busca editais no portal do DPI para o ano fornecido."""
        url = build_dpi_url(year)
        try:
            resp = httpx.get(
                url,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            return parse_dpi_html(resp.text, base_url=str(resp.url))
        except httpx.HTTPError:
            return []

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai PDFs anexos vinculados a um edital do DPI."""
        if edital_url.lower().endswith(".pdf"):
            return [{"titulo": "Edital Oficial DPI", "link": edital_url, "tipo": classify_document(edital_url, edital_url)}]

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
                t = a.get_text(" ", strip=True) or "Arquivo Anexo"
                documentos.append({
                    "titulo": t,
                    "link": full_h,
                    "tipo": classify_document(t, full_h),
                })
        return documentos


dpi_scraper = DPIScraper()

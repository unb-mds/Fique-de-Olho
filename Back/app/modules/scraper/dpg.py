"""Scraper para o Decanato de Pós-Graduação da UnB (DPG)."""

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

DPG_BASE_URL = "https://dpg.unb.br"
DPG_EDITAIS_URL = "https://dpg.unb.br/editais-abertos/"
DEFAULT_TIMEOUT = 12.0
USER_AGENT = "Fique-de-Olho/1.0"

DATE_PATTERN = re.compile(
    r"\b(\d{1,2}\s+de\s+[A-Za-zÀ-ÿ]+\s+de\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})\b",
    re.IGNORECASE,
)


def parse_dpg_html(html: str, base_url: str = DPG_BASE_URL) -> List[Dict[str, Any]]:
    """Extrai os editais principais e anexos da página de editais abertos do DPG."""
    soup = BeautifulSoup(html, "html.parser")
    editais: List[Dict[str, Any]] = []
    seen_links = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)

        if not text or len(text) < 5:
            continue

        # Ignora links de navegação institucional
        if any(ign in text.lower() for ign in ["pular para", "governo", "regimento", "cookies", "ouvidoria"]):
            continue

        full_url = urljoin(base_url, href)

        # Identifica postagens de editais ou links diretos de editais em PDF
        is_edital = any(k in text.lower() for k in ["edital", "chamada", "seleção"]) or "edital" in href.lower()
        if not is_edital:
            continue

        if full_url in seen_links:
            continue
        seen_links.add(full_url)

        date_match = DATE_PATTERN.search(text)
        data_pub = date_match.group(0) if date_match else ""

        editais.append(
            {
                "titulo": text,
                "link": full_url,
                "data_publicacao": data_pub,
            }
        )

    return editais


class DPGScraper(BaseScraper):
    """Implementação do scraper para o portal do DPG (Pós-Graduação)."""

    @property
    def orgao_origem(self) -> str:
        return "DPG"

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Extrai os editais abertos do DPG."""
        url = DPG_EDITAIS_URL
        try:
            resp = httpx.get(
                url,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            return parse_dpg_html(resp.text, base_url=str(resp.url))
        except httpx.HTTPError:
            return []

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai anexos PDF de uma página de edital ou do próprio link."""
        if edital_url.lower().endswith(".pdf"):
            tipo = classify_document(edital_url, edital_url)
            return [{"titulo": "Edital Oficial", "link": edital_url, "tipo": tipo}]

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


dpg_scraper = DPGScraper()

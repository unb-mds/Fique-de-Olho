"""Scraper para o Decanato de Extensão da UnB (DEX)."""

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

DEX_BASE_URL = "https://dex.unb.br"
DEX_EDITAIS_URL = "https://dex.unb.br/editais"
DEFAULT_TIMEOUT = 12.0
USER_AGENT = "Fique-de-Olho/1.0"

DATE_PATTERN = re.compile(
    r"\b(\d{1,2}\s+de\s+[A-Za-zÀ-ÿ]+\s+de\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})\b",
    re.IGNORECASE,
)


def parse_dex_html(html: str, base_url: str = DEX_BASE_URL) -> List[Dict[str, Any]]:
    """Extrai oportunidades e editais do portal do DEX."""
    soup = BeautifulSoup(html, "html.parser")
    editais: List[Dict[str, Any]] = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)

        if not text or len(text) < 4:
            continue

        if any(ign in text.lower() for ign in ["pular para", "governo", "regimento", "cookies"]):
            continue

        full_url = urljoin(base_url, href)

        is_edital = (
            any(k in text.lower() for k in ["edital", "pibex", "seleção", "selecao", "chamada", "bolsista"])
            or "download=" in href.lower()
            or "edital" in href.lower()
        )
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


class DEXScraper(BaseScraper):
    """Implementação do scraper para o Decanato de Extensão (DEX)."""

    @property
    def orgao_origem(self) -> str:
        return "DEX"

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Busca editais no portal do DEX."""
        try:
            resp = httpx.get(
                DEX_EDITAIS_URL,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            return parse_dex_html(resp.text, base_url=str(resp.url))
        except httpx.HTTPError:
            return []

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai links para download de arquivos de um edital do DEX."""
        if edital_url.lower().endswith(".pdf") or "download=" in edital_url.lower():
            tipo = classify_document(edital_url, edital_url)
            return [{"titulo": "Documento Oficial DEX", "link": edital_url, "tipo": tipo}]

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
            if ".pdf" in h.lower() or "download=" in h.lower():
                full_h = urljoin(str(resp.url), h)
                t = a.get_text(" ", strip=True) or "Arquivo DEX"
                documentos.append({
                    "titulo": t,
                    "link": full_h,
                    "tipo": classify_document(t, full_h),
                })
        return documentos


dex_scraper = DEXScraper()

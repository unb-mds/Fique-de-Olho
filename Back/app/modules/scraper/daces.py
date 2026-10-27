"""Scraper para a Diretoria de Acessibilidade da UnB (DACES / DAC)."""

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

DACES_BASE_URL = "https://acessibilidade.unb.br"
DEFAULT_TIMEOUT = 12.0
USER_AGENT = "Fique-de-Olho/1.0"

DATE_PATTERN = re.compile(
    r"\b(\d{1,2}\s+de\s+[A-Za-zÀ-ÿ]+\s+de\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})\b",
    re.IGNORECASE,
)


def build_daces_url(year: Optional[int] = None) -> str:
    y = year or 2026
    return f"{DACES_BASE_URL}/editais-{y}/"


def parse_daces_html(html: str, base_url: str = DACES_BASE_URL) -> List[Dict[str, Any]]:
    """Extrai os editais de acessibilidade (PTA, tutoria, ledores, etc.)."""
    soup = BeautifulSoup(html, "html.parser")
    editais: List[Dict[str, Any]] = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)

        if not text or len(text) < 4:
            continue

        if any(ign in text.lower() for ign in ["pular para", "governo", "regimento", "cookies", "mapas"]):
            continue

        full_url = urljoin(base_url, href)

        is_edital = any(k in text.lower() for k in ["edital", "abertura", "pta", "tutoria", "acessibilidade"]) or "edital" in href.lower()
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


class DACESScraper(BaseScraper):
    """Implementação do scraper para a Diretoria de Acessibilidade (DACES)."""

    @property
    def orgao_origem(self) -> str:
        return "DACES"

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Busca editais no portal da DACES para o ano informado."""
        url = build_daces_url(year)
        try:
            resp = httpx.get(
                url,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            return parse_daces_html(resp.text, base_url=str(resp.url))
        except httpx.HTTPError:
            try:
                fallback_resp = httpx.get(
                    f"{DACES_BASE_URL}/editais-2/",
                    headers={"User-Agent": USER_AGENT},
                    follow_redirects=True,
                    timeout=DEFAULT_TIMEOUT,
                )
                fallback_resp.raise_for_status()
                return parse_daces_html(fallback_resp.text, base_url=str(fallback_resp.url))
            except httpx.HTTPError:
                return []

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai anexos e resultados de um edital da DACES."""
        if edital_url.lower().endswith(".pdf"):
            return [{"titulo": "Edital Oficial DACES", "link": edital_url, "tipo": classify_document(edital_url, edital_url)}]

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
                t = a.get_text(" ", strip=True) or "Arquivo DACES"
                documentos.append({
                    "titulo": t,
                    "link": full_h,
                    "tipo": classify_document(t, full_h),
                })
        return documentos


daces_scraper = DACESScraper()

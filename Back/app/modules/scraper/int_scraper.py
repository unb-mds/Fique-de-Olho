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

GENERIC_DOC_LINK_TEXTS = {
    "baixar",
    "baixar em pdf",
    "baixar pdf",
    "aqui",
    "pdf",
    "download",
    "acesse aqui",
    "clique aqui",
}


def _is_relevant_int_link(text: str, href: str) -> bool:
    if not text or len(text) < 5:
        return False
    low_text = text.lower()
    low_href = href.lower()
    if any(ign in low_text for ign in ["pular para", "governo", "regimento", "cookies"]):
        return False
    return any(k in low_text or k in low_href for k in ["edital", "selecao", "seleção", "chamada"])


def _extract_article_resumo(article: Any, titulo: str, data_pub: str) -> Optional[str]:
    """Extrai o resumo/trecho descritivo de um card <article> da INT."""
    partes: List[str] = []
    for p in article.find_all("p"):
        txt = " ".join(p.get_text(" ", strip=True).split())
        if not txt or txt == titulo or txt == data_pub:
            continue
        if len(txt) >= 20:
            partes.append(txt)
    if partes:
        return " ".join(partes)[:600]

    full_text = " ".join(article.get_text(" ", strip=True).split())
    if titulo:
        full_text = full_text.replace(titulo, "", 1).strip()
    if data_pub:
        full_text = full_text.replace(data_pub, "", 1).strip()
    return full_text[:600] if len(full_text) >= 20 else None


def parse_int_html(html: str, base_url: str = INT_BASE_URL) -> List[Dict[str, Any]]:
    """Extrai editais da listagem de seleções abertas da INT, incluindo data e resumo."""
    soup = BeautifulSoup(html, "html.parser")
    editais: List[Dict[str, Any]] = []
    seen = set()

    # Primeiro percorre cards <article> (estrutura real do WordPress da INT)
    for article in soup.find_all("article"):
        link_el = None
        for a in article.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(" ", strip=True)
            if _is_relevant_int_link(text, href):
                link_el = a
                break
        if link_el is None:
            continue

        href = link_el["href"].strip()
        text = link_el.get_text(" ", strip=True)
        full_url = urljoin(base_url, href)
        if full_url in seen:
            continue
        seen.add(full_url)

        article_text = article.get_text(" ", strip=True)
        date_match = DATE_PATTERN.search(article_text)
        data_pub = date_match.group(0) if date_match else ""
        resumo = _extract_article_resumo(article, text, data_pub)

        item: Dict[str, Any] = {
            "titulo": text,
            "link": full_url,
            "data_publicacao": data_pub,
        }
        if resumo:
            item["resumo"] = resumo
        editais.append(item)

    if editais:
        return editais

    # Fallback para páginas/HTML simplificados sem <article>
    content = soup.select_one(".entry-content, article, main") or soup
    for a in content.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)
        if not _is_relevant_int_link(text, href):
            continue

        full_url = urljoin(base_url, href)
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


def _is_int_document_href(href: str) -> bool:
    low = href.lower()
    return ".pdf" in low or "sei.unb.br/sei/publicacoes/" in low


def _extract_doc_title(anchor: Any) -> str:
    """Recupera o rótulo real do documento quando o link tem texto genérico ('baixar em PDF', 'aqui')."""
    text = " ".join(anchor.get_text(" ", strip=True).split())
    if text and text.lower() not in GENERIC_DOC_LINK_TEXTS:
        return text

    parent = anchor.find_parent(["li", "p", "tr"])
    if parent is not None:
        parent_text = " ".join(parent.get_text(" ", strip=True).split())
        cleaned = re.sub(r"\(\s*baixar\s+em\s+pdf\s*\)", "", parent_text, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*[–-]\s*$", "", cleaned).strip()
        if cleaned and len(cleaned) <= 220:
            return cleaned

    return text or "Documento Anexo"


def parse_int_documentos(html: str, base_url: str = INT_BASE_URL) -> List[Dict[str, Any]]:
    """Extrai PDFs e publicações oficiais do SEI vinculados à página de seleção da INT."""
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one(".entry-content, article, main") or soup
    documentos: List[Dict[str, Any]] = []
    seen = set()

    for a in content.find_all("a", href=True):
        h = a["href"].strip()
        if not _is_int_document_href(h):
            continue
        full_h = urljoin(base_url, h)
        if full_h in seen:
            continue
        seen.add(full_h)
        t = _extract_doc_title(a)
        documentos.append({
            "titulo": t,
            "link": full_h,
            "tipo": classify_document(t, full_h),
        })
    return documentos


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

        return parse_int_documentos(resp.text, base_url=str(resp.url))


int_scraper = INTScraper()

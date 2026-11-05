"""Scraper para os editais, regras de bolsistas e processos seletivos do UnB Idiomas."""

import html
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

logger = logging.getLogger(__name__)

UNB_IDIOMAS_BASE_URL = "https://unbidiomas.unb.br"
UNB_IDIOMAS_MEDIA_API = f"{UNB_IDIOMAS_BASE_URL}/wp-json/wp/v2/media?mime_type=application/pdf&per_page=100"
UNB_IDIOMAS_POSTS_API = f"{UNB_IDIOMAS_BASE_URL}/wp-json/wp/v2/posts?search=edital&per_page=50"

DEFAULT_TIMEOUT = 15.0
USER_AGENT = "Fique-de-Olho/1.0"

EDITAL_KEYWORDS = [
    "edital",
    "bolsista",
    "bolsa",
    "norma",
    "orientacoes",
    "competencia-leitora",
    "competência leitora",
    "selecao",
    "seleção",
    "exame",
]


def is_edital_title_or_slug(title: str, slug: str) -> bool:
    """Verifica se um título ou slug do WordPress se refere a um edital ou seleção do UnB Idiomas."""
    combined = f"{title} {slug}".lower()
    return any(k in combined for k in EDITAL_KEYWORDS)


def clean_title(title_raw: str) -> str:
    """Limpa entidades HTML e pontuações do título."""
    unescaped = html.unescape(title_raw or "")
    unescaped = unescaped.replace("&#8211;", "–").replace("&#8217;", "'")
    return unescaped.strip()


class UnBIdiomasScraper(BaseScraper):
    """Implementação do scraper para editais e seleções do UnB Idiomas."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self._url_to_docs_cache: Dict[str, List[Dict[str, Any]]] = {}

    @property
    def orgao_origem(self) -> str:
        return "UNB_IDIOMAS"

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Busca todos os editais e chamadas de bolsistas do UnB Idiomas."""
        editais: List[Dict[str, Any]] = []
        seen_links = set()

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                # 1. Coleta a partir da API de mídia (documentos PDF diretos)
                try:
                    resp_media = client.get(UNB_IDIOMAS_MEDIA_API)
                    if resp_media.status_code == 200:
                        media_items = resp_media.json()
                        if isinstance(media_items, list):
                            for it in media_items:
                                title = clean_title(it.get("title", {}).get("rendered", ""))
                                slug = it.get("slug", "")
                                source_url = it.get("source_url", "")

                                if not source_url or source_url in seen_links:
                                    continue

                                if not is_edital_title_or_slug(title, slug):
                                    continue

                                date_str = (it.get("date") or "")[:10]
                                ano_edital: Optional[int] = None
                                if date_str and len(date_str) >= 4 and date_str[:4].isdigit():
                                    ano_edital = int(date_str[:4])

                                if year is not None and ano_edital is not None and ano_edital != year:
                                    continue

                                seen_links.add(source_url)
                                edital_dict = {
                                    "titulo": title or "Edital UnB Idiomas",
                                    "link": source_url,
                                    "data_publicacao": date_str,
                                    "ano": ano_edital,
                                    "tipo": "documento_pdf",
                                    "status": "aberto" if (ano_edital and ano_edital >= 2026) else "fechado",
                                }
                                self._url_to_docs_cache[source_url] = [{
                                    "titulo": title or "Edital Oficial UnB Idiomas",
                                    "link": source_url,
                                    "tipo": classify_document(title, source_url),
                                }]
                                editais.append(edital_dict)
                except httpx.HTTPError as exc:
                    logger.warning(f"Erro ao consultar API de mídia do UnB Idiomas: {exc}")

                # 2. Coleta a partir de posts publicados
                try:
                    resp_posts = client.get(UNB_IDIOMAS_POSTS_API)
                    if resp_posts.status_code == 200:
                        posts = resp_posts.json()
                        if isinstance(posts, list):
                            for p in posts:
                                title = clean_title(p.get("title", {}).get("rendered", ""))
                                link = p.get("link", "")
                                if not link or link in seen_links:
                                    continue

                                date_str = (p.get("date") or "")[:10]
                                ano_edital: Optional[int] = None
                                if date_str and len(date_str) >= 4 and date_str[:4].isdigit():
                                    ano_edital = int(date_str[:4])

                                if year is not None and ano_edital is not None and ano_edital != year:
                                    continue

                                seen_links.add(link)
                                editais.append({
                                    "titulo": title,
                                    "assunto": f"Cursos e Editais de Línguas Estrangeiras - {title}",
                                    "tipo": "Cursos de Idiomas",
                                    "tipo_edital": "Cursos de Idiomas",
                                    "descricao": f"Chamada pública e avisos de cursos de línguas estrangeiras oferecidos pelo UnB Idiomas: {title}.",
                                    "resumo": f"Chamada pública e avisos de cursos de línguas estrangeiras oferecidos pelo UnB Idiomas: {title}.",
                                    "link": link,
                                    "data_publicacao": date_str,
                                    "ano": ano_edital,
                                    "status": "aberto" if (ano_edital and ano_edital >= 2026) else "fechado",
                                })
                except httpx.HTTPError as exc:
                    logger.warning(f"Erro ao consultar API de posts do UnB Idiomas: {exc}")

        except Exception as exc:
            logger.error(f"Erro geral no scraper do UnB Idiomas: {exc}")
            return editais

        return editais

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai os documentos PDF associados a um edital do UnB Idiomas."""
        if edital_url in self._url_to_docs_cache:
            return self._url_to_docs_cache[edital_url]

        if edital_url.lower().endswith(".pdf"):
            return [{
                "titulo": "Edital Oficial UnB Idiomas",
                "link": edital_url,
                "tipo": classify_document(edital_url, edital_url),
            }]

        documentos: List[Dict[str, Any]] = []
        seen = set()

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                resp = client.get(edital_url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for a in soup.find_all("a", href=True):
                        h = a["href"].strip()
                        if ".pdf" in h.lower():
                            full_h = urljoin(str(resp.url), h)
                            if full_h in seen:
                                continue
                            seen.add(full_h)
                            t = clean_title(a.get_text(" ", strip=True)) or "Anexo UnB Idiomas"
                            documentos.append({
                                "titulo": t,
                                "link": full_h,
                                "tipo": classify_document(t, full_h),
                            })
        except Exception as exc:
            logger.error(f"Erro ao extrair documentos de {edital_url} no UnB Idiomas: {exc}")

        return documentos


unb_idiomas_scraper = UnBIdiomasScraper()

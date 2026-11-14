import html as html_lib
import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

logger = logging.getLogger(__name__)


class DOUScraper(BaseScraper):
    """
    Scraper para o Diário Oficial da União (DOU) — Seção 3 — filtrado para
    "Fundação Universidade de Brasília" (FUB / UnB).

    Estratégia:
    1. Consulta pública oficial de busca do portal da Imprensa Nacional:
       `https://www.in.gov.br/consulta/-/buscar/dou` com parâmetros:
       - `q='"Fundação Universidade de Brasília"'`
       - `s='do3'` (Seção 3: Editais, Avisos de Licitação, Contratos, Convênios, Concursos)
       - `exactDate='ano'`, `sortType='0'`
    2. Extrai os itens estruturados do bloco JSON oficial do Liferay
       (`<script id="_br_com_seatecnologia_in_buscadou_BuscaDouPortlet_params">`, chave `jsonArray`),
       com fallback para cartões HTML de resultados (`a[href*="/web/dou/-/"]`).
    3. Resiliência estrita contra bloqueios WAF (`HTTP 403 Forbidden`), `429`, `5xx` ou timeouts:
       nunca tenta contornar bloqueios anti-bot/CAPTCHA; registra `logger.warning` e retorna
       lista vazia de forma segura para não interromper `run_periodic_pipeline` ou `sync_all_portais`.
    """

    BASE_URL = "https://www.in.gov.br"
    SEARCH_URL = "https://www.in.gov.br/consulta/-/buscar/dou"
    DETAIL_BASE_URL = "https://www.in.gov.br/web/dou/-/"
    DEFAULT_QUERY = '"Fundação Universidade de Brasília"'
    DEFAULT_SECTION = "do3"

    PORTLET_SCRIPT_ID = "_br_com_seatecnologia_in_buscadou_BuscaDouPortlet_params"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    def __init__(
        self,
        timeout: float = 20.0,
        cache_ttl: float = 300.0,
        search_query: str = DEFAULT_QUERY,
        section: str = DEFAULT_SECTION,
    ):
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.search_query = search_query
        self.section = section
        self._cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        self._docs_by_page: Dict[str, List[Dict[str, str]]] = {}

    @property
    def orgao_origem(self) -> str:
        return "DOU"

    def clear_cache(self) -> None:
        """Limpa o cache em memória do scraper."""
        self._cache.clear()
        self._docs_by_page.clear()

    def _get_client(self, timeout: Optional[float] = None) -> httpx.Client:
        return httpx.Client(
            timeout=timeout or self.timeout,
            follow_redirects=True,
            headers=self.DEFAULT_HEADERS,
        )

    @staticmethod
    def _clean_text(text: str) -> str:
        if not text:
            return ""
        unescaped = html_lib.unescape(text)
        cleaned = re.sub(r"<[^>]+>", " ", unescaped)
        return re.sub(r"\s+", " ", cleaned).strip()

    @classmethod
    def _parse_pub_date(cls, raw_date: str) -> Tuple[str, Optional[int]]:
        if not raw_date:
            now = datetime.now()
            return now.strftime("%Y-%m-%d"), now.year
        raw_date = raw_date.strip()
        # Formato DD/MM/YYYY ou DD-MM-YYYY
        m_br = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](20\d{2})$", raw_date)
        if m_br:
            try:
                dt = datetime(int(m_br.group(3)), int(m_br.group(2)), int(m_br.group(1)))
                return dt.strftime("%Y-%m-%d"), dt.year
            except ValueError:
                pass
        # Formato YYYY-MM-DD
        m_iso = re.match(r"^(20\d{2})-(\d{2})-(\d{2})", raw_date)
        if m_iso:
            return f"{m_iso.group(1)}-{m_iso.group(2)}-{m_iso.group(3)}", int(m_iso.group(1))
        now = datetime.now()
        return now.strftime("%Y-%m-%d"), now.year

    @classmethod
    def _extract_year(cls, *texts: Optional[str]) -> Optional[int]:
        for text in texts:
            if not text:
                continue
            m_ed = re.search(r"\b\d{1,5}\s*[/\-]\s*(20\d{2})\b", text)
            if m_ed:
                return int(m_ed.group(1))
            years = [int(m) for m in re.findall(r"\b(20\d{2})\b", text) if 2018 <= int(m) <= 2030]
            if years:
                return max(years)
        return None

    @staticmethod
    def _infer_status(art_type: str, title: str, content: str = "") -> str:
        combined = f"{art_type} {title} {content}".lower()
        if any(
            k in combined
            for k in (
                "resultado final",
                "resultado de julgamento",
                "homologação",
                "homologacao",
                "extrato de contrato",
                "extrato de termo aditivo",
                "extrato de apostilamento",
            )
        ):
            return "fechado"
        return "aberto"

    @classmethod
    def _make_doc(cls, title: str, url: str) -> Dict[str, str]:
        clean_title = cls._clean_text(title) or "Publicação Oficial no DOU"
        doc_type = classify_document(clean_title, url)
        return {
            "titulo": clean_title,
            "link": url,
            "url_pdf": url,
            "tipo": doc_type,
            "tipo_documento": doc_type,
        }

    def _build_edital_from_json_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        raw_title = self._clean_text(str(item.get("title") or ""))
        url_title = str(item.get("urlTitle") or "").strip().lstrip("/")
        if not raw_title or not url_title:
            return None

        art_type = self._clean_text(str(item.get("artType") or "Publicação DOU Seção 3"))
        pub_date_raw = str(item.get("pubDate") or "")
        pub_date_iso, pub_year = self._parse_pub_date(pub_date_raw)
        content_snippet = self._clean_text(str(item.get("content") or ""))
        hierarchy = self._clean_text(str(item.get("hierarchyStr") or "Fundação Universidade de Brasília"))
        edition_num = self._clean_text(str(item.get("editionNumber") or ""))
        page_num = self._clean_text(str(item.get("numberPage") or ""))

        # Garante que pertence à Fundação Universidade de Brasília / FUB / UnB
        combined_check = f"{hierarchy} {raw_title} {content_snippet}".lower()
        if not any(
            kw in combined_check
            for kw in ("universidade de brasília", "universidade de brasilia", "fub", "unb", "154040")
        ):
            return None

        detail_url = f"{self.DETAIL_BASE_URL}{url_title}"
        ano = pub_year or self._extract_year(raw_title, content_snippet)

        # Link oficial de leitura do jornal na data/seção
        br_date_dash = pub_date_raw.replace("/", "-") if "/" in pub_date_raw else pub_date_iso
        jornal_url = f"{self.BASE_URL}/leiturajornal?data={br_date_dash}&secao=DO3"

        doc = self._make_doc(f"{raw_title} (DOU Seção 3)", detail_url)
        docs = [doc]
        self._docs_by_page[detail_url] = docs

        meta_parts = ["DOU Seção 3"]
        if edition_num:
            meta_parts.append(f"Edição {edition_num}")
        if page_num:
            meta_parts.append(f"Página {page_num}")
        if hierarchy:
            meta_parts.append(hierarchy)
        resumo = f"{' | '.join(meta_parts)} — {content_snippet}" if content_snippet else " | ".join(meta_parts)

        # Identificador único baseado no ID numérico final do urlTitle ou no próprio urlTitle
        m_id = re.search(r"-(\d{6,})$", url_title)
        item_id = m_id.group(1) if m_id else re.sub(r"[^a-z0-9]+", "-", url_title.lower()).strip("-")[:55]

        return {
            "identificador_origem": f"dou-s3-{item_id}",
            "titulo": raw_title,
            "link": detail_url,
            "url_pagina": detail_url,
            "url_pdf": None,
            "url_jornal": jornal_url,
            "orgao_origem": self.orgao_origem,
            "orgao_emissor": self.orgao_origem,
            "campus": "Darcy Ribeiro",
            "tipo": art_type,
            "categoria": art_type,
            "assunto": art_type,
            "resumo": resumo[:800],
            "descricao": resumo[:800],
            "status": self._infer_status(art_type, raw_title, content_snippet),
            "data_publicacao": pub_date_iso,
            "inicio_inscricao": None,
            "fim_inscricao": None,
            "ano": ano,
            "documentos": docs,
        }

    def _parse_search_html(self, html: str) -> List[Dict[str, Any]]:
        """
        Extrai publicações da página de busca do DOU via `<script id="...BuscaDouPortlet_params">`
        com fallback para links HTML `/web/dou/-/...`.
        """
        if not html or not html.strip():
            return []

        soup = BeautifulSoup(html, "html.parser")
        results: List[Dict[str, Any]] = []
        seen_urls: Set[str] = set()

        # 1. Extração via script JSON do portlet de busca do DOU
        script_tag = soup.find("script", id=self.PORTLET_SCRIPT_ID)
        if script_tag and script_tag.string:
            try:
                data = json.loads(script_tag.string.strip())
                json_array = data.get("jsonArray", [])
                if isinstance(json_array, list):
                    for raw_item in json_array:
                        if not isinstance(raw_item, dict):
                            continue
                        parsed = self._build_edital_from_json_item(raw_item)
                        if parsed and parsed["link"] not in seen_urls:
                            seen_urls.add(parsed["link"])
                            results.append(parsed)
            except Exception as e:
                logger.warning(f"Falha ao decodificar JSON do portlet de busca do DOU: {e}")

        if results:
            return results

        # 2. Fallback HTML: links diretos para `/web/dou/-/`
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if "/web/dou/-/" not in href:
                continue
            full_url = urljoin(self.BASE_URL, href)
            if full_url in seen_urls:
                continue

            title = self._clean_text(a_tag.get_text(" ", strip=True))
            if not title:
                continue

            container = a_tag.find_parent(["div", "article", "li"]) or a_tag.parent
            context = self._clean_text(container.get_text(" ", strip=True)) if container else title

            m_date = re.search(r"\b(\d{2}/\d{2}/20\d{2})\b", context)
            pub_date_iso, pub_year = self._parse_pub_date(m_date.group(1) if m_date else "")
            ano = self._extract_year(title, context) or pub_year

            url_slug = full_url.split("/web/dou/-/")[-1].strip("/")
            m_id = re.search(r"-(\d{6,})$", url_slug)
            item_id = m_id.group(1) if m_id else re.sub(r"[^a-z0-9]+", "-", url_slug.lower()).strip("-")[:55]

            doc = self._make_doc(f"{title} (DOU Seção 3)", full_url)
            docs = [doc]
            self._docs_by_page[full_url] = docs
            seen_urls.add(full_url)

            results.append(
                {
                    "identificador_origem": f"dou-s3-{item_id}",
                    "titulo": title,
                    "link": full_url,
                    "url_pagina": full_url,
                    "url_pdf": None,
                    "orgao_origem": self.orgao_origem,
                    "orgao_emissor": self.orgao_origem,
                    "campus": "Darcy Ribeiro",
                    "tipo": "Publicação DOU Seção 3",
                    "categoria": "Publicação DOU Seção 3",
                    "assunto": "Publicação DOU Seção 3",
                    "resumo": context[:800],
                    "descricao": context[:800],
                    "status": self._infer_status("", title, context),
                    "data_publicacao": pub_date_iso,
                    "inicio_inscricao": None,
                    "fim_inscricao": None,
                    "ano": ano,
                    "documentos": docs,
                }
            )

        return results

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Consulta a Seção 3 do Diário Oficial da União filtrando por
        "Fundação Universidade de Brasília". Em caso de bloqueio WAF (403),
        erro HTTP (5xx) ou timeout, registra warning e retorna `[]`.
        """
        cache_key = f"editais:{year if year is not None else 'all'}"
        now = time.time()
        if cache_key in self._cache:
            ts, cached = self._cache[cache_key]
            if now - ts < self.cache_ttl:
                return [dict(item) for item in cached]

        params = {
            "q": self.search_query,
            "s": self.section,
            "exactDate": "ano",
            "sortType": "0",
        }

        try:
            with self._get_client() as client:
                resp = client.get(self.SEARCH_URL, params=params)
                if resp.status_code == 403:
                    logger.warning(
                        "Consulta ao DOU (in.gov.br) bloqueada por WAF/anti-bot (HTTP 403 Forbidden). "
                        "Retornando lista vazia com segurança."
                    )
                    return []
                if resp.status_code != 200:
                    logger.warning(
                        f"Consulta ao DOU (in.gov.br) retornou HTTP {resp.status_code}. "
                        "Retornando lista vazia."
                    )
                    return []
                html_text = resp.text
        except httpx.TimeoutException as e:
            logger.warning(f"Timeout ao consultar o portal do DOU (in.gov.br): {e}")
            return []
        except Exception as e:
            logger.warning(f"Erro ao consultar o portal do DOU (in.gov.br): {e}")
            return []

        results = self._parse_search_html(html_text)
        if year is not None:
            results = [item for item in results if item.get("ano") == year]

        self._cache[cache_key] = (now, [dict(item) for item in results])
        return results

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """
        Extrai links de documentos PDF ou versões certificadas da página de uma publicação do DOU.
        """
        if not edital_url:
            return []

        if edital_url in self._docs_by_page and self._docs_by_page[edital_url]:
            return [dict(d) for d in self._docs_by_page[edital_url]]

        if edital_url.lower().split("?")[0].endswith(".pdf"):
            filename = edital_url.rstrip("/").split("/")[-1]
            return [self._make_doc(filename, edital_url)]

        try:
            with self._get_client() as client:
                resp = client.get(edital_url)
                if resp.status_code in (403, 429) or resp.status_code >= 400:
                    logger.warning(f"Detalhe do DOU ({edital_url}) retornou HTTP {resp.status_code}.")
                    return []
        except Exception as e:
            logger.warning(f"Erro ao buscar documentos da publicação DOU ({edital_url}): {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        docs: List[Dict[str, str]] = []
        seen: Set[str] = set()

        for a_tag in soup.find_all("a", href=True):
            href = urljoin(edital_url, a_tag["href"].strip())
            low = href.lower()
            if (low.split("?")[0].endswith(".pdf") or ("leiturajornal?" in low and "data=" in low)) and href not in seen:
                seen.add(href)
                label = self._clean_text(a_tag.get_text(" ", strip=True)) or "Edição Completa DOU (Seção 3)"
                docs.append(self._make_doc(label, href))

        if not docs:
            title_tag = soup.select_one(".identifica, h1, title")
            label = self._clean_text(title_tag.get_text(" ", strip=True)) if title_tag else "Publicação Oficial no DOU"
            docs.append(self._make_doc(label, edital_url))

        self._docs_by_page[edital_url] = docs
        return [dict(d) for d in docs]

    def download_documento(self, url: str, timeout: float = 15.0) -> bytes:
        with self._get_client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content


dou_scraper = DOUScraper()

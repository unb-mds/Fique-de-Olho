import html as html_lib
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

logger = logging.getLogger(__name__)


class PPGContScraper(BaseScraper):
    """
    Scraper para o portal do Programa de Pós-Graduação em Ciências Contábeis (PPGCont/FACE/UnB).
    URL base: https://ppgcont.unb.br/

    Estratégia combinada:
    1. Raspagem das páginas oficiais de editais e seleções (`/editais-internos/`,
       `/aluno-regular/`, `/processo-seletivo-2027-ingresso-em-2027/` e páginas
       de processos seletivos descobertas dinamicamente).
    2. Consulta à API REST do WordPress (`/wp-json/wp/v2/posts` e `/pages`) com
       filtro semântico para capturar novos editais, chamadas, processos seletivos
       de mestrado/doutorado, retificações e resultados, ignorando documentos
       administrativos estáticos (planejamento estratégico, formulários gerais, regimentos).
    """

    BASE_URL = "https://ppgcont.unb.br"
    EDITAIS_INTERNOS_URL = "https://ppgcont.unb.br/editais-internos/"
    ALUNO_REGULAR_URL = "https://ppgcont.unb.br/aluno-regular/"
    PROCESSO_SELETIVO_2027_URL = "https://ppgcont.unb.br/processo-seletivo-2027-ingresso-em-2027/"

    WP_POSTS_API_URL = "https://ppgcont.unb.br/wp-json/wp/v2/posts"
    WP_PAGES_API_URL = "https://ppgcont.unb.br/wp-json/wp/v2/pages"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    EDITAL_KEYWORDS = (
        "edital",
        "chamada",
        "processo seletivo",
        "seleção",
        "selecao",
        "aluno regular",
        "aluno especial",
        "bolsa",
        "fomento",
        "fapdf",
        "fap-df",
        "homologação",
        "homologacao",
        "resultado",
        "retificação",
        "retificacao",
        "adendo",
        "convocação",
        "convocacao",
        "isenção",
        "isencao",
    )

    EXCLUDED_KEYWORDS = (
        "planejamento estratégico",
        "planejamento estrategico",
        "planejamento_ppgcont",
        "regimento",
        "estatuto",
        "resolução",
        "resolucao",
        "formulário de marcação",
        "formulario de marcacao",
        "formulario-de-marcarcao",
        "orientações para marcar",
        "orientacoes-para-marcar",
        "trancamento_justificado",
        "formulario_de_registro",
        "exposicao_motivos",
        "lista de oferta",
        "lista_202",
        "corpo docente",
        "quem somos",
        "histórico",
        "historico",
    )

    IGNORED_STATIC_SLUGS = {
        "editais-internos",
        "aluno-regular",
        "aluno-especial",
        "pos-doutorado",
        "dissertacoes-e-teses",
        "planejamento-estrategico",
        "regimentos-e-normas",
        "formularios",
        "corpo-docente",
        "contato",
    }

    def __init__(self, timeout: float = 20.0, cache_ttl: float = 300.0, max_pages: int = 2):
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.max_pages = max_pages
        self._cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        self._docs_by_page: Dict[str, List[Dict[str, str]]] = {}

    @property
    def orgao_origem(self) -> str:
        return "PPGCONT"

    def clear_cache(self) -> None:
        """Limpa o cache em memória do scraper."""
        self._cache.clear()
        self._docs_by_page.clear()

    def _get_cached(self, key: str) -> Optional[List[Dict[str, Any]]]:
        entry = self._cache.get(key)
        if not entry:
            return None
        ts, data = entry
        if (time.monotonic() - ts) > self.cache_ttl:
            del self._cache[key]
            return None
        return [dict(item) for item in data]

    def _set_cached(self, key: str, data: List[Dict[str, Any]]) -> None:
        self._cache[key] = (time.monotonic(), [dict(item) for item in data])

    @staticmethod
    def _clean_text(text: str) -> str:
        if not text:
            return ""
        unescaped = html_lib.unescape(text)
        cleaned = BeautifulSoup(unescaped, "html.parser").get_text(" ", strip=True)
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    def _is_pdf_url(href: str) -> bool:
        if not href:
            return False
        parsed = urlparse(href.strip())
        path = (parsed.path or "").lower()
        return path.endswith(".pdf") or ".pdf" in path

    @staticmethod
    def _is_followup_doc(label: str) -> bool:
        norm = (label or "").lower()
        return any(
            kw in norm
            for kw in (
                "adendo",
                "retificação",
                "retificacao",
                "resultado",
                "homologação",
                "homologacao",
                "convocação",
                "convocacao",
                "orientação",
                "orientacao",
                "isenção",
                "isencao",
                "prorrogação",
                "prorrogacao",
                "edital dpg",
                "anexo",
            )
        )

    @classmethod
    def _is_relevant_edital(cls, title: str, text: str = "", url: str = "") -> bool:
        title_lower = (title or "").lower()
        url_lower = (url or "").lower()

        if any(excl in title_lower or excl in url_lower for excl in cls.EXCLUDED_KEYWORDS):
            return False

        return any(kw in title_lower or kw in url_lower for kw in cls.EDITAL_KEYWORDS)

    @staticmethod
    def _extract_year(text: str, url: str = "", fallback_date: Optional[str] = None) -> Optional[int]:
        combined = f"{text or ''} {url or ''}"
        for pattern in (
            r"\b(?:n[º°o\.]?\s*\d+\s*/\s*)(20\d{2})\b",
            r"\b\d{1,3}\s*/\s*(20\d{2})\b",
            r"/uploads/(20\d{2})/",
            r"\b(20\d{2})\b",
        ):
            m = re.search(pattern, combined, re.IGNORECASE)
            if m:
                year_val = int(m.group(1))
                if 2000 <= year_val <= 2100:
                    return year_val

        if fallback_date and len(fallback_date) >= 4 and fallback_date[:4].isdigit():
            return int(fallback_date[:4])
        return None

    @staticmethod
    def _extract_date_from_text_or_url(text: str, url: str = "") -> Optional[str]:
        m = re.search(r"\b(\d{2})/(\d{2})/(20\d{2})\b", text or "")
        if m:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= day <= 31 and 1 <= month <= 12:
                return f"{year:04d}-{month:02d}-{day:02d}"

        m_upload = re.search(r"/uploads/(20\d{2})/(\d{2})/", url or "")
        if m_upload:
            year, month = int(m_upload.group(1)), int(m_upload.group(2))
            if 1 <= month <= 12:
                return f"{year:04d}-{month:02d}-01"
        return None

    @staticmethod
    def _infer_categoria(title: str, text: str = "") -> str:
        norm = f"{title} {text}".lower()
        if "fapdf" in norm or "fap-df" in norm or "fomento" in norm or "pesquisa" in norm or "apoio" in norm:
            return "pesquisa"
        if "bolsa" in norm or "auxílio" in norm or "auxilio" in norm:
            return "bolsa"
        return "pos-graduacao"

    @staticmethod
    def _infer_status(title: str, text: str = "", doc_types: Optional[List[str]] = None) -> str:
        norm = f"{title} {text}".lower()
        if doc_types and "resultado_final" in doc_types and "processo seletivo 2027" not in norm:
            return "fechado"
        if "encerrad" in norm or "finalizad" in norm:
            return "fechado"
        return "aberto"

    @staticmethod
    def _make_doc(url_pdf: str, label: str = "") -> Dict[str, str]:
        filename = urlparse(url_pdf).path.rsplit("/", 1)[-1]
        classification_hint = f"{label} {filename}".strip()
        if any(k in classification_hint.lower() for k in ("preliminar", "homologacao", "homologação", "isencao", "isenção")):
            classification_hint = f"{classification_hint} provisório"
        elif any(k in classification_hint.lower() for k in ("adendo", "prorrogacao", "prorrogação")):
            classification_hint = f"{classification_hint} retificação"
        tipo_doc = classify_document(classification_hint, url_pdf)
        return {
            "titulo": label or filename or "Documento PDF",
            "link": url_pdf,
            "url_pdf": url_pdf,
            "tipo": tipo_doc,
            "tipo_documento": tipo_doc,
        }

    def _extract_pdf_docs_from_container(self, container: Optional[Tag], base_url: str) -> List[Dict[str, str]]:
        if container is None:
            return []
        docs: List[Dict[str, str]] = []
        seen_urls: Set[str] = set()

        for a_tag in container.find_all("a", href=True):
            href = (a_tag.get("href") or "").strip()
            if not self._is_pdf_url(href):
                continue
            full_url = urljoin(base_url, href)
            if full_url in seen_urls:
                continue
            label = self._clean_text(a_tag.get_text(" ", strip=True))
            if any(excl in f"{label} {full_url}".lower() for excl in self.EXCLUDED_KEYWORDS):
                continue
            seen_urls.add(full_url)
            docs.append(self._make_doc(full_url, label))
        return docs

    def _scrape_editais_internos_page(self, client: httpx.Client) -> List[Dict[str, Any]]:
        """
        Extrai e agrupa os editais da página `/editais-internos/`, associando adendos,
        editais complementares e resultados finais ao respectivo edital de abertura.
        """
        results: List[Dict[str, Any]] = []
        try:
            response = client.get(self.EDITAIS_INTERNOS_URL)
            response.raise_for_status()
        except Exception as exc:
            logger.warning("Falha ao acessar página de editais internos do PPGCont (%s): %s", self.EDITAIS_INTERNOS_URL, exc)
            return results

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup.select("header, footer, nav, script, style"):
            tag.decompose()

        groups: List[Dict[str, Any]] = []
        pending_followups: List[Dict[str, str]] = []
        seen_urls: Set[str] = set()

        for a_tag in soup.find_all("a", href=True):
            href = (a_tag.get("href") or "").strip()
            if not self._is_pdf_url(href):
                continue
            full_url = urljoin(self.EDITAIS_INTERNOS_URL, href)
            if full_url in seen_urls:
                continue
            label = self._clean_text(a_tag.get_text(" ", strip=True))
            if not label or any(excl in f"{label} {full_url}".lower() for excl in self.EXCLUDED_KEYWORDS):
                continue

            seen_urls.add(full_url)
            doc_entry = self._make_doc(full_url, label)

            if self._is_followup_doc(label):
                if groups:
                    groups[-1]["documentos"].append(doc_entry)
                else:
                    pending_followups.append(doc_entry)
            else:
                doc_entry["tipo"] = "original"
                doc_entry["tipo_documento"] = "original"
                docs_list = [doc_entry] + pending_followups
                pending_followups = []
                groups.append(
                    {
                        "titulo": label,
                        "url_pdf": full_url,
                        "documentos": docs_list,
                    }
                )

        if pending_followups and groups:
            groups[-1]["documentos"].extend(pending_followups)

        for idx, grp in enumerate(groups, start=1):
            titulo = grp["titulo"]
            url_pdf = grp["url_pdf"]
            docs = grp["documentos"]
            data_pub = self._extract_date_from_text_or_url(titulo, url_pdf)
            year_val = self._extract_year(titulo, url_pdf, data_pub)
            slug = re.sub(r"[^a-z0-9]+", "-", titulo.lower()).strip("-")[:45] or f"interno-{idx}"
            page_anchor = f"{self.EDITAIS_INTERNOS_URL}#{slug}"
            self._docs_by_page[page_anchor] = docs
            self._docs_by_page[self.EDITAIS_INTERNOS_URL] = (
                self._docs_by_page.get(self.EDITAIS_INTERNOS_URL, []) + docs
            )

            doc_types = [d["tipo_documento"] for d in docs]
            categoria = self._infer_categoria(titulo)

            results.append(
                {
                    "identificador_origem": f"PPGCONT-INTERNO-{slug}",
                    "titulo": titulo,
                    "resumo": f"{titulo} — Programa de Pós-Graduação em Ciências Contábeis (PPGCont/FACE/UnB).",
                    "descricao": f"{titulo} — Programa de Pós-Graduação em Ciências Contábeis (PPGCont/FACE/UnB).",
                    "texto_completo": titulo,
                    "link": self.EDITAIS_INTERNOS_URL,
                    "url_pagina": self.EDITAIS_INTERNOS_URL,
                    "url_pdf": url_pdf,
                    "orgao_origem": self.orgao_origem,
                    "orgao_emissor": self.orgao_origem,
                    "campus": "Darcy Ribeiro",
                    "tipo": categoria,
                    "categoria": categoria,
                    "assunto": categoria,
                    "ano": year_val,
                    "data_publicacao": data_pub,
                    "inicio_inscricao": None,
                    "fim_inscricao": None,
                    "status": self._infer_status(titulo, doc_types=doc_types),
                    "documentos": docs,
                }
            )

        return results

    def _scrape_processo_seletivo_page(self, client: httpx.Client, page_url: str, default_title: str = "") -> Optional[Dict[str, Any]]:
        """
        Extrai todos os documentos (edital de abertura, retificações, isenção,
        homologações e convocações) de uma página dedicada de processo seletivo.
        """
        try:
            response = client.get(page_url)
            response.raise_for_status()
        except Exception as exc:
            logger.warning("Falha ao acessar página de processo seletivo PPGCont (%s): %s", page_url, exc)
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        h1_tag = soup.find(["h1", "h2"])
        page_title = self._clean_text(h1_tag.get_text(" ", strip=True)) if h1_tag else default_title
        if not page_title or page_title.lower() in ("ppgcont", "aluno regular"):
            page_title = default_title or "Processo Seletivo Aluno Regular PPGCont"

        for tag in soup.select("header, footer, nav, script, style"):
            tag.decompose()

        docs = self._extract_pdf_docs_from_container(soup, page_url)
        if not docs:
            return None

        self._docs_by_page[page_url] = docs
        url_pdf = docs[0]["url_pdf"]
        for d in docs:
            if d["tipo_documento"] == "original":
                url_pdf = d["url_pdf"]
                break

        body_text = self._clean_text(soup.get_text(" ", strip=True))
        data_pub = self._extract_date_from_text_or_url(body_text, url_pdf)
        year_val = self._extract_year(f"{page_title} { docs[0]['titulo'] }", url_pdf, data_pub)
        slug = urlparse(page_url).path.strip("/").split("/")[-1] or "processo-seletivo"
        doc_types = [d["tipo_documento"] for d in docs]

        return {
            "identificador_origem": f"PPGCONT-PS-{slug[:50]}",
            "titulo": page_title,
            "resumo": body_text[:400] if body_text else page_title,
            "descricao": body_text[:400] if body_text else page_title,
            "texto_completo": body_text[:2500] if body_text else page_title,
            "link": page_url,
            "url_pagina": page_url,
            "url_pdf": url_pdf,
            "orgao_origem": self.orgao_origem,
            "orgao_emissor": self.orgao_origem,
            "campus": "Darcy Ribeiro",
            "tipo": "pos-graduacao",
            "categoria": "pos-graduacao",
            "assunto": "pos-graduacao",
            "ano": year_val,
            "data_publicacao": data_pub,
            "inicio_inscricao": None,
            "fim_inscricao": None,
            "status": self._infer_status(page_title, body_text, doc_types=doc_types),
            "documentos": docs,
        }

    def _discover_processo_seletivo_urls(self, client: httpx.Client) -> List[Tuple[str, str]]:
        """Descobre páginas de processos seletivos linkadas em `/aluno-regular/`."""
        discovered: List[Tuple[str, str]] = [
            (self.PROCESSO_SELETIVO_2027_URL, "Processo Seletivo 2027 – Aluno Regular (Mestrado e Doutorado)")
        ]
        seen: Set[str] = {self.PROCESSO_SELETIVO_2027_URL.rstrip("/")}

        try:
            resp = client.get(self.ALUNO_REGULAR_URL)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                href = (a_tag.get("href") or "").strip()
                full_url = urljoin(self.ALUNO_REGULAR_URL, href)
                norm = full_url.rstrip("/")
                if norm in seen or "ppgcont.unb.br" not in norm:
                    continue
                label = self._clean_text(a_tag.get_text(" ", strip=True))
                if "processo-seletivo" in norm.lower() or "edital" in norm.lower():
                    seen.add(norm)
                    discovered.append((full_url, label))
        except Exception as exc:
            logger.debug("Falha ao descobrir URLs em %s: %s", self.ALUNO_REGULAR_URL, exc)

        return discovered

    def _fetch_wp_rest_items(self, client: httpx.Client, api_url: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for page in range(1, self.max_pages + 1):
            try:
                response = client.get(api_url, params={"per_page": 30, "page": page})
                if response.status_code == 400:
                    break
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list) or not payload:
                    break
                items.extend(payload)
                total_pages = int(response.headers.get("X-WP-TotalPages", "1") or "1")
                if page >= total_pages:
                    break
            except Exception as exc:
                logger.warning("Falha ao consultar API REST do PPGCont (%s, page=%d): %s", api_url, page, exc)
                break
        return items

    def _parse_wp_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        slug = (item.get("slug") or "").strip().lower()
        if slug in self.IGNORED_STATIC_SLUGS:
            return None

        link = (item.get("link") or "").strip()
        title_raw = (item.get("title") or {}).get("rendered") or ""
        content_html = (item.get("content") or {}).get("rendered") or ""
        excerpt_html = (item.get("excerpt") or {}).get("rendered") or ""

        titulo = self._clean_text(title_raw)
        if not titulo or not link:
            return None

        content_soup = BeautifulSoup(content_html, "html.parser")
        body_text = self._clean_text(content_soup.get_text(" ", strip=True))
        resumo_text = self._clean_text(excerpt_html) or body_text[:400]

        if not self._is_relevant_edital(titulo, body_text, link):
            return None

        docs = self._extract_pdf_docs_from_container(content_soup, link)
        if docs:
            self._docs_by_page[link] = docs

        url_pdf = docs[0]["url_pdf"] if docs else None
        for d in docs:
            if d["tipo_documento"] == "original":
                url_pdf = d["url_pdf"]
                break

        date_str = (item.get("date") or "")[:10]
        if not re.match(r"^20\d{2}-\d{2}-\d{2}$", date_str):
            date_str = self._extract_date_from_text_or_url(f"{titulo} {body_text}", url_pdf or link)

        year_val = self._extract_year(f"{titulo} {body_text}", url_pdf or link, date_str)
        wp_id = item.get("id") or slug or link.rstrip("/").split("/")[-1]
        categoria = self._infer_categoria(titulo, body_text)
        doc_types = [d["tipo_documento"] for d in docs]

        return {
            "identificador_origem": f"PPGCONT-WP-{wp_id}",
            "titulo": titulo,
            "resumo": resumo_text[:500] if resumo_text else titulo,
            "descricao": resumo_text[:500] if resumo_text else titulo,
            "texto_completo": body_text[:2500] if body_text else titulo,
            "link": link,
            "url_pagina": link,
            "url_pdf": url_pdf,
            "orgao_origem": self.orgao_origem,
            "orgao_emissor": self.orgao_origem,
            "campus": "Darcy Ribeiro",
            "tipo": categoria,
            "categoria": categoria,
            "assunto": categoria,
            "ano": year_val,
            "data_publicacao": date_str,
            "inicio_inscricao": None,
            "fim_inscricao": None,
            "status": self._infer_status(titulo, body_text, doc_types=doc_types),
            "documentos": docs,
        }

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retorna os editais e processos seletivos do PPGCont/FACE/UnB.
        """
        cache_key = f"editais:{year if year is not None else 'all'}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        collected: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()

        with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.DEFAULT_HEADERS) as client:
            # 1. Editais internos (/editais-internos/)
            for item in self._scrape_editais_internos_page(client):
                dedup = item.get("url_pdf") or item["identificador_origem"]
                if dedup not in seen_keys:
                    seen_keys.add(dedup)
                    collected.append(item)

            # 2. Páginas de Processos Seletivos (/processo-seletivo-2027-ingresso-em-2027/ e similares)
            for ps_url, ps_label in self._discover_processo_seletivo_urls(client):
                ps_item = self._scrape_processo_seletivo_page(client, ps_url, ps_label)
                if ps_item:
                    dedup = ps_item["url_pagina"].rstrip("/")
                    if dedup not in seen_keys:
                        seen_keys.add(dedup)
                        if ps_item.get("url_pdf"):
                            seen_keys.add(ps_item["url_pdf"])
                        collected.append(ps_item)

            # 3. Posts e páginas via WP REST API
            for api_url in (self.WP_POSTS_API_URL, self.WP_PAGES_API_URL):
                for raw in self._fetch_wp_rest_items(client, api_url):
                    parsed = self._parse_wp_item(raw)
                    if not parsed:
                        continue
                    page_key = parsed["url_pagina"].rstrip("/")
                    pdf_key = parsed.get("url_pdf") or ""
                    if page_key in seen_keys or (pdf_key and pdf_key in seen_keys):
                        continue
                    seen_keys.add(page_key)
                    if pdf_key:
                        seen_keys.add(pdf_key)
                    collected.append(parsed)

        if year is not None:
            filtered: List[Dict[str, Any]] = []
            for ed in collected:
                ed_year = ed.get("ano")
                pub = str(ed.get("data_publicacao") or "")
                if ed_year == year or pub.startswith(str(year)) or str(year) in ed.get("titulo", ""):
                    filtered.append(ed)
            collected = filtered

        self._set_cached(cache_key, collected)
        return [dict(item) for item in collected]

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """
        Retorna os documentos PDF associados a uma página de edital ou link direto.
        """
        if not edital_url:
            return []

        if self._is_pdf_url(edital_url):
            return [self._make_doc(edital_url)]

        if edital_url in self._docs_by_page:
            return [dict(d) for d in self._docs_by_page[edital_url]]

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.DEFAULT_HEADERS) as client:
                response = client.get(edital_url)
                response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup.select("header, footer, nav, script, style"):
                tag.decompose()
            docs = self._extract_pdf_docs_from_container(soup, edital_url)
            self._docs_by_page[edital_url] = docs
            return [dict(d) for d in docs]
        except Exception as exc:
            logger.warning("Erro ao extrair documentos de %s no PPGCont: %s", edital_url, exc)
            return []

    def download_documento(self, url: str, timeout: float = 15.0) -> bytes:
        """Baixa os bytes de um documento público do PPGCont."""
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=self.DEFAULT_HEADERS) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content


ppgcont_scraper = PPGContScraper()

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


class FACEScraper(BaseScraper):
    """
    Scraper para o portal da Faculdade de Economia, Administração, Contabilidade e
    Gestão de Políticas Públicas (FACE/UnB).
    URL base: https://face.unb.br/

    Estratégia combinada:
    1. Raspagem das páginas oficiais de editais e extensão (`/editais-face/`,
       `/extensao-informacoes/`, `/extensao-projetos/`, `/todas-as-noticias/`).
    2. Consulta paginada à API REST do WordPress (`/wp-json/wp/v2/posts`, `/pages` e
       `/media`) com filtro semântico estrito para capturar editais, chamadas,
       seleções, monitoria, extensão, pesquisa e direção, descartando notícias
       irrelevantes (ex.: defesas de memorial, atas de reunião ordinária, eventos gerais).
    """

    BASE_URL = "https://face.unb.br"
    EDITAIS_PAGE_URL = "https://face.unb.br/editais-face/"
    EXTENSAO_PROJETOS_URL = "https://face.unb.br/extensao-projetos/"
    EXTENSAO_INFO_URL = "https://face.unb.br/extensao-informacoes/"
    NOTICIAS_URL = "https://face.unb.br/todas-as-noticias/"

    WP_POSTS_API_URL = "https://face.unb.br/wp-json/wp/v2/posts"
    WP_PAGES_API_URL = "https://face.unb.br/wp-json/wp/v2/pages"
    WP_MEDIA_API_URL = "https://face.unb.br/wp-json/wp/v2/media"

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
        "chamada pública",
        "chamada publica",
        "processo seletivo",
        "seleção",
        "selecao",
        "monitoria",
        "bolsa",
        "bolsista",
        "resultado provisório",
        "resultado provisorio",
        "resultado preliminar",
        "resultado final",
        "retificação",
        "retificacao",
        "convocação",
        "convocacao",
        "iniciação científica",
        "iniciacao cientifica",
        "pibic",
        "pibex",
    )

    EXCLUDED_KEYWORDS = (
        "defesa de memorial",
        "ata da ",
        "ata de reunião",
        "ata de reuniao",
        "pauta da ",
        "calendário de reuniões",
        "calendario de reunioes",
        "estatuto e regimento",
        "política de cookies",
        "politica de cookies",
        "regimento interno",
        "quem somos",
        "ex-diretores",
        "infraestrutura",
    )

    IGNORED_STATIC_SLUGS = {
        "quem-somos",
        "apresentacao",
        "ex-diretores",
        "infraestrutura",
        "agenda",
        "direitos-humanos",
        "todas-as-noticias",
        "editais-face",
        "extensao-informacoes",
        "extensao-normas-e-documentacao",
        "extensao-projetos",
    }

    def __init__(self, timeout: float = 20.0, cache_ttl: float = 300.0, max_pages: int = 2):
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.max_pages = max_pages
        self._cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        self._docs_by_page: Dict[str, List[Dict[str, str]]] = {}

    @property
    def orgao_origem(self) -> str:
        return "FACE"

    def clear_cache(self) -> None:
        """Limpa o cache em memória do scraper."""
        self._cache.clear()
        self._docs_by_page.clear()

    def _get_client(self, timeout: Optional[float] = None) -> httpx.Client:
        return httpx.Client(
            timeout=timeout or self.timeout,
            follow_redirects=True,
            verify=False,
            headers=self.DEFAULT_HEADERS,
        )

    @staticmethod
    def _clean_text(text: str) -> str:
        if not text:
            return ""
        unescaped = html_lib.unescape(text)
        return re.sub(r"\s+", " ", unescaped).strip()

    @classmethod
    def _strip_html(cls, raw_html: str) -> str:
        if not raw_html:
            return ""
        soup = BeautifulSoup(raw_html, "html.parser")
        return cls._clean_text(soup.get_text(" ", strip=True))

    @staticmethod
    def _normalize_url(href: str, base_url: str = BASE_URL) -> str:
        if not href:
            return ""
        href = href.strip()
        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            return ""
        full = urljoin(base_url, href)
        if full.startswith("http://face.unb.br"):
            full = "https://" + full[len("http://") :]
        return full

    @classmethod
    def _is_direct_pdf(cls, url: str) -> bool:
        if not url:
            return False
        low = url.lower().split("?")[0]
        return low.endswith(".pdf")

    @classmethod
    def _is_document_url(cls, url: str) -> bool:
        if not url:
            return False
        low = url.lower().split("?")[0]
        if any(bad in low for bad in ("estatuto_e_regimento", "resolucao_cplad", "politica-de-cookies")):
            return False
        if low.endswith((".pdf", ".doc", ".docx", ".zip")):
            return True
        if "drive.google.com/file/d/" in url.lower():
            return True
        return False

    @classmethod
    def _is_semantic_edital(cls, title: str, text: str = "", url: str = "") -> bool:
        combined = f"{title} {text} {url}".lower()
        for bad in cls.EXCLUDED_KEYWORDS:
            if bad in combined and "edital" not in title.lower():
                return False
        return any(kw in combined for kw in cls.EDITAL_KEYWORDS)

    @classmethod
    def _extract_year(cls, *texts: Optional[str]) -> Optional[int]:
        for text in texts:
            if not text:
                continue
            m_ed = re.search(r"\b\d{1,4}\s*[/\-._]\s*(20\d{2})\b", text)
            if m_ed:
                return int(m_ed.group(1))
            m_up = re.search(r"/uploads/(20\d{2})/", text)
            if m_up:
                return int(m_up.group(1))
            years = [int(m) for m in re.findall(r"\b(20\d{2})\b", text) if 2018 <= int(m) <= 2030]
            if years:
                return max(years)
        return None

    @classmethod
    def _extract_dates_from_text(cls, text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        if not text:
            return None, None, None

        found_dates: List[str] = []
        for d, m, y in re.findall(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d{2})\b", text):
            try:
                dt = datetime(int(y), int(m), int(d))
                found_dates.append(dt.strftime("%Y-%m-%d"))
            except ValueError:
                continue

        pub_date = found_dates[0] if found_dates else None
        inicio_insc: Optional[str] = None
        fim_insc: Optional[str] = None

        m_range = re.search(
            r"inscri[çc][õo]es[^\n.;]{0,50}?(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d{2})\s*(?:a|até|ate|-)\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d{2})",
            text,
            re.IGNORECASE,
        )
        if m_range:
            try:
                d1 = datetime(int(m_range.group(3)), int(m_range.group(2)), int(m_range.group(1)))
                d2 = datetime(int(m_range.group(6)), int(m_range.group(5)), int(m_range.group(4)))
                inicio_insc = d1.strftime("%Y-%m-%d")
                fim_insc = d2.strftime("%Y-%m-%d")
            except ValueError:
                pass

        return pub_date, inicio_insc, fim_insc

    @staticmethod
    def _infer_categoria(title: str, summary: str = "") -> str:
        combined = f"{title} {summary}".lower()
        if "monitoria" in combined or "tutoria" in combined:
            return "Monitoria"
        if "pesquisa" in combined or "pibic" in combined or "iniciação científica" in combined:
            return "Pesquisa"
        if "extens" in combined or "pibex" in combined:
            return "Extensão"
        if "direção" in combined or "direcao" in combined:
            return "Direção / Chamada Interna"
        if "pós-graduação" in combined or "pos-graduacao" in combined or "mestrado" in combined or "doutorado" in combined:
            return "Pós-Graduação"
        return "Edital FACE"

    @staticmethod
    def _infer_status(title: str, text: str = "", docs: Optional[List[Dict[str, str]]] = None) -> str:
        combined = f"{title} {text}".lower()
        if "resultado final" in combined or "encerrad" in combined or "homologação" in combined:
            return "fechado"
        if docs and any(d.get("tipo_documento") == "resultado_final" for d in docs):
            return "fechado"
        return "aberto"

    @classmethod
    def _make_doc(cls, title: str, url: str) -> Dict[str, str]:
        clean_title = cls._clean_text(title) or "Documento do Edital"
        classify_hint = re.sub(r"preliminar", "provisório", clean_title, flags=re.IGNORECASE)
        doc_type = classify_document(classify_hint, url)
        return {
            "titulo": clean_title,
            "link": url,
            "url_pdf": url,
            "tipo": doc_type,
            "tipo_documento": doc_type,
        }

    @classmethod
    def _extract_docs_from_container(cls, container: Tag, base_url: str = BASE_URL) -> List[Dict[str, str]]:
        docs: List[Dict[str, str]] = []
        seen: Set[str] = set()
        for a_tag in container.find_all("a", href=True):
            href = cls._normalize_url(a_tag.get("href", ""), base_url=base_url)
            if not cls._is_document_url(href) or href in seen:
                continue
            seen.add(href)
            label = cls._clean_text(a_tag.get_text(" ", strip=True))
            if not label or label.lower() in {"aqui", "clique aqui", "baixar", "download", "pdf"}:
                parent_txt = cls._clean_text(a_tag.parent.get_text(" ", strip=True)) if a_tag.parent else ""
                label = parent_txt or href.split("/")[-1]
            docs.append(cls._make_doc(label, href))
        return docs

    def _build_edital_dict(
        self,
        *,
        identificador_origem: str,
        titulo: str,
        url_pagina: str,
        data_publicacao: str,
        ano: Optional[int],
        resumo: str = "",
        documentos: Optional[List[Dict[str, str]]] = None,
        inicio_inscricao: Optional[str] = None,
        fim_inscricao: Optional[str] = None,
        campus: str = "Darcy Ribeiro",
    ) -> Dict[str, Any]:
        docs = documentos or []
        direct_pdf = next(
            (d["url_pdf"] for d in docs if self._is_direct_pdf(d.get("url_pdf", ""))),
            docs[0]["url_pdf"] if docs else (url_pagina if self._is_direct_pdf(url_pagina) else None),
        )
        categoria = self._infer_categoria(titulo, resumo)
        status = self._infer_status(titulo, resumo, docs)
        clean_resumo = self._clean_text(resumo) or titulo

        if docs:
            self._docs_by_page[url_pagina] = docs

        return {
            "identificador_origem": identificador_origem,
            "titulo": self._clean_text(titulo),
            "link": url_pagina,
            "url_pagina": url_pagina,
            "url_pdf": direct_pdf,
            "orgao_origem": self.orgao_origem,
            "orgao_emissor": self.orgao_origem,
            "campus": campus or "Darcy Ribeiro",
            "tipo": categoria,
            "categoria": categoria,
            "assunto": categoria,
            "resumo": clean_resumo[:800],
            "descricao": clean_resumo[:800],
            "status": status,
            "data_publicacao": data_publicacao,
            "inicio_inscricao": inicio_inscricao,
            "fim_inscricao": fim_inscricao,
            "ano": ano,
            "documentos": docs,
        }

    def _parse_html_page(self, html: str, page_url: str) -> List[Dict[str, Any]]:
        """
        Analisa uma página HTML da FACE (ex.: `/editais-face/`) extraindo editais e documentos.
        Agrupa documentos relacionados (retificações, resultados, anexos) ao mesmo edital
        quando numerados sob o mesmo processo ou listados em sequência.
        """
        soup = BeautifulSoup(html, "html.parser")
        for noise in soup.select("header, footer"):
            noise.decompose()

        content = soup
        results: List[Dict[str, Any]] = []
        groups: List[Dict[str, Any]] = []
        current_group: Optional[Dict[str, Any]] = None

        for a_tag in content.find_all("a", href=True):
            href = self._normalize_url(a_tag.get("href", ""), base_url=page_url)
            if not href:
                continue

            text = self._clean_text(a_tag.get_text(" ", strip=True))
            parent_text = self._clean_text(a_tag.parent.get_text(" ", strip=True)) if a_tag.parent else text
            label = text if len(text) >= 6 else (parent_text or text)

            if self._is_document_url(href):
                if not self._is_semantic_edital(label, parent_text, href):
                    continue
                low_label = label.lower()
                is_followup = any(
                    k in low_label
                    for k in ("resultado", "retificação", "retificacao", "anexo", "convocação", "convocacao")
                ) and not low_label.startswith("edital")

                doc = self._make_doc(label, href)
                if is_followup and current_group is not None:
                    if not any(d["url_pdf"] == href for d in current_group["docs"]):
                        current_group["docs"].append(doc)
                    continue

                current_group = {
                    "title": label or href.split("/")[-1],
                    "url_pagina": href,
                    "context": parent_text,
                    "docs": [doc],
                }
                groups.append(current_group)
            elif href.startswith(self.BASE_URL):
                slug = urlparse(href).path.strip("/").split("/")[-1].lower()
                if not slug or slug in self.IGNORED_STATIC_SLUGS or "/wp-admin/" in href:
                    continue
                if not self._is_semantic_edital(label, parent_text, href):
                    continue
                groups.append(
                    {
                        "title": label,
                        "url_pagina": href,
                        "context": parent_text,
                        "docs": [],
                    }
                )

        for grp in groups:
            title = grp["title"]
            target_url = grp["url_pagina"]
            docs = grp["docs"]
            ano = self._extract_year(title, grp["context"], target_url)
            pub_date, inicio_insc, fim_insc = self._extract_dates_from_text(grp["context"])
            if not pub_date:
                m_up = re.search(r"/uploads/(20\d{2})/(\d{2})/", target_url)
                if m_up:
                    pub_date = f"{m_up.group(1)}-{m_up.group(2)}-01"
                elif ano:
                    pub_date = f"{ano}-01-01"
                else:
                    pub_date = datetime.now().strftime("%Y-%m-%d")
            if not ano and len(pub_date) >= 4 and pub_date[:4].isdigit():
                ano = int(pub_date[:4])

            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50]
            results.append(
                self._build_edital_dict(
                    identificador_origem=f"face-html-{slug}",
                    titulo=title,
                    url_pagina=target_url,
                    data_publicacao=pub_date,
                    ano=ano,
                    resumo=grp["context"] or title,
                    documentos=docs,
                    inicio_inscricao=inicio_insc,
                    fim_inscricao=fim_insc,
                )
            )

        return results

    def _fetch_from_wp_api(self, client: httpx.Client) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        seen_links: Set[str] = set()

        # 1. Posts e páginas paginadas
        for endpoint, prefix in ((self.WP_POSTS_API_URL, "post"), (self.WP_PAGES_API_URL, "page")):
            for page_num in range(1, self.max_pages + 1):
                try:
                    resp = client.get(endpoint, params={"per_page": 50, "page": page_num})
                    if resp.status_code != 200:
                        break
                    items = resp.json()
                    if not isinstance(items, list) or not items:
                        break
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        slug = str(item.get("slug") or "").lower()
                        if slug in self.IGNORED_STATIC_SLUGS and prefix == "page":
                            # Se for a página agregadora `/editais-face/`, extrai os blocos internos
                            raw_content = (item.get("content") or {}).get("rendered", "")
                            if slug == "editais-face" and raw_content:
                                page_link = self._normalize_url(item.get("link") or self.EDITAIS_PAGE_URL)
                                for sub in self._parse_html_page(raw_content, page_url=page_link):
                                    if sub["link"] not in seen_links:
                                        seen_links.add(sub["link"])
                                        results.append(sub)
                            continue

                        title = self._strip_html((item.get("title") or {}).get("rendered", ""))
                        link = self._normalize_url(item.get("link", ""))
                        raw_content = (item.get("content") or {}).get("rendered", "")
                        raw_excerpt = (item.get("excerpt") or {}).get("rendered", "")
                        content_text = self._strip_html(raw_content)
                        excerpt_text = self._strip_html(raw_excerpt)

                        if not title or not link or link in seen_links:
                            continue
                        if not self._is_semantic_edital(title, f"{excerpt_text} {content_text[:300]}", link):
                            continue

                        frag = BeautifulSoup(raw_content, "html.parser") if raw_content else BeautifulSoup("", "html.parser")
                        docs = self._extract_docs_from_container(frag, base_url=link)

                        raw_date = str(item.get("date") or "")
                        pub_date = raw_date[:10] if len(raw_date) >= 10 else ""
                        txt_pub, inicio_insc, fim_insc = self._extract_dates_from_text(content_text)
                        if not pub_date:
                            pub_date = txt_pub or datetime.now().strftime("%Y-%m-%d")

                        ano = self._extract_year(title, pub_date, link)
                        if not ano and len(pub_date) >= 4 and pub_date[:4].isdigit():
                            ano = int(pub_date[:4])

                        item_id = item.get("id") or slug
                        seen_links.add(link)
                        results.append(
                            self._build_edital_dict(
                                identificador_origem=f"face-{prefix}-{item_id}",
                                titulo=title,
                                url_pagina=link,
                                data_publicacao=pub_date,
                                ano=ano,
                                resumo=excerpt_text or content_text[:400],
                                documentos=docs,
                                inicio_inscricao=inicio_insc,
                                fim_inscricao=fim_insc,
                            )
                        )
                    if len(items) < 50:
                        break
                except Exception as e:
                    logger.warning(f"Falha ao consultar {endpoint} página {page_num} na FACE: {e}")
                    break

        # 2. Mídias PDF de editais na biblioteca WP
        try:
            resp_media = client.get(self.WP_MEDIA_API_URL, params={"per_page": 50})
            if resp_media.status_code == 200 and isinstance(resp_media.json(), list):
                for media in resp_media.json():
                    if not isinstance(media, dict):
                        continue
                    source_url = self._normalize_url(media.get("source_url", ""))
                    if not self._is_direct_pdf(source_url) or source_url in seen_links:
                        continue
                    title = self._strip_html((media.get("title") or {}).get("rendered", ""))
                    if not self._is_semantic_edital(title, "", source_url):
                        continue
                    raw_date = str(media.get("date") or "")
                    pub_date = raw_date[:10] if len(raw_date) >= 10 else datetime.now().strftime("%Y-%m-%d")
                    ano = self._extract_year(title, source_url, pub_date)
                    if not ano and len(pub_date) >= 4 and pub_date[:4].isdigit():
                        ano = int(pub_date[:4])

                    media_id = media.get("id") or source_url.split("/")[-1]
                    doc = self._make_doc(title, source_url)
                    seen_links.add(source_url)
                    results.append(
                        self._build_edital_dict(
                            identificador_origem=f"face-media-{media_id}",
                            titulo=title,
                            url_pagina=source_url,
                            data_publicacao=pub_date,
                            ano=ano,
                            resumo=f"Documento oficial publicado pela FACE/UnB: {title}",
                            documentos=[doc],
                        )
                    )
        except Exception as e:
            logger.warning(f"Falha ao consultar WP media API da FACE: {e}")

        return results

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Busca editais publicados pela FACE/UnB nas páginas de editais e API WordPress.
        """
        cache_key = f"editais:{year if year is not None else 'all'}"
        now = time.time()
        if cache_key in self._cache:
            ts, cached = self._cache[cache_key]
            if now - ts < self.cache_ttl:
                return [dict(item) for item in cached]

        combined: List[Dict[str, Any]] = []
        seen_urls: Set[str] = set()

        with self._get_client() as client:
            # 1. Páginas oficiais HTML (`/editais-face/`, `/extensao-projetos/`, `/todas-as-noticias/`)
            for page_url in (self.EDITAIS_PAGE_URL, self.EXTENSAO_PROJETOS_URL, self.NOTICIAS_URL):
                try:
                    resp = client.get(page_url)
                    if resp.status_code == 200 and resp.text:
                        for item in self._parse_html_page(resp.text, page_url=page_url):
                            norm_key = (item.get("url_pdf") or item["link"]).rstrip("/").lower()
                            if norm_key not in seen_urls:
                                seen_urls.add(norm_key)
                                combined.append(item)
                except Exception as e:
                    logger.warning(f"Erro ao raspar página da FACE ({page_url}): {e}")

            # 2. Endpoints WP REST API
            for item in self._fetch_from_wp_api(client):
                norm_key = (item.get("url_pdf") or item["link"]).rstrip("/").lower()
                if norm_key not in seen_urls:
                    seen_urls.add(norm_key)
                    combined.append(item)

        if year is not None:
            combined = [item for item in combined if item.get("ano") == year]

        self._cache[cache_key] = (now, [dict(item) for item in combined])
        return combined

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """
        Retorna os documentos PDF vinculados a uma página ou URL de edital da FACE.
        """
        if not edital_url:
            return []

        if edital_url in self._docs_by_page and self._docs_by_page[edital_url]:
            return [dict(d) for d in self._docs_by_page[edital_url]]

        if self._is_document_url(edital_url):
            filename = edital_url.rstrip("/").split("/")[-1]
            return [self._make_doc(filename, edital_url)]

        try:
            with self._get_client() as client:
                resp = client.get(edital_url)
                resp.raise_for_status()
        except Exception as e:
            logger.error(f"Erro ao buscar documentos do edital FACE ({edital_url}): {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        for noise in soup.select("header, footer"):
            noise.decompose()

        content = soup
        docs = self._extract_docs_from_container(content, base_url=edital_url)
        self._docs_by_page[edital_url] = docs
        return [dict(d) for d in docs]

    def download_documento(self, url: str, timeout: float = 15.0) -> bytes:
        with self._get_client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content


face_scraper = FACEScraper()

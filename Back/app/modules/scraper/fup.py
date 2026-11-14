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


class FUPScraper(BaseScraper):
    """
    Scraper para o portal da Faculdade UnB Planaltina (FUP/UnB).
    URL principal: https://fup.unb.br/editais-da-fup/

    Estratégia combinada:
    1. API REST WordPress (`/wp-json/wp/v2/posts?categories=33` para a categoria Editais e
       `/wp-json/wp/v2/posts?search=edital` para chamadas e seleções fora da categoria,
       como o projeto "FUP de Braços Abertos", auxílio a eventos e voluntários SEMUNI).
    2. Raspagem HTML da página principal `/editais-da-fup/` (grade JetSmartFilters / Elementor)
       e das páginas temáticas `/editais-de-fomento-fup/`, `/pibex-fup/` e `/monitoria/`,
       agrupando editais de abertura, retificações e resultados provisórios/finais.
    3. Define `campus = "Planaltina"` por padrão quando não houver outro especificado.
    """

    BASE_URL = "https://fup.unb.br"
    EDITAIS_URL = "https://fup.unb.br/editais-da-fup/"
    FOMENTO_URL = "https://fup.unb.br/editais-de-fomento-fup/"
    PIBEX_URL = "https://fup.unb.br/pibex-fup/"
    MONITORIA_URL = "https://fup.unb.br/monitoria/"

    WP_POSTS_API_URL = "https://fup.unb.br/wp-json/wp/v2/posts"
    EDITAIS_CATEGORY_ID = 33

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
        "selecao",
        "seleção",
        "processo seletivo",
        "bolsa",
        "bolsista",
        "monitoria",
        "fomento",
        "auxilio",
        "auxílio",
        "pibex",
        "extensao",
        "extensão",
        "resultado",
        "retificacao",
        "retificação",
        "convocacao",
        "convocação",
        "bracos abertos",
        "braços abertos",
    )

    IGNORED_PDF_PATTERNS = (
        "regimento_interno",
        "relatorios-de-sustentabilidade",
        "relatorio-de-sustentabilidade",
        "plano-de-melhorias-academicas",
        "relatorio-diagnostico",
        "estatuto_e_regimento",
        "calendario_academico",
    )

    IGNORED_LINK_DOMAINS = (
        "twitter.com",
        "facebook.com",
        "pinterest.com",
        "instagram.com",
        "linkedin.com",
        "youtube.com",
        "wa.me",
        "whatsapp.com",
    )

    PT_MONTHS = {
        "janeiro": 1,
        "fevereiro": 2,
        "marco": 3,
        "março": 3,
        "abril": 4,
        "maio": 5,
        "junho": 6,
        "julho": 7,
        "agosto": 8,
        "setembro": 9,
        "outubro": 10,
        "novembro": 11,
        "dezembro": 12,
    }

    def __init__(self, timeout: float = 20.0, cache_ttl: float = 300.0):
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        self._docs_by_page: Dict[str, List[Dict[str, str]]] = {}

    @property
    def orgao_origem(self) -> str:
        return "FUP"

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
        if full.startswith("http://fup.unb.br"):
            full = "https://" + full[len("http://") :]
        return full

    @classmethod
    def _is_ignored_url(cls, url: str) -> bool:
        if not url:
            return True
        low = url.lower()
        for domain in cls.IGNORED_LINK_DOMAINS:
            if domain in low:
                return True
        for pat in cls.IGNORED_PDF_PATTERNS:
            if pat in low:
                return True
        return False

    @classmethod
    def _is_document_url(cls, url: str) -> bool:
        if not url or cls._is_ignored_url(url):
            return False
        low = url.lower().split("?")[0]
        if low.endswith((".pdf", ".doc", ".docx", ".zip")):
            return True
        if "drive.google.com/file/d/" in url.lower() or "drive.google.com/open" in url.lower():
            return True
        return False

    @classmethod
    def _is_direct_pdf(cls, url: str) -> bool:
        if not url:
            return False
        low = url.lower().split("?")[0]
        return low.endswith(".pdf")

    @classmethod
    def _is_relevant_edital(cls, title: str, content: str = "", url: str = "") -> bool:
        combined = f"{title} {content} {url}".lower()
        return any(kw in combined for kw in cls.EDITAL_KEYWORDS)

    @classmethod
    def _extract_year(cls, *texts: Optional[str]) -> Optional[int]:
        for text in texts:
            if not text:
                continue
            # Padrão Edital N/YYYY ou YYYY no texto/URL
            m_ed = re.search(r"\b\d{1,4}\s*[/\-._]\s*(20\d{2})\b", text)
            if m_ed:
                return int(m_ed.group(1))
            m_up = re.search(r"/uploads/(20\d{2})/", text)
            if m_up:
                return int(m_up.group(1))
            years = [int(m) for m in re.findall(r"\b(20\d{2})\b", text) if 2015 <= int(m) <= 2030]
            if years:
                return max(years)
        return None

    @classmethod
    def _extract_dates_from_text(cls, text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Extrai (data_publicacao, inicio_inscricao, fim_inscricao) quando presentes no texto.
        """
        if not text:
            return None, None, None

        found_dates: List[str] = []
        # Formato DD/MM/YYYY
        for d, m, y in re.findall(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d{2})\b", text):
            try:
                dt = datetime(int(y), int(m), int(d))
                found_dates.append(dt.strftime("%Y-%m-%d"))
            except ValueError:
                continue

        # Formato "DD de mês de YYYY"
        for d, month_name, y in re.findall(
            r"\b(\d{1,2})\s+de\s+([a-zç]+)\s+de\s+(20\d{2})\b", text.lower()
        ):
            m_num = cls.PT_MONTHS.get(month_name)
            if m_num:
                try:
                    dt = datetime(int(y), m_num, int(d))
                    found_dates.append(dt.strftime("%Y-%m-%d"))
                except ValueError:
                    continue

        pub_date = found_dates[0] if found_dates else None
        inicio_insc: Optional[str] = None
        fim_insc: Optional[str] = None

        # Procura janela de inscrição ("inscrições de DD/MM/YYYY a DD/MM/YYYY" ou "até DD/MM/YYYY")
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
        else:
            m_until = re.search(
                r"(?:inscri[çc][õo]es|prazo)[^\n.;]{0,40}?(?:at[ée]|encerram[- ]se em)\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d{2})",
                text,
                re.IGNORECASE,
            )
            if m_until:
                try:
                    d2 = datetime(int(m_until.group(3)), int(m_until.group(2)), int(m_until.group(1)))
                    fim_insc = d2.strftime("%Y-%m-%d")
                except ValueError:
                    pass

        return pub_date, inicio_insc, fim_insc

    @staticmethod
    def _infer_categoria(title: str, summary: str = "") -> str:
        combined = f"{title} {summary}".lower()
        if "monitoria" in combined or "tutoria" in combined:
            return "Monitoria"
        if "pibex" in combined or "extens" in combined or "braços abertos" in combined or "bracos abertos" in combined or "semuni" in combined:
            return "Extensão"
        if "pesquisa" in combined or "pibic" in combined or "iniciação científica" in combined:
            return "Pesquisa"
        if "auxílio" in combined or "auxilio" in combined or "fomento" in combined or "apoio" in combined or "evento" in combined:
            return "Fomento / Apoio Estudantil"
        if "pós-graduação" in combined or "pos-graduacao" in combined or "mestrado" in combined or "doutorado" in combined:
            return "Pós-Graduação"
        return "Edital FUP"

    @staticmethod
    def _infer_status(title: str, text: str = "", docs: Optional[List[Dict[str, str]]] = None) -> str:
        combined = f"{title} {text}".lower()
        if "resultado final" in combined or "edital finalizado" in combined or "encerrad" in combined:
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
    def _extract_docs_from_html_fragment(cls, container: Tag, base_url: str = BASE_URL) -> List[Dict[str, str]]:
        docs: List[Dict[str, str]] = []
        seen_urls: Set[str] = set()

        for a_tag in container.find_all("a", href=True):
            href = cls._normalize_url(a_tag["href"], base_url=base_url)
            if not cls._is_document_url(href) or href in seen_urls:
                continue
            seen_urls.add(href)
            label = cls._clean_text(a_tag.get_text(" ", strip=True))
            if not label or label.lower() in {"aqui", "clique aqui", "acesse aqui", "edital", "baixar", "download"}:
                parent_text = cls._clean_text(a_tag.parent.get_text(" ", strip=True)) if a_tag.parent else ""
                label = parent_text or label or href.split("/")[-1]
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
        campus: str = "Planaltina",
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
            "campus": campus or "Planaltina",
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

    def _parse_wp_post_item(self, post: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        post_id = post.get("id")
        raw_title = (post.get("title") or {}).get("rendered", "")
        title = self._strip_html(raw_title)
        link = self._normalize_url(post.get("link", ""))
        if not title or not link:
            return None

        raw_content = (post.get("content") or {}).get("rendered", "")
        raw_excerpt = (post.get("excerpt") or {}).get("rendered", "")
        content_text = self._strip_html(raw_content)
        excerpt_text = self._strip_html(raw_excerpt)

        if not self._is_relevant_edital(title, excerpt_text, link):
            return None

        raw_date = post.get("date", "")
        pub_date = raw_date[:10] if isinstance(raw_date, str) and len(raw_date) >= 10 else ""
        text_pub, inicio_insc, fim_insc = self._extract_dates_from_text(content_text)
        if not pub_date:
            pub_date = text_pub or datetime.now().strftime("%Y-%m-%d")

        ano = self._extract_year(title, pub_date, link)
        if not ano and len(pub_date) >= 4 and pub_date[:4].isdigit():
            ano = int(pub_date[:4])

        docs: List[Dict[str, str]] = []
        if raw_content:
            frag = BeautifulSoup(raw_content, "html.parser")
            docs = self._extract_docs_from_html_fragment(frag, base_url=link)

        slug = post.get("slug") or (str(post_id) if post_id else re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-"))
        identificador = f"fup-wp-{post_id or slug}"

        return self._build_edital_dict(
            identificador_origem=identificador,
            titulo=title,
            url_pagina=link,
            data_publicacao=pub_date,
            ano=ano,
            resumo=excerpt_text or content_text[:400],
            documentos=docs,
            inicio_inscricao=inicio_insc,
            fim_inscricao=fim_insc,
            campus="Planaltina",
        )

    def _fetch_from_wp_api(self, client: httpx.Client) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        seen_links: Set[str] = set()

        queries = [
            {"categories": self.EDITAIS_CATEGORY_ID, "per_page": 50},
            {"search": "edital", "per_page": 30},
        ]

        for params in queries:
            try:
                resp = client.get(self.WP_POSTS_API_URL, params=params)
                if resp.status_code != 200:
                    logger.warning(f"FUP WP API retornou HTTP {resp.status_code} para params={params}")
                    continue
                payload = resp.json()
                if not isinstance(payload, list):
                    continue
                for post in payload:
                    if not isinstance(post, dict):
                        continue
                    parsed = self._parse_wp_post_item(post)
                    if parsed and parsed["link"] not in seen_links:
                        seen_links.add(parsed["link"])
                        results.append(parsed)
            except Exception as e:
                logger.warning(f"Falha ao consultar WP API da FUP ({params}): {e}")

        return results

    def _parse_editais_listing_html(self, html: str, page_url: str = EDITAIS_URL) -> List[Dict[str, Any]]:
        """
        Extrai editais da grade HTML de `/editais-da-fup/` (JetSmartFilters / Elementor cards).
        """
        soup = BeautifulSoup(html, "html.parser")
        results: List[Dict[str, Any]] = []
        seen_links: Set[str] = set()

        # Procura nos cards JetListing / Elementor ou headings h2/h3/h4 com links
        candidates: List[Tag] = []
        for item in soup.select(".jet-listing-grid__item, article, .elementor-post"):
            a_tag = item.find("a", href=True)
            if a_tag:
                candidates.append(a_tag)

        if not candidates:
            for h_tag in soup.find_all(["h2", "h3", "h4"]):
                a_tag = h_tag.find("a", href=True)
                if a_tag:
                    candidates.append(a_tag)

        for a_tag in candidates:
            href = self._normalize_url(a_tag.get("href", ""), base_url=page_url)
            title = self._clean_text(a_tag.get_text(" ", strip=True))
            if not href or not title or len(title) < 5 or href in seen_links:
                continue
            if self._is_ignored_url(href):
                continue
            if not self._is_relevant_edital(title, "", href):
                continue

            seen_links.add(href)
            container = a_tag.find_parent(class_=re.compile(r"jet-listing-grid__item|elementor-column|article")) or a_tag.parent
            context_text = self._clean_text(container.get_text(" ", strip=True)) if container else title
            pub_date, inicio_insc, fim_insc = self._extract_dates_from_text(context_text)
            ano = self._extract_year(title, context_text, href)
            if not pub_date:
                pub_date = f"{ano}-01-01" if ano else datetime.now().strftime("%Y-%m-%d")
            if not ano and len(pub_date) >= 4 and pub_date[:4].isdigit():
                ano = int(pub_date[:4])

            slug = urlparse(href).path.strip("/").split("/")[-1] or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            docs = [self._make_doc(title, href)] if self._is_document_url(href) else []

            results.append(
                self._build_edital_dict(
                    identificador_origem=f"fup-grid-{slug[:60]}",
                    titulo=title,
                    url_pagina=href,
                    data_publicacao=pub_date,
                    ano=ano,
                    resumo=context_text,
                    documentos=docs,
                    inicio_inscricao=inicio_insc,
                    fim_inscricao=fim_insc,
                    campus="Planaltina",
                )
            )

        return results

    def _parse_thematic_page_html(self, html: str, page_url: str, section_prefix: str) -> List[Dict[str, Any]]:
        """
        Extrai editais e seus documentos (abertura, retificação, resultado provisório/final)
        de páginas temáticas da FUP como `/editais-de-fomento-fup/` e `/pibex-fup/`.
        """
        soup = BeautifulSoup(html, "html.parser")
        results: List[Dict[str, Any]] = []

        # Remove rodapé/cabeçalho de navegação e carrossel de últimas notícias
        for noise in soup.select("header, footer, nav, .jet-listing-grid"):
            noise.decompose()

        content = soup.select_one("main, article, .entry-content, .elementor-section-wrap") or soup
        groups: List[Dict[str, Any]] = []
        current_group: Optional[Dict[str, Any]] = None

        for a_tag in content.find_all("a", href=True):
            href = self._normalize_url(a_tag.get("href", ""), base_url=page_url)
            if not self._is_document_url(href):
                continue

            link_text = self._clean_text(a_tag.get_text(" ", strip=True))
            parent_text = self._clean_text(a_tag.parent.get_text(" ", strip=True)) if a_tag.parent else link_text
            label = link_text if len(link_text) > 10 else (parent_text or link_text)
            low_label = label.lower()

            is_followup = any(
                k in low_label
                for k in (
                    "resultado",
                    "retificação",
                    "retificacao",
                    "apêndice",
                    "apendice",
                    "anexo",
                    "cronograma",
                )
            ) and not low_label.startswith(("edital fup", "edital nº", "edital no", "edital de seleção", "projeto"))

            if is_followup and current_group is not None:
                doc = self._make_doc(label, href)
                if not any(d["url_pdf"] == href for d in current_group["docs"]):
                    current_group["docs"].append(doc)
                continue

            # Novo edital / chamada de projeto
            title = label
            if title.lower() in {"edital", "aqui", "aqui.", "acesse aqui"}:
                # Tenta buscar heading anterior
                prev_h = a_tag.find_previous(["h2", "h3", "h4", "strong", "p"])
                if prev_h:
                    cand = self._clean_text(prev_h.get_text(" ", strip=True))
                    if len(cand) > 8:
                        title = cand

            if not self._is_relevant_edital(title, parent_text, href):
                continue

            doc = self._make_doc(title, href)
            current_group = {
                "title": title,
                "primary_href": href,
                "context": parent_text,
                "docs": [doc],
            }
            groups.append(current_group)

        for idx, grp in enumerate(groups, start=1):
            title = grp["title"]
            docs = grp["docs"]
            primary_href = grp["primary_href"]
            ano = self._extract_year(title, grp["context"], primary_href)
            pub_date, inicio_insc, fim_insc = self._extract_dates_from_text(grp["context"])
            if not pub_date:
                m_up = re.search(r"/uploads/(20\d{2})/(\d{2})/", primary_href)
                if m_up:
                    pub_date = f"{m_up.group(1)}-{m_up.group(2)}-01"
                elif ano:
                    pub_date = f"{ano}-01-01"
                else:
                    pub_date = datetime.now().strftime("%Y-%m-%d")
            if not ano and len(pub_date) >= 4 and pub_date[:4].isdigit():
                ano = int(pub_date[:4])

            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50] or str(idx)
            canonical_url = f"{page_url.rstrip('/')}/#{slug}"

            results.append(
                self._build_edital_dict(
                    identificador_origem=f"fup-{section_prefix}-{slug}",
                    titulo=title,
                    url_pagina=canonical_url,
                    data_publicacao=pub_date,
                    ano=ano,
                    resumo=grp["context"] or title,
                    documentos=docs,
                    inicio_inscricao=inicio_insc,
                    fim_inscricao=fim_insc,
                    campus="Planaltina",
                )
            )

        return results

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retorna os editais publicados no portal da FUP.
        Se `year` for informado, filtra apenas editais daquele ano.
        """
        cache_key = f"editais:{year if year is not None else 'all'}"
        now = time.time()
        if cache_key in self._cache:
            ts, cached = self._cache[cache_key]
            if now - ts < self.cache_ttl:
                return [dict(item) for item in cached]

        combined: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()

        with self._get_client() as client:
            # 1. WordPress REST API (categoria Editais + busca por edital)
            api_items = self._fetch_from_wp_api(client)
            for item in api_items:
                key = item["link"].rstrip("/").lower()
                if key not in seen_keys:
                    seen_keys.add(key)
                    combined.append(item)

            # 2. Página HTML principal `/editais-da-fup/` (fallback/complemento)
            try:
                resp_main = client.get(self.EDITAIS_URL)
                if resp_main.status_code == 200 and resp_main.text:
                    grid_items = self._parse_editais_listing_html(resp_main.text, page_url=self.EDITAIS_URL)
                    for item in grid_items:
                        key = item["link"].rstrip("/").lower()
                        if key not in seen_keys:
                            seen_keys.add(key)
                            combined.append(item)
            except Exception as e:
                logger.warning(f"Erro ao raspar página principal da FUP ({self.EDITAIS_URL}): {e}")

            # 3. Páginas temáticas (`/editais-de-fomento-fup/` e `/pibex-fup/`)
            for page_url, prefix in ((self.FOMENTO_URL, "fomento"), (self.PIBEX_URL, "pibex")):
                try:
                    resp_page = client.get(page_url)
                    if resp_page.status_code == 200 and resp_page.text:
                        thematic_items = self._parse_thematic_page_html(
                            resp_page.text, page_url=page_url, section_prefix=prefix
                        )
                        for item in thematic_items:
                            key = item["identificador_origem"].lower()
                            if key not in seen_keys:
                                seen_keys.add(key)
                                combined.append(item)
                except Exception as e:
                    logger.warning(f"Erro ao raspar página temática da FUP ({page_url}): {e}")

        if year is not None:
            combined = [item for item in combined if item.get("ano") == year]

        self._cache[cache_key] = (now, [dict(item) for item in combined])
        return combined

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """
        Extrai os documentos (PDFs e links de arquivos do edital) a partir da URL do edital.
        """
        if not edital_url:
            return []

        if edital_url in self._docs_by_page and self._docs_by_page[edital_url]:
            return [dict(d) for d in self._docs_by_page[edital_url]]

        if self._is_document_url(edital_url):
            filename = edital_url.rstrip("/").split("/")[-1]
            return [self._make_doc(filename, edital_url)]

        target_url = edital_url.split("#")[0]
        try:
            with self._get_client() as client:
                resp = client.get(target_url)
                resp.raise_for_status()
        except Exception as e:
            logger.error(f"Erro ao buscar documentos do edital FUP ({edital_url}): {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        for noise in soup.select("header, footer, .jet-listing-grid"):
            noise.decompose()

        content = soup
        docs = self._extract_docs_from_html_fragment(content, base_url=target_url)
        self._docs_by_page[edital_url] = docs
        return [dict(d) for d in docs]

    def download_documento(self, url: str, timeout: float = 15.0) -> bytes:
        with self._get_client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content


fup_scraper = FUPScraper()

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


class DireitoScraper(BaseScraper):
    """
    Scraper para o portal da Faculdade de Direito da UnB (FD / DIREITO).
    URL base: https://direito.unb.br/

    Estratégia combinada:
    1. Raspagem das seções oficiais de editais e seleções da Faculdade de Direito:
       - `/editais/` (Editais da Direção, Processos Seletivos Simplificados, PDS, etc.)
       - `/monitoria/` (Editais e Resultados de Monitoria de Graduação)
       - `/grupos-de-pesquisa/` (Chamadas e editais de Grupos de Pesquisa, ex.: JURAPP)
       - `/projetos-e-acoes-de-extensao/` e `/programa-de-educacao-tutorial/` (Extensão e PET)
       - `/apresentacao/` e `/atividades/` (Núcleo de Prática Jurídica - NPJ)
       - `/iniciacao-cientifica/` (PIBIC / Pesquisa)
    2. Consulta à API REST do WordPress (`/wp-json/wp/v2/posts`, `/media`) filtrando
       estritamente publicações de editais, chamadas, seleções e resultados e descartando
       legislação estática (ex.: Lei de Estágio, Resoluções CEPE de 1990, Cartas).
    """

    BASE_URL = "https://direito.unb.br"
    EDITAIS_URL = "https://direito.unb.br/editais/"
    MONITORIA_URL = "https://direito.unb.br/monitoria/"
    GRUPOS_PESQUISA_URL = "https://direito.unb.br/grupos-de-pesquisa/"
    EXTENSAO_URL = "https://direito.unb.br/projetos-e-acoes-de-extensao/"
    PET_URL = "https://direito.unb.br/programa-de-educacao-tutorial/"
    NPJ_URL = "https://direito.unb.br/apresentacao/"
    INICIACAO_CIENTIFICA_URL = "https://direito.unb.br/iniciacao-cientifica/"

    SECTION_URLS: Tuple[Tuple[str, str], ...] = (
        (EDITAIS_URL, "editais"),
        (MONITORIA_URL, "monitoria"),
        (GRUPOS_PESQUISA_URL, "pesquisa"),
        (EXTENSAO_URL, "extensao"),
        (PET_URL, "pet"),
        (NPJ_URL, "npj"),
        (INICIACAO_CIENTIFICA_URL, "pibic"),
    )

    WP_POSTS_API_URL = "https://direito.unb.br/wp-json/wp/v2/posts"
    WP_MEDIA_API_URL = "https://direito.unb.br/wp-json/wp/v2/media"

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
        "monitoria",
        "resultado provisório",
        "resultado provisorio",
        "resultado preliminar",
        "resultado final",
        "resultado da monitoria",
        "retificação",
        "retificacao",
        "inscrições abertas",
        "inscricoes abertas",
        "npj",
        "prática jurídica",
        "pratica juridica",
        "grupo de pesquisa",
        "pet ",
        "bolsa",
        "bolsista",
    )

    IGNORED_DOC_PATTERNS = (
        "lei_estagio",
        "l11788",
        "resolucao_cepe",
        "resolucao_monitoria",
        "resolucao_cplad",
        "estatuto_e_regimento",
        "regimento_interno",
        "sei_unb-14242377-carta",
        "calendario_academico",
        "fluxo_curricular",
        "politica-de-cookies",
        "lorem-ipsum",
    )

    def __init__(self, timeout: float = 20.0, cache_ttl: float = 300.0):
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        self._docs_by_page: Dict[str, List[Dict[str, str]]] = {}

    @property
    def orgao_origem(self) -> str:
        return "DIREITO"

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
        if full.startswith("http://direito.unb.br"):
            full = "https://" + full[len("http://") :]
        return full

    @classmethod
    def _is_ignored_doc(cls, url: str, title: str = "") -> bool:
        combined = f"{url} {title}".lower()
        return any(pat in combined for pat in cls.IGNORED_DOC_PATTERNS)

    @classmethod
    def _is_direct_pdf(cls, url: str) -> bool:
        if not url or cls._is_ignored_doc(url):
            return False
        low = url.lower().split("?")[0]
        return low.endswith(".pdf")

    @classmethod
    def _is_document_url(cls, url: str, title: str = "") -> bool:
        if not url or cls._is_ignored_doc(url, title):
            return False
        low = url.lower().split("?")[0]
        if low.endswith((".pdf", ".doc", ".docx", ".zip")):
            return True
        if "drive.google.com/file/d/" in url.lower():
            return True
        return False

    @classmethod
    def _is_relevant_edital(cls, title: str, context: str = "", url: str = "") -> bool:
        if cls._is_ignored_doc(url, title):
            return False
        combined = f"{title} {context} {url}".lower()
        return any(kw in combined for kw in cls.EDITAL_KEYWORDS)

    @classmethod
    def _extract_year(cls, *texts: Optional[str]) -> Optional[int]:
        for text in texts:
            if not text:
                continue
            m_ed = re.search(r"\b\d{1,4}\s*[/\-._]\s*(20\d{2})\b", text)
            if m_ed:
                return int(m_ed.group(1))
            m_sem = re.search(r"\b(20\d{2})\s*[.\-/]\s*[12]\b", text)
            if m_sem:
                return int(m_sem.group(1))
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
    def _infer_categoria(title: str, section: str = "", summary: str = "") -> str:
        combined = f"{title} {section} {summary}".lower()
        if "monitoria" in combined:
            return "Monitoria"
        if "npj" in combined or "prática jurídica" in combined or "pratica juridica" in combined:
            return "NPJ / Prática Jurídica"
        if "pesquisa" in combined or "jurapp" in combined or "pibic" in combined or "iniciação científica" in combined:
            return "Grupos de Pesquisa / Iniciação Científica"
        if "pet" in combined or "educação tutorial" in combined or "extens" in combined:
            return "Extensão / PET"
        return "Processo Seletivo / Edital FD"

    @staticmethod
    def _infer_status(title: str, text: str = "", docs: Optional[List[Dict[str, str]]] = None) -> str:
        combined = f"{title} {text}".lower()
        if "resultado final" in combined or "encerrad" in combined:
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

    def _build_edital_dict(
        self,
        *,
        identificador_origem: str,
        titulo: str,
        url_pagina: str,
        data_publicacao: str,
        ano: Optional[int],
        section: str = "editais",
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
        categoria = self._infer_categoria(titulo, section, resumo)
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

    def _parse_section_html(self, html: str, page_url: str, section: str) -> List[Dict[str, Any]]:
        """
        Extrai editais e documentos de uma página de seção da Faculdade de Direito,
        agrupando resultados provisórios/finais ou retificações ao edital principal
        quando pertencem ao mesmo processo seletivo, além de expor os itens individuais.
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
            if not self._is_document_url(href):
                continue

            text = self._clean_text(a_tag.get_text(" ", strip=True))
            parent_text = self._clean_text(a_tag.parent.get_text(" ", strip=True)) if a_tag.parent else text
            label = text if len(text) >= 5 else (parent_text or text or href.split("/")[-1])

            if not self._is_relevant_edital(label, parent_text, href):
                continue

            doc = self._make_doc(label, href)
            low_label = label.lower()
            is_followup = any(
                k in low_label
                for k in (
                    "resultado provisório",
                    "resultado provisorio",
                    "resultado preliminar",
                    "resultado final",
                    "resultado da monitoria",
                    "retificação",
                    "retificacao",
                )
            )

            if is_followup and current_group is not None:
                # Verifica se compartilha o mesmo ano/semestre ou número de edital
                curr_year = self._extract_year(current_group["title"], current_group["url_pagina"])
                doc_year = self._extract_year(label, href)
                if curr_year is None or doc_year is None or curr_year == doc_year:
                    if not any(d["url_pdf"] == href for d in current_group["docs"]):
                        current_group["docs"].append(doc)
                    continue

            current_group = {
                "title": label,
                "url_pagina": href,
                "context": parent_text,
                "docs": [doc],
            }
            groups.append(current_group)

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

            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:55]
            results.append(
                self._build_edital_dict(
                    identificador_origem=f"direito-{section}-{slug}",
                    titulo=title,
                    url_pagina=target_url,
                    data_publicacao=pub_date,
                    ano=ano,
                    section=section,
                    resumo=grp["context"] or title,
                    documentos=docs,
                    inicio_inscricao=inicio_insc,
                    fim_inscricao=fim_insc,
                )
            )

        return results

    def _fetch_from_wp_api(self, client: httpx.Client) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        seen_urls: Set[str] = set()

        # 1. Posts do portal Direito
        try:
            resp_posts = client.get(self.WP_POSTS_API_URL, params={"per_page": 50})
            if resp_posts.status_code == 200 and isinstance(resp_posts.json(), list):
                for post in resp_posts.json():
                    if not isinstance(post, dict):
                        continue
                    title = self._strip_html((post.get("title") or {}).get("rendered", ""))
                    link = self._normalize_url(post.get("link", ""))
                    raw_content = (post.get("content") or {}).get("rendered", "")
                    raw_excerpt = (post.get("excerpt") or {}).get("rendered", "")
                    content_text = self._strip_html(raw_content)
                    excerpt_text = self._strip_html(raw_excerpt)

                    if not title or not link or link in seen_urls:
                        continue
                    if not self._is_relevant_edital(title, f"{excerpt_text} {content_text[:300]}", link):
                        continue

                    docs: List[Dict[str, str]] = []
                    if raw_content:
                        frag = BeautifulSoup(raw_content, "html.parser")
                        for a_tag in frag.find_all("a", href=True):
                            href = self._normalize_url(a_tag["href"], base_url=link)
                            if self._is_document_url(href):
                                label = self._clean_text(a_tag.get_text(" ", strip=True)) or href.split("/")[-1]
                                if not any(d["url_pdf"] == href for d in docs):
                                    docs.append(self._make_doc(label, href))

                    raw_date = str(post.get("date") or "")
                    pub_date = raw_date[:10] if len(raw_date) >= 10 else ""
                    txt_pub, inicio_insc, fim_insc = self._extract_dates_from_text(content_text)
                    if not pub_date:
                        pub_date = txt_pub or datetime.now().strftime("%Y-%m-%d")

                    ano = self._extract_year(title, pub_date, link)
                    if not ano and len(pub_date) >= 4 and pub_date[:4].isdigit():
                        ano = int(pub_date[:4])

                    post_id = post.get("id") or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
                    seen_urls.add(link)
                    results.append(
                        self._build_edital_dict(
                            identificador_origem=f"direito-post-{post_id}",
                            titulo=title,
                            url_pagina=link,
                            data_publicacao=pub_date,
                            ano=ano,
                            section="noticias",
                            resumo=excerpt_text or content_text[:400],
                            documentos=docs,
                            inicio_inscricao=inicio_insc,
                            fim_inscricao=fim_insc,
                        )
                    )
        except Exception as e:
            logger.warning(f"Falha ao consultar WP posts API da Faculdade de Direito: {e}")

        # 2. Biblioteca de mídia WP (`/wp-json/wp/v2/media`)
        try:
            resp_media = client.get(self.WP_MEDIA_API_URL, params={"per_page": 50})
            if resp_media.status_code == 200 and isinstance(resp_media.json(), list):
                for media in resp_media.json():
                    if not isinstance(media, dict):
                        continue
                    source_url = self._normalize_url(media.get("source_url", ""))
                    title = self._strip_html((media.get("title") or {}).get("rendered", ""))
                    if not self._is_direct_pdf(source_url) or source_url in seen_urls:
                        continue
                    if not self._is_relevant_edital(title, "", source_url):
                        continue

                    raw_date = str(media.get("date") or "")
                    pub_date = raw_date[:10] if len(raw_date) >= 10 else datetime.now().strftime("%Y-%m-%d")
                    ano = self._extract_year(title, source_url, pub_date)
                    if not ano and len(pub_date) >= 4 and pub_date[:4].isdigit():
                        ano = int(pub_date[:4])

                    media_id = media.get("id") or source_url.split("/")[-1]
                    doc = self._make_doc(title, source_url)
                    seen_urls.add(source_url)
                    results.append(
                        self._build_edital_dict(
                            identificador_origem=f"direito-media-{media_id}",
                            titulo=title,
                            url_pagina=source_url,
                            data_publicacao=pub_date,
                            ano=ano,
                            section="media",
                            resumo=f"Documento de edital/seleção publicado pela Faculdade de Direito/UnB: {title}",
                            documentos=[doc],
                        )
                    )
        except Exception as e:
            logger.warning(f"Falha ao consultar WP media API da Faculdade de Direito: {e}")

        return results

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retorna os editais, chamadas e resultados da Faculdade de Direito da UnB.
        """
        cache_key = f"editais:{year if year is not None else 'all'}"
        now = time.time()
        if cache_key in self._cache:
            ts, cached = self._cache[cache_key]
            if now - ts < self.cache_ttl:
                return [dict(item) for item in cached]

        combined: List[Dict[str, Any]] = []
        seen_doc_urls: Set[str] = set()

        with self._get_client() as client:
            # 1. Páginas de seções oficiais (`/editais/`, `/monitoria/`, `/grupos-de-pesquisa/`, etc.)
            for page_url, section in self.SECTION_URLS:
                try:
                    resp = client.get(page_url)
                    if resp.status_code != 200 or not resp.text:
                        continue
                    section_items = self._parse_section_html(resp.text, page_url=page_url, section=section)
                    for item in section_items:
                        primary_key = (item.get("url_pdf") or item["link"]).rstrip("/").lower()
                        if primary_key not in seen_doc_urls:
                            seen_doc_urls.add(primary_key)
                            for d in item.get("documentos", []):
                                seen_doc_urls.add(d["url_pdf"].rstrip("/").lower())
                            combined.append(item)
                except Exception as e:
                    logger.warning(f"Erro ao raspar seção '{section}' do portal Direito ({page_url}): {e}")

            # 2. WP REST API (posts e PDFs não agrupados nas páginas estáticas)
            for item in self._fetch_from_wp_api(client):
                primary_key = (item.get("url_pdf") or item["link"]).rstrip("/").lower()
                if primary_key not in seen_doc_urls:
                    seen_doc_urls.add(primary_key)
                    combined.append(item)

        if year is not None:
            combined = [item for item in combined if item.get("ano") == year]

        self._cache[cache_key] = (now, [dict(item) for item in combined])
        return combined

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """
        Extrai todos os documentos PDF vinculados a uma URL de edital da Faculdade de Direito.
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
            logger.error(f"Erro ao buscar documentos do edital Direito ({edital_url}): {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        for noise in soup.select("header, footer"):
            noise.decompose()

        content = soup
        docs: List[Dict[str, str]] = []
        seen: Set[str] = set()
        for a_tag in content.find_all("a", href=True):
            href = self._normalize_url(a_tag.get("href", ""), base_url=edital_url)
            if not self._is_document_url(href) or href in seen:
                continue
            seen.add(href)
            label = self._clean_text(a_tag.get_text(" ", strip=True)) or href.split("/")[-1]
            docs.append(self._make_doc(label, href))

        self._docs_by_page[edital_url] = docs
        return [dict(d) for d in docs]

    def download_documento(self, url: str, timeout: float = 15.0) -> bytes:
        with self._get_client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content


direito_scraper = DireitoScraper()

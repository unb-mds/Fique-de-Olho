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


class PRCScraper(BaseScraper):
    """
    Scraper para a Prefeitura do Campus da UnB (PRC / Prefeitura).
    URLs oficiais: https://prc.unb.br/ e https://prefeitura.unb.br/

    Estratégia combinada:
    1. Portal oficial WordPress da Prefeitura (`https://prefeitura.unb.br/`):
       - `/editais-relatorios-e-outros-documentos/` (Editais PRC/COPS, Processos Seletivos PRC,
         notas informativas, resultados provisórios e finais).
       - `/licitacoes/` e `/salas-prc-e-espacos-de-uso-comum/` (permissão de uso, concessão
         de espaços físicos, cantinas, quiosques, destinação de materiais e licitações).
       - API REST WordPress (`/wp-json/wp/v2/posts` e `/media`) filtrando editais, seleções,
         chamadas, permissões de uso e resultados.
    2. Portal Joomla `https://prc.unb.br/` (categorias de artigos e `com_search`),
       aplicando filtro de exclusão de páginas institucionais estáticas no padrão de `fal.py`.
    """

    BASE_URL = "https://prc.unb.br"
    PREFEITURA_URL = "https://prefeitura.unb.br"
    PREFEITURA_EDITAIS_URL = "https://prefeitura.unb.br/editais-relatorios-e-outros-documentos/"
    PREFEITURA_LICITACOES_URL = "https://prefeitura.unb.br/licitacoes/"
    PREFEITURA_ESPACOS_URL = "https://prefeitura.unb.br/salas-prc-e-espacos-de-uso-comum/"

    WP_POSTS_API_URL = "https://prefeitura.unb.br/wp-json/wp/v2/posts"
    WP_MEDIA_API_URL = "https://prefeitura.unb.br/wp-json/wp/v2/media"

    JOOMLA_NEWS_URL = "https://prc.unb.br/index.php?option=com_content&view=category&id=8&Itemid=358"
    JOOMLA_SEARCH_URL = (
        "https://prc.unb.br/index.php?option=com_search&searchword=edital&searchphrase=all&ordering=newest"
    )

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
        "chamamento",
        "processo seletivo",
        "seleção",
        "selecao",
        "permissão de uso",
        "permissao de uso",
        "concessão",
        "concessao",
        "cantina",
        "quiosque",
        "espaço",
        "espaco",
        "licitação",
        "licitacao",
        "pregão",
        "pregao",
        "material lenhoso",
        "resultado provisório",
        "resultado provisorio",
        "resultado preliminar",
        "resultado final",
        "nota informativa",
        "retificação",
        "retificacao",
        "estágio",
        "estagio",
        "estagiário",
        "estagiario",
        "bolsa",
        "auxílio",
        "auxilio",
    )

    STATIC_INSTITUTIONAL_PATTERNS = (
        "quem-somos",
        "gabinete-da-prefeitura",
        "prefeitura-adjunta",
        "estrutura-organizacional",
        "equipe",
        "contato",
        "faq",
        "historico",
        "localizacao",
        "estatuto_e_regimento",
        "resolucao_cplad",
        "resolucao_comissao",
        "escala_prc",
        "dedetizacao",
        "achados-e-perdidos",
        "combate-ao-escorpiao",
        "combate-a-dengue",
    )

    def __init__(self, timeout: float = 20.0, cache_ttl: float = 300.0):
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        self._docs_by_page: Dict[str, List[Dict[str, str]]] = {}

    @property
    def orgao_origem(self) -> str:
        return "PRC"

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
    def _normalize_url(href: str, base_url: str) -> str:
        if not href:
            return ""
        href = href.strip()
        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            return ""
        return urljoin(base_url, href)

    @classmethod
    def _is_static_or_ignored(cls, url: str, title: str = "") -> bool:
        combined = f"{url} {title}".lower()
        for pat in cls.STATIC_INSTITUTIONAL_PATTERNS:
            if pat in combined and "edital" not in title.lower():
                return True
        return False

    @classmethod
    def _is_document_url(cls, url: str, title: str = "") -> bool:
        if not url or cls._is_static_or_ignored(url, title):
            return False
        low = url.lower().split("?")[0]
        if low.endswith((".pdf", ".doc", ".docx", ".zip")):
            return True
        if "drive.google.com/file/d/" in url.lower():
            return True
        return False

    @classmethod
    def _is_direct_pdf(cls, url: str) -> bool:
        if not url:
            return False
        return url.lower().split("?")[0].endswith(".pdf")

    @classmethod
    def _is_relevant_edital(cls, title: str, context: str = "", url: str = "") -> bool:
        if cls._is_static_or_ignored(url, title):
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
            m_up = re.search(r"/(20\d{2})/", text)
            if m_up:
                return int(m_up.group(1))
            years = [int(m) for m in re.findall(r"\b(20\d{2})\b", text) if 2018 <= int(m) <= 2030]
            if years:
                return max(years)
        return None

    @staticmethod
    def _infer_categoria(title: str, summary: str = "") -> str:
        combined = f"{title} {summary}".lower()
        if any(k in combined for k in ("permissão de uso", "permissao de uso", "concessão", "concessao", "cantina", "quiosque", "espaço", "espaco")):
            return "Permissão de Uso / Concessão de Espaço"
        if any(k in combined for k in ("licitação", "licitacao", "pregão", "pregao", "material lenhoso")):
            return "Licitação / Destinação de Bens PRC"
        if any(k in combined for k in ("estágio", "estagio", "estagiário", "estagiario")):
            return "Processo Seletivo de Estágio PRC"
        return "Edital / Aviso PRC"

    @staticmethod
    def _infer_status(title: str, text: str = "", docs: Optional[List[Dict[str, str]]] = None) -> str:
        combined = f"{title} {text}".lower()
        if "resultado final" in combined or "encerrad" in combined or "homologad" in combined:
            return "fechado"
        if docs and any(d.get("tipo_documento") == "resultado_final" for d in docs):
            return "fechado"
        return "aberto"

    @classmethod
    def _make_doc(cls, title: str, url: str) -> Dict[str, str]:
        clean_title = cls._clean_text(title) or "Documento PRC"
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
        resumo: str = "",
        documentos: Optional[List[Dict[str, str]]] = None,
        inicio_inscricao: Optional[str] = None,
        fim_inscricao: Optional[str] = None,
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
            "campus": "Darcy Ribeiro",
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

    def _parse_prefeitura_editais_html(self, html: str, page_url: str = PREFEITURA_EDITAIS_URL) -> List[Dict[str, Any]]:
        """
        Analisa a página `/editais-relatorios-e-outros-documentos/` (e páginas correlatas de
        `prefeitura.unb.br`), agrupando cada Edital de Abertura com suas Notas Informativas,
        Resultados Provisórios e Resultados Finais.
        """
        soup = BeautifulSoup(html, "html.parser")
        for noise in soup.select("header, footer"):
            noise.decompose()

        content = soup
        groups: List[Dict[str, Any]] = []
        current_group: Optional[Dict[str, Any]] = None

        for a_tag in content.find_all("a", href=True):
            href = self._normalize_url(a_tag.get("href", ""), base_url=page_url)
            text = self._clean_text(a_tag.get_text(" ", strip=True))
            if not self._is_document_url(href, text):
                continue

            if not text:
                text = href.split("/")[-1]

            low = text.lower()
            is_followup = any(
                kw in low
                for kw in (
                    "nota informativa",
                    "resultado",
                    "retificação",
                    "retificacao",
                    "chamamento para entrevista",
                    "relação definitiva",
                    "relacao definitiva",
                    "deferimento de inscri",
                    "anexo",
                )
            ) and not low.startswith("edital ")

            doc = self._make_doc(text, href)

            if is_followup and current_group is not None:
                if not any(d["url_pdf"] == href for d in current_group["docs"]):
                    current_group["docs"].append(doc)
                continue

            title = text
            if title.upper() == "EDITAL DE ABERTURA":
                m_ed = re.search(r"Edital[_-]?(\d+)[_-](20\d{2})[_-]?PRC", href, re.IGNORECASE)
                if m_ed:
                    title = f"Edital nº {m_ed.group(1)}/{m_ed.group(2)} - PRC - Processo Seletivo"
                else:
                    title = "Edital de Abertura - Processo Seletivo PRC"

            current_group = {
                "title": title,
                "primary_href": href,
                "docs": [doc],
            }
            groups.append(current_group)

        results: List[Dict[str, Any]] = []
        for idx, grp in enumerate(groups, start=1):
            title = grp["title"]
            docs = grp["docs"]
            primary_href = grp["primary_href"]
            ano = self._extract_year(title, primary_href)
            m_up = re.search(r"/(20\d{2})/(\d{2})/", primary_href)
            if m_up:
                pub_date = f"{m_up.group(1)}-{m_up.group(2)}-01"
            elif ano:
                pub_date = f"{ano}-01-01"
            else:
                pub_date = datetime.now().strftime("%Y-%m-%d")

            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50] or str(idx)
            canonical_url = f"{page_url.rstrip('/')}/#{slug}" if len(docs) > 1 else primary_href

            results.append(
                self._build_edital_dict(
                    identificador_origem=f"prc-edital-{slug}",
                    titulo=title,
                    url_pagina=canonical_url,
                    data_publicacao=pub_date,
                    ano=ano,
                    resumo=f"{title} ({len(docs)} documento(s) oficial(is) publicado(s) pela PRC/UnB)",
                    documentos=docs,
                )
            )

        return results

    def _fetch_from_prefeitura_wp_api(self, client: httpx.Client) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        seen_links: Set[str] = set()

        try:
            resp = client.get(self.WP_POSTS_API_URL, params={"per_page": 30})
            if resp.status_code == 200 and isinstance(resp.json(), list):
                for post in resp.json():
                    if not isinstance(post, dict):
                        continue
                    title = self._strip_html((post.get("title") or {}).get("rendered", ""))
                    link = self._normalize_url(post.get("link", ""), base_url=self.PREFEITURA_URL)
                    raw_content = (post.get("content") or {}).get("rendered", "")
                    raw_excerpt = (post.get("excerpt") or {}).get("rendered", "")
                    content_text = self._strip_html(raw_content)
                    excerpt_text = self._strip_html(raw_excerpt)

                    if not title or not link or link in seen_links:
                        continue
                    if not self._is_relevant_edital(title, excerpt_text, link):
                        continue

                    docs: List[Dict[str, str]] = []
                    if raw_content:
                        frag = BeautifulSoup(raw_content, "html.parser")
                        for a_tag in frag.find_all("a", href=True):
                            href = self._normalize_url(a_tag["href"], base_url=link)
                            label = self._clean_text(a_tag.get_text(" ", strip=True)) or href.split("/")[-1]
                            if self._is_document_url(href, label) and not any(d["url_pdf"] == href for d in docs):
                                docs.append(self._make_doc(label, href))

                    raw_date = str(post.get("date") or "")
                    pub_date = raw_date[:10] if len(raw_date) >= 10 else datetime.now().strftime("%Y-%m-%d")
                    ano = self._extract_year(title, pub_date, link)
                    if not ano and len(pub_date) >= 4 and pub_date[:4].isdigit():
                        ano = int(pub_date[:4])

                    post_id = post.get("id") or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
                    seen_links.add(link)
                    results.append(
                        self._build_edital_dict(
                            identificador_origem=f"prc-wp-post-{post_id}",
                            titulo=title,
                            url_pagina=link,
                            data_publicacao=pub_date,
                            ano=ano,
                            resumo=excerpt_text or content_text[:400],
                            documentos=docs,
                        )
                    )
        except Exception as e:
            logger.warning(f"Falha ao consultar WP posts API da Prefeitura UnB: {e}")

        return results

    def _parse_joomla_prc_html(self, html: str, base_url: str = BASE_URL) -> List[Dict[str, Any]]:
        """
        Analisa listagens de artigos/busca Joomla em `https://prc.unb.br/`,
        filtrando apenas chamadas/editais e descartando páginas estáticas institucionais.
        """
        soup = BeautifulSoup(html, "html.parser")
        results: List[Dict[str, Any]] = []
        seen: Set[str] = set()

        for a_tag in soup.find_all("a", href=True):
            href = self._normalize_url(a_tag.get("href", ""), base_url=base_url)
            title = self._clean_text(a_tag.get_text(" ", strip=True))
            if not href or not title or len(title) < 8 or href in seen:
                continue
            if not ("view=article" in href or "/noticias/" in href or self._is_document_url(href, title)):
                continue
            if not self._is_relevant_edital(title, "", href):
                continue

            seen.add(href)
            parent_text = self._clean_text(a_tag.parent.get_text(" ", strip=True)) if a_tag.parent else title
            ano = self._extract_year(title, parent_text, href)
            pub_date = f"{ano}-01-01" if ano else datetime.now().strftime("%Y-%m-%d")
            m_id = re.search(r"[?&]id=(\d+)", href)
            art_id = m_id.group(1) if m_id else re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
            docs = [self._make_doc(title, href)] if self._is_document_url(href, title) else []

            results.append(
                self._build_edital_dict(
                    identificador_origem=f"prc-joomla-{art_id}",
                    titulo=title,
                    url_pagina=href,
                    data_publicacao=pub_date,
                    ano=ano,
                    resumo=parent_text,
                    documentos=docs,
                )
            )

        return results

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retorna os editais, licitações, permissões de uso e processos seletivos da PRC/UnB.
        """
        cache_key = f"editais:{year if year is not None else 'all'}"
        now = time.time()
        if cache_key in self._cache:
            ts, cached = self._cache[cache_key]
            if now - ts < self.cache_ttl:
                return [dict(item) for item in cached]

        combined: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()

        with self._get_client() as client:
            # 1. Páginas de Editais e Licitações em `https://prefeitura.unb.br`
            for page_url in (self.PREFEITURA_EDITAIS_URL, self.PREFEITURA_LICITACOES_URL):
                try:
                    resp = client.get(page_url)
                    if resp.status_code == 200 and resp.text:
                        for item in self._parse_prefeitura_editais_html(resp.text, page_url=page_url):
                            if item["identificador_origem"] not in seen_ids:
                                seen_ids.add(item["identificador_origem"])
                                combined.append(item)
                except Exception as e:
                    logger.warning(f"Erro ao raspar página da Prefeitura UnB ({page_url}): {e}")

            # 2. WP REST API de `https://prefeitura.unb.br`
            for item in self._fetch_from_prefeitura_wp_api(client):
                if item["identificador_origem"] not in seen_ids:
                    seen_ids.add(item["identificador_origem"])
                    combined.append(item)

            # 3. Portal Joomla `https://prc.unb.br`
            for joomla_url in (self.JOOMLA_NEWS_URL, self.JOOMLA_SEARCH_URL):
                try:
                    resp_j = client.get(joomla_url)
                    if resp_j.status_code == 200 and resp_j.text:
                        for item in self._parse_joomla_prc_html(resp_j.text, base_url=self.BASE_URL):
                            if item["identificador_origem"] not in seen_ids:
                                seen_ids.add(item["identificador_origem"])
                                combined.append(item)
                except Exception as e:
                    logger.warning(f"Erro ao raspar portal Joomla PRC ({joomla_url}): {e}")

        if year is not None:
            combined = [item for item in combined if item.get("ano") == year]

        self._cache[cache_key] = (now, [dict(item) for item in combined])
        return combined

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """
        Extrai todos os documentos (PDFs, notas informativas, resultados) associados a um edital da PRC.
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
            logger.error(f"Erro ao buscar documentos do edital PRC ({edital_url}): {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        for noise in soup.select("header, footer"):
            noise.decompose()

        content = soup
        docs: List[Dict[str, str]] = []
        seen: Set[str] = set()
        for a_tag in content.find_all("a", href=True):
            href = self._normalize_url(a_tag.get("href", ""), base_url=target_url)
            label = self._clean_text(a_tag.get_text(" ", strip=True)) or href.split("/")[-1]
            if self._is_document_url(href, label) and href not in seen:
                seen.add(href)
                docs.append(self._make_doc(label, href))

        self._docs_by_page[edital_url] = docs
        return [dict(d) for d in docs]

    def download_documento(self, url: str, timeout: float = 15.0) -> bytes:
        with self._get_client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content


prc_scraper = PRCScraper()

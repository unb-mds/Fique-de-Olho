"""Scraper para a UnBTV (Canal Universitário da Universidade de Brasília).

Coleta e categoriza editais, seleções públicas de estagiários, bolsistas e projetos técnicos
em Audiovisual, Comunicação, Cinegrafia, Edição, Jornalismo, Programação e PGD UnBTV.

Fontes oficiais:
- Portal de Editais de Seleção da UnBTV:
  https://unbtv.unb.br/editais-de-selecao-2/
- API REST WordPress da UnBTV:
  https://unbtv.unb.br/wp-json/wp/v2/posts?search=edital&per_page=20
"""

from __future__ import annotations

from datetime import datetime, timezone
import html as html_lib
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

logger = logging.getLogger(__name__)

UNBTV_BASE_URL = "https://unbtv.unb.br"
UNBTV_EDITAIS_URL = f"{UNBTV_BASE_URL}/editais-de-selecao-2/"
UNBTV_POSTS_API_URL = f"{UNBTV_BASE_URL}/wp-json/wp/v2/posts?search=edital&per_page=20"

DEFAULT_TIMEOUT = 20.0
CACHE_TTL_SECONDS = 300.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Fique-de-Olho/1.0"
)

DOC_EXTENSIONS = (".pdf", ".doc", ".docx", ".zip", ".odt", ".xlsx", ".xls")
DATE_SLASH_PATTERN = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b")
DATE_ISO_PATTERN = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
DATE_PT_PATTERN = re.compile(
    r"\b(\d{1,2})\s+de\s+(?:janeiro|fevereiro|março|marco|abril|maio|junho|"
    r"julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+(20\d{2})\b",
    re.IGNORECASE,
)
YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")

MESES_PT_NUM = {
    "janeiro": "01",
    "fevereiro": "02",
    "marco": "03",
    "março": "03",
    "abril": "04",
    "maio": "05",
    "junho": "06",
    "julho": "07",
    "agosto": "08",
    "setembro": "09",
    "outubro": "10",
    "novembro": "11",
    "dezembro": "12",
}


def _current_year() -> int:
    """Retorna o ano corrente em UTC para execuções periódicas."""
    return datetime.now(timezone.utc).year


def _clean_str(text: Optional[str]) -> str:
    if not text:
        return ""
    unescaped = html_lib.unescape(text)
    return " ".join(unescaped.strip().split())


def _is_doc_or_form(url: str) -> bool:
    if not url:
        return False
    u_low = url.lower()
    return any(u_low.endswith(ext) or ext in u_low for ext in DOC_EXTENSIONS)


def classify_unbtv_document(title: str, link: str) -> str:
    """Classifica anexos e documentos de seleção da UnBTV."""
    t_low = (title or "").lower()
    l_low = (link or "").lower()
    combined = f"{t_low} {l_low}"

    if "resultado final" in combined or "resultado_final" in combined or "resultado definitivo" in combined:
        return "resultado_final"
    if "resultado preliminar" in combined or "resultado provisório" in combined or "resultado_provisorio" in combined or "provisório" in combined:
        return "resultado_provisorio"
    if "retifica" in combined or "errata" in combined:
        return "retificacao"
    if "homologa" in combined or "convoca" in combined or "lista" in combined:
        return "resultado_provisorio"
    return classify_document(title, link)


def _extract_date_str(text: str, fallback_year: int) -> str:
    """Extrai uma data válida em formato DD/MM/AAAA."""
    if not text:
        return f"01/01/{fallback_year}"
    m_slash = DATE_SLASH_PATTERN.search(text)
    if m_slash:
        dia, mes, ano = int(m_slash.group(1)), int(m_slash.group(2)), int(m_slash.group(3))
        return f"{dia:02d}/{mes:02d}/{ano}"

    m_pt = DATE_PT_PATTERN.search(text)
    if m_pt:
        dia = int(m_pt.group(1))
        mes_raw = m_pt.group(0).lower()
        ano = int(m_pt.group(2))
        for m_nome, m_num in MESES_PT_NUM.items():
            if m_nome in mes_raw:
                return f"{dia:02d}/{m_num}/{ano}"

    m_iso = DATE_ISO_PATTERN.search(text)
    if m_iso:
        ano, mes, dia = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        return f"{dia:02d}/{mes:02d}/{ano}"

    m_year = YEAR_PATTERN.search(text)
    if m_year:
        return f"01/01/{m_year.group(1)}"

    return f"01/01/{fallback_year}"


def _infer_unbtv_tipo(title: str, text: str = "") -> str:
    comb = f"{title} {text}".lower()
    if "estágio" in comb or "estagio" in comb or "estagiário" in comb:
        return "Estágio"
    if "bolsa" in comb or "bolsista" in comb:
        return "Bolsas / Auxílios"
    return "Extensões"


def _infer_unbtv_tipo_edital(title: str) -> str:
    t_low = title.lower()
    if "estágio" in t_low or "estagio" in t_low or "estagiário" in t_low:
        return "Processo Seletivo de Estágio"
    if "pgd" in t_low or "teletrabalho" in t_low:
        return "Processo Seletivo PGD / Teletrabalho"
    if "bolsa" in t_low or "bolsista" in t_low:
        return "Bolsa de Audiovisual e Comunicação"
    return "Processo Seletivo UnBTV"


def parse_unbtv_editais_page(
    html: str,
    base_url: str = UNBTV_EDITAIS_URL,
    reference_year: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Extrai as seções e documentos estruturados da página de editais da UnBTV."""
    curr_yr = reference_year or _current_year()
    soup = BeautifulSoup(html, "html.parser")
    editais: List[Dict[str, Any]] = []

    h4_tags = soup.find_all("h4")
    if not h4_tags:
        return editais

    # Encontra o container que abriga os widgets das seleções
    col = h4_tags[0].find_parent("div", class_=lambda c: c and "elementor-column" in c)
    wrap = col.find("div", class_=lambda c: c and "elementor-widget-wrap" in c) if col else soup

    current_group_title: Optional[str] = None
    group_widgets: Dict[str, List[Any]] = {}

    for w in wrap.find_all("div", class_=lambda c: c and "elementor-widget" in c, recursive=False):
        h4 = w.find("h4")
        if h4:
            current_group_title = _clean_str(h4.get_text())
            group_widgets[current_group_title] = []
            continue

        if current_group_title is not None:
            group_widgets[current_group_title].append(w)

    for g_title, widgets in group_widgets.items():
        m_yr = YEAR_PATTERN.search(g_title)
        g_year = int(m_yr.group(1)) if m_yr else curr_yr

        docs: List[Dict[str, Any]] = []
        date_candidates: List[str] = []
        main_edital_title = g_title
        canonical_link = base_url
        has_resultado_final = False
        text_snippets: List[str] = []

        for w in widgets:
            w_text = _clean_str(w.get_text(" ", strip=True))
            if w_text:
                text_snippets.append(w_text)
                date_candidates.append(w_text)

            for a in w.find_all("a", href=True):
                href = urljoin(base_url, a["href"].strip())
                if any(x in href.lower() for x in ["ouvidoria", "transparencia", "estatuto", "regimento"]):
                    continue
                if _is_doc_or_form(href):
                    t = _clean_str(a.get_text(" ", strip=True)) or href.split("/")[-1]
                    doc_tipo = classify_unbtv_document(t, href)
                    if doc_tipo == "resultado_final":
                        has_resultado_final = True

                    docs.append({
                        "titulo": t,
                        "link": href,
                        "tipo": doc_tipo,
                    })

                    # Se for edital de abertura, define como canonical link e título mais representativo
                    if "edital" in t.lower() and "abertura" in t.lower() or "edital unbtv" in t.lower():
                        canonical_link = href
                        main_edital_title = t
                    elif "edital" in t.lower() and not any(k in t.lower() for k in ["resultado", "análise", "analise", "lista"]):
                        canonical_link = href
                        main_edital_title = t

        if not docs:
            continue

        full_desc = " ".join(text_snippets)
        date_pub = _extract_date_str(" ".join(date_candidates), g_year)
        status = "fechado" if (has_resultado_final or g_year < curr_yr) else "aberto"
        tipo_cat = _infer_unbtv_tipo(main_edital_title, full_desc)
        tipo_ed = _infer_unbtv_tipo_edital(main_edital_title)

        desc = f"Processo seletivo e edital da UnBTV (Canal Universitário da UnB): {main_edital_title}. {full_desc[:300]}".strip()
        resumo = f"Edital UnBTV ({g_year}): {main_edital_title}."

        editais.append({
            "titulo": main_edital_title,
            "assunto": f"Audiovisual e Comunicação / UnBTV — {tipo_ed}",
            "tipo": tipo_cat,
            "tipo_edital": tipo_ed,
            "programa": "Rádio e Televisão Universitárias (UnBTV)",
            "descricao": desc,
            "resumo": resumo,
            "unidade": "UNBTV",
            "campus": "Darcy Ribeiro",
            "link": canonical_link,
            "link_inscricao": None,
            "data_publicacao": date_pub,
            "inicio_inscricao": None,
            "fim_inscricao": None,
            "status": status,
            "ano": g_year,
            "documentos": docs,
        })

    return editais


def parse_unbtv_wp_post(post: Dict[str, Any], reference_year: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Converte post de processo seletivo ou estágio da API REST WordPress da UnBTV."""
    curr_yr = reference_year or _current_year()
    raw_title = post.get("title", {}).get("rendered", "")
    title = _clean_str(raw_title)
    if not title:
        return None

    # Filtra posts irrelevantes sem relação com editais/vagas/oportunidades
    post_title_check = title.lower()
    if not any(k in post_title_check for k in ["edital", "trabalhe", "seleção", "selecao", "estágio", "estagio", "vaga", "bolsa"]):
        return None

    link = post.get("link", "").strip()
    date_raw = post.get("date", "")
    date_pub = date_raw[:10] if date_raw else f"{curr_yr}-01-01"

    m_yr = YEAR_PATTERN.search(title) or YEAR_PATTERN.search(date_pub)
    ed_yr = int(m_yr.group(1)) if m_yr else curr_yr

    content_html = post.get("content", {}).get("rendered", "")
    excerpt_html = post.get("excerpt", {}).get("rendered", "")
    soup_content = BeautifulSoup(content_html, "html.parser")
    clean_desc = _clean_str(soup_content.get_text(" ", strip=True)) or _clean_str(BeautifulSoup(excerpt_html, "html.parser").get_text(" ", strip=True))

    docs: List[Dict[str, Any]] = []
    seen_urls = set()
    link_inscricao: Optional[str] = None
    has_resultado_final = False

    for a in soup_content.find_all("a", href=True):
        href = a["href"].strip()
        text = _clean_str(a.get_text(strip=True)) or href.split("/")[-1]
        if any(x in href.lower() for x in ["forms.gle", "docs.google.com/forms", "inscric"]):
            link_inscricao = href
        if _is_doc_or_form(href) and href not in seen_urls:
            seen_urls.add(href)
            doc_tipo = classify_unbtv_document(text, href)
            if doc_tipo == "resultado_final":
                has_resultado_final = True
            docs.append({
                "titulo": text,
                "link": href,
                "tipo": doc_tipo,
            })

    status = "fechado" if (has_resultado_final or ed_yr < curr_yr) else "aberto"
    tipo_cat = _infer_unbtv_tipo(title, clean_desc)
    tipo_ed = _infer_unbtv_tipo_edital(title)

    return {
        "titulo": title,
        "assunto": f"Audiovisual e Comunicação / UnBTV — {tipo_ed}",
        "tipo": tipo_cat,
        "tipo_edital": tipo_ed,
        "programa": "Rádio e Televisão Universitárias (UnBTV)",
        "descricao": clean_desc or f"Publicação de oportunidade da UnBTV: {title}.",
        "resumo": f"Edital e seleção UnBTV ({ed_yr}): {title}.",
        "unidade": "UNBTV",
        "campus": "Darcy Ribeiro",
        "link": link,
        "link_inscricao": link_inscricao,
        "data_publicacao": date_pub,
        "inicio_inscricao": None,
        "fim_inscricao": None,
        "status": status,
        "ano": ed_yr,
        "documentos": docs,
    }


class UnBTVScraper(BaseScraper):
    """Scraper para o portal de editais e seleções de estágio/audiovisual da UnBTV."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self._url_to_docs_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

    @property
    def orgao_origem(self) -> str:
        return "UNBTV"

    def _cache_set(self, url: str, docs: List[Dict[str, Any]]) -> None:
        self._url_to_docs_cache[url] = (time.time(), docs)

    def _cache_get(self, url: str) -> Optional[List[Dict[str, Any]]]:
        item = self._url_to_docs_cache.get(url)
        if not item:
            return None
        ts, docs = item
        if time.time() - ts > CACHE_TTL_SECONDS:
            self._url_to_docs_cache.pop(url, None)
            return None
        return docs

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Coleta editais e processos seletivos em Audiovisual e PGD da UnBTV."""
        self._url_to_docs_cache.clear()
        curr_year = _current_year()
        editais: List[Dict[str, Any]] = []
        seen_links = set()
        seen_titles = set()

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                # 1. Coleta da página oficial de editais da UnBTV
                try:
                    resp_editais = client.get(UNBTV_EDITAIS_URL)
                    if resp_editais.status_code == 200:
                        parsed_editais = parse_unbtv_editais_page(resp_editais.text, base_url=str(resp_editais.url), reference_year=curr_year)
                        for item in parsed_editais:
                            self._cache_set(item["link"], item.get("documentos", []))
                            norm_t = re.sub(r"[^a-z0-9]+", "", item["titulo"].lower())
                            if item["link"] in seen_links or norm_t in seen_titles:
                                continue
                            if year is not None and item.get("ano") != year:
                                continue
                            seen_links.add(item["link"])
                            seen_titles.add(norm_t)
                            editais.append(item)
                except httpx.HTTPError as exc:
                    logger.warning(f"[UNBTV] Erro ao acessar {UNBTV_EDITAIS_URL}: {exc}")

                # 2. Coleta via WP REST API de posts com palavra-chave 'edital'
                try:
                    resp_api = client.get(UNBTV_POSTS_API_URL)
                    if resp_api.status_code == 200:
                        posts_data = resp_api.json()
                        if isinstance(posts_data, list):
                            for post_obj in posts_data:
                                item = parse_unbtv_wp_post(post_obj, reference_year=curr_year)
                                if not item:
                                    continue
                                self._cache_set(item["link"], item.get("documentos", []))
                                norm_t = re.sub(r"[^a-z0-9]+", "", item["titulo"].lower())
                                if item["link"] in seen_links or norm_t in seen_titles:
                                    continue
                                if year is not None and item.get("ano") != year:
                                    continue
                                seen_links.add(item["link"])
                                seen_titles.add(norm_t)
                                editais.append(item)
                except (httpx.HTTPError, ValueError, TypeError) as exc:
                    logger.warning(f"[UNBTV] Erro ao consultar API de posts da UnBTV: {exc}")

        except Exception as exc:
            logger.error(f"[UNBTV] Erro geral na coleta: {exc}")
            return editais

        return editais

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Recupera ou extrai documentos vinculados a uma seleção da UnBTV."""
        if not edital_url:
            return []

        cached = self._cache_get(edital_url)
        if cached is not None:
            return cached

        if _is_doc_or_form(edital_url):
            doc = [{
                "titulo": _clean_str(edital_url.split("/")[-1]),
                "link": edital_url,
                "tipo": classify_unbtv_document(edital_url, edital_url),
            }]
            self._cache_set(edital_url, doc)
            return doc

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
                    docs = []
                    for a in soup.find_all("a", href=True):
                        h = urljoin(str(resp.url), a["href"].strip())
                        t = _clean_str(a.get_text(strip=True)) or h.split("/")[-1]
                        if any(x in h.lower() for x in ["ouvidoria", "transparencia", "estatuto", "regimento"]):
                            continue
                        if _is_doc_or_form(h):
                            docs.append({
                                "titulo": t,
                                "link": h,
                                "tipo": classify_unbtv_document(t, h),
                            })
                    self._cache_set(edital_url, docs)
                    return docs
        except Exception as exc:
            logger.warning(f"[UNBTV] Erro ao buscar documentos em {edital_url}: {exc}")

        return []


unbtv_scraper = UnBTVScraper()

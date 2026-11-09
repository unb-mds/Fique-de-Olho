"""Scraper para a EDU (Editora da Universidade de Brasília).

Coleta e categoriza chamadas e editais para submissão de originais de livros,
coletâneas e publicações acadêmicas, editais de credenciamento, estágios,
bolsas de preservação de acervo e chamamentos da Festa do Livro da UnB.

Fontes oficiais:
- Portal de Editais da Editora UnB:
  https://editora.unb.br/editais/
- API REST WordPress da Editora UnB:
  https://editora.unb.br/wp-json/wp/v2/posts?search=edital&per_page=20
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

EDU_BASE_URL = "https://editora.unb.br"
EDU_EDITAIS_URL = f"{EDU_BASE_URL}/editais/"
EDU_POSTS_API_URL = f"{EDU_BASE_URL}/wp-json/wp/v2/posts?search=edital&per_page=20"

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
    """Retorna o ano corrente em UTC para coletas dinâmicas periódicas."""
    return datetime.now(timezone.utc).year


def _clean_str(text: Optional[str]) -> str:
    if not text:
        return ""
    unescaped = html_lib.unescape(text)
    return " ".join(unescaped.strip().split())


def _is_doc_or_subpage(url: str) -> bool:
    if not url:
        return False
    u_low = url.lower()
    return (
        any(u_low.endswith(ext) or ext in u_low for ext in DOC_EXTENSIONS)
        or "estagio.unb.br" in u_low
        or "livros.unb.br" in u_low
    )


def classify_edu_document(title: str, link: str) -> str:
    """Classifica anexos e documentos da Editora UnB."""
    t_low = (title or "").lower()
    l_low = (link or "").lower()
    combined = f"{t_low} {l_low}"

    if "resultado final" in combined or "resultado definitivo" in combined or "resultado_final" in combined:
        return "resultado_final"
    if "resultado preliminar" in combined or "resultado provisório" in combined or "resultado provisorio" in combined:
        return "resultado_provisorio"
    if "retifica" in combined or "errata" in combined:
        return "retificacao"
    if "minuta" in combined or "termo de referência" in combined or "termo de referencia" in combined or "estudo técnico" in combined:
        return "original"
    if "formulário" in combined or "formulario" in combined or "requerimento" in combined:
        return "original"
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


def _infer_edu_tipo(title: str, text: str = "") -> str:
    comb = f"{title} {text}".lower()
    if "estágio" in comb or "estagio" in comb or "estagiár" in comb or "estagiar" in comb:
        return "Estágio"
    if "bolsa" in comb or "auxílio" in comb or "auxilio" in comb:
        return "Bolsas / Auxílios"
    if "livro" in comb or "publicação" in comb or "publicacao" in comb or "coletânea" in comb or "original" in comb:
        return "Pesquisa"
    return "Extensões"


def _infer_edu_tipo_edital(title: str) -> str:
    t_low = title.lower()
    if "publicação de livro" in t_low or "livro" in t_low or "original" in t_low or "coletânea" in t_low:
        return "Publicação de Livros Acadêmicos"
    if "credenciamento" in t_low:
        return "Credenciamento"
    if "estágio" in t_low or "estagiário" in t_low:
        return "Processo Seletivo de Estágio"
    if "bolsista" in t_low or "acervo" in t_low:
        return "Bolsa de Preservação de Acervo"
    if "festa do livro" in t_low or "patrocínio" in t_low or "patrocinador" in t_low:
        return "Festa do Livro / Patrocínio"
    return "Edital Editorial"


def parse_edu_editais_page(
    html: str,
    base_url: str = EDU_EDITAIS_URL,
    reference_year: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Extrai os blocos estruturados de editais e anexos da página oficial editora.unb.br/editais/."""
    curr_yr = reference_year or _current_year()
    soup = BeautifulSoup(html, "html.parser")
    editais: List[Dict[str, Any]] = []

    container = soup.find("div", class_=lambda c: c and ("elementor-26162" in c or "entry-content" in c)) or soup
    sections = container.find_all("section", recursive=False)
    if not sections:
        sections = soup.find_all("section")

    current_status = "aberto"
    current_edital: Optional[Dict[str, Any]] = None

    for sec in sections:
        txt = _clean_str(sec.get_text(" ", strip=True))
        txt_low = txt.lower()

        if "editais abertos" in txt_low:
            current_status = "aberto"
            continue
        if "editais encerrados" in txt_low:
            current_status = "fechado"
            continue

        h2 = sec.find("h2")
        if h2:
            h2_txt = _clean_str(h2.get_text())
            if any(k in h2_txt.lower() for k in ["edital", "chamada", "credenciamento"]):
                if current_edital:
                    editais.append(current_edital)

                m_yr = YEAR_PATTERN.search(h2_txt)
                ed_yr = int(m_yr.group(1)) if m_yr else curr_yr
                current_edital = {
                    "raw_title": h2_txt,
                    "status": current_status,
                    "year": ed_yr,
                    "docs": [],
                    "date_texts": [],
                    "link_inscricao": None,
                    "canonical_link": base_url,
                }
                continue

        if current_edital is not None:
            # Captura documentos desta subseção
            for a in sec.find_all("a", href=True):
                href = urljoin(base_url, a["href"].strip())
                if any(x in href.lower() for x in ["estatuto", "regimento", "politica_de_cookies", "telefones"]):
                    continue
                if _is_doc_or_subpage(href):
                    # Procura o H3 mais próximo dentro da coluna ou seção interna
                    col = a.find_parent("div", class_=lambda c: c and "elementor-column" in c)
                    h3 = col.find("h3") if col else None
                    if not h3:
                        inner_sec = a.find_parent("section", class_=lambda c: c and "elementor-inner-section" in c)
                        h3 = inner_sec.find("h3") if inner_sec else None

                    doc_title = _clean_str(h3.get_text()) if h3 else _clean_str(a.get_text(strip=True)) or href.split("/")[-1]
                    doc_tipo = classify_edu_document(doc_title, href)

                    current_edital["docs"].append({
                        "titulo": doc_title,
                        "link": href,
                        "tipo": doc_tipo,
                    })
                    current_edital["date_texts"].append(txt)

                    # Se for edital principal em PDF, define como canonical link
                    if ("edital" in doc_title.lower() or "credenciamento" in doc_title.lower()) and "anexo" not in doc_title.lower() and "termo" not in doc_title.lower() and "resultado" not in doc_title.lower():
                        current_edital["canonical_link"] = href

    if current_edital:
        editais.append(current_edital)

    final_editais: List[Dict[str, Any]] = []
    for ed in editais:
        title = ed["raw_title"]
        ed_yr = ed["year"]
        combined_text = " ".join([title] + ed["date_texts"])
        date_pub = _extract_date_str(combined_text, ed_yr)

        has_resultado_final = any(d["tipo"] == "resultado_final" for d in ed["docs"])
        status = "fechado" if (has_resultado_final or ed["status"] == "fechado" or ed_yr < curr_yr) else "aberto"
        tipo_cat = _infer_edu_tipo(title, combined_text)
        tipo_ed = _infer_edu_tipo_edital(title)

        desc = f"Edital e chamada da Editora da Universidade de Brasília (EDU/UnB): {title}."
        resumo = f"Edital EDU ({ed_yr}): {title}."

        final_editais.append({
            "titulo": title,
            "assunto": f"Editorial e Publicações / EDU — {tipo_ed}",
            "tipo": tipo_cat,
            "tipo_edital": tipo_ed,
            "programa": "Editora UnB (EDU/UnB)",
            "descricao": desc,
            "resumo": resumo,
            "unidade": "EDU",
            "campus": "Darcy Ribeiro",
            "link": ed["canonical_link"],
            "link_inscricao": ed["link_inscricao"],
            "data_publicacao": date_pub,
            "inicio_inscricao": None,
            "fim_inscricao": None,
            "status": status,
            "ano": ed_yr,
            "documentos": ed["docs"],
        })

    return final_editais


def parse_edu_wp_post(post: Dict[str, Any], reference_year: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Converte um item de post da API REST da Editora UnB em um registro de edital/oportunidade."""
    curr_yr = reference_year or _current_year()
    raw_title = post.get("title", {}).get("rendered", "")
    title = _clean_str(raw_title)
    if not title:
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

    post_title_check = title.lower()
    if not any(k in post_title_check for k in ["edital", "chamada", "seleção", "selecao", "inscrições", "inscricoes", "bolsa", "estágio", "estagio", "credenciamento", "vaga", "patrocínio", "patrocinio", "espaço autoral", "selecionados"]):
        return None

    docs: List[Dict[str, Any]] = []
    seen_urls = set()
    link_inscricao: Optional[str] = None
    has_resultado_final = False

    for a in soup_content.find_all("a", href=True):
        href = a["href"].strip()
        text = _clean_str(a.get_text(strip=True)) or href.split("/")[-1]
        if any(x in href.lower() for x in ["forms.gle", "docs.google.com/forms", "inscric"]):
            link_inscricao = href
        if _is_doc_or_subpage(href) and href not in seen_urls:
            seen_urls.add(href)
            doc_tipo = classify_edu_document(text, href)
            if doc_tipo == "resultado_final":
                has_resultado_final = True
            docs.append({
                "titulo": text,
                "link": href,
                "tipo": doc_tipo,
            })

    status = "fechado" if (has_resultado_final or ed_yr < curr_yr) else "aberto"
    tipo_cat = _infer_edu_tipo(title, clean_desc)
    tipo_ed = _infer_edu_tipo_edital(title)

    return {
        "titulo": title,
        "assunto": f"Editorial e Publicações / EDU — {tipo_ed}",
        "tipo": tipo_cat,
        "tipo_edital": tipo_ed,
        "programa": "Editora UnB (EDU/UnB)",
        "descricao": clean_desc or f"Publicação oficial da Editora UnB: {title}.",
        "resumo": f"Edital e chamada EDU ({ed_yr}): {title}.",
        "unidade": "EDU",
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


class EDUScraper(BaseScraper):
    """Scraper para o portal de chamadas e editais da Editora UnB (EDU)."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self._url_to_docs_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

    @property
    def orgao_origem(self) -> str:
        return "EDU"

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
        """Coleta editais e chamadas de publicações, livros e bolsas da Editora UnB."""
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
                # 1. Coleta da página oficial de editais editora.unb.br/editais/
                try:
                    resp_editais = client.get(EDU_EDITAIS_URL)
                    if resp_editais.status_code == 200:
                        parsed_editais = parse_edu_editais_page(resp_editais.text, base_url=str(resp_editais.url), reference_year=curr_year)
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
                    logger.warning(f"[EDU] Erro ao acessar {EDU_EDITAIS_URL}: {exc}")

                # 2. Coleta via WP REST API de posts com palavra-chave 'edital'
                try:
                    resp_api = client.get(EDU_POSTS_API_URL)
                    if resp_api.status_code == 200:
                        posts_data = resp_api.json()
                        if isinstance(posts_data, list):
                            for post_obj in posts_data:
                                item = parse_edu_wp_post(post_obj, reference_year=curr_year)
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
                    logger.warning(f"[EDU] Erro ao consultar API de posts da EDU: {exc}")

        except Exception as exc:
            logger.error(f"[EDU] Erro geral na coleta: {exc}")
            return editais

        return editais

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Recupera ou extrai documentos vinculados a um edital da Editora UnB."""
        if not edital_url:
            return []

        cached = self._cache_get(edital_url)
        if cached is not None:
            return cached

        if _is_doc_or_subpage(edital_url):
            doc = [{
                "titulo": _clean_str(edital_url.split("/")[-1]),
                "link": edital_url,
                "tipo": classify_edu_document(edital_url, edital_url),
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
                        if any(x in h.lower() for x in ["estatuto", "regimento", "politica_de_cookies"]):
                            continue
                        if _is_doc_or_subpage(h):
                            docs.append({
                                "titulo": t,
                                "link": h,
                                "tipo": classify_edu_document(t, h),
                            })
                    self._cache_set(edital_url, docs)
                    return docs
        except Exception as exc:
            logger.warning(f"[EDU] Erro ao buscar documentos em {edital_url}: {exc}")

        return []


edu_scraper = EDUScraper()

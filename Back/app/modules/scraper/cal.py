"""Scraper para a CAL / IdA (Casa da Cultura da América Latina / Instituto de Artes da UnB).

Coleta e categoriza chamadas públicas, editais de ocupação de galerias (Galeria CAL,
Galeria Acervo, Galeria de Bolso), mediação cultural, mostras e residências artísticas,
editais da Rede CUC (Casas Universitárias de Cultura) e editais do Instituto de Artes (IdA).

Fontes oficiais:
- Portal Institucional da CAL (Casa da Cultura da América Latina):
  https://cal.unb.br/
- Diretoria de Difusão Cultural (DDC/DEX — Unidade gestora das Casas de Cultura e CAL):
  https://ddc.unb.br/editais
  https://ddc.unb.br/editalredecuc/
  https://ddc.unb.br/edital-rede-cuc-2025/
  https://ddc.unb.br/casas/cal/
- Portal de Editais do Instituto de Artes (IdA/UnB):
  https://ida.unb.br/edita/ida
  https://ida.unb.br/editais
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

CAL_BASE_URL = "https://cal.unb.br"
DDC_BASE_URL = "https://ddc.unb.br"
DDC_EDITAIS_URL = f"{DDC_BASE_URL}/editais"
DDC_CUC_2026_URL = f"{DDC_BASE_URL}/editalredecuc/"
DDC_CUC_2025_URL = f"{DDC_BASE_URL}/edital-rede-cuc-2025/"
DDC_CASAS_CAL_URL = f"{DDC_BASE_URL}/casas/cal/"
IDA_BASE_URL = "https://ida.unb.br"
IDA_EDITAIS_URL = f"{IDA_BASE_URL}/edita/ida"

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


def _is_doc(url: str) -> bool:
    if not url:
        return False
    u_lower = url.lower()
    return any(u_lower.endswith(ext) or ext in u_lower for ext in DOC_EXTENSIONS)


def classify_cal_document(title: str, link: str) -> str:
    """Classifica o tipo de documento cultural para editais da CAL/IdA."""
    t_low = (title or "").lower()
    l_low = (link or "").lower()
    combined = f"{t_low} {l_low}"

    if "resultado final" in combined or "resultado definitivo" in combined or "resultado_final" in combined:
        return "resultado_final"
    if "resultado preliminar" in combined or "resultado provisório" in combined or "resultado provisorio" in combined or "rp.pdf" in combined:
        return "resultado_provisorio"
    if "retifica" in combined or "errata" in combined:
        return "retificacao"
    if "homologa" in combined or "convoca" in combined or "recurso" in combined or "comissão" in combined or "comissao" in combined:
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


def _infer_cal_tipo(title: str, text: str = "") -> str:
    comb = f"{title} {text}".lower()
    if "bolsa" in comb or "auxílio" in comb or "auxilio" in comb:
        return "Bolsas / Auxílios"
    if "estágio" in comb or "estagio" in comb:
        return "Estágio"
    if "pesquisa" in comb:
        return "Pesquisa"
    return "Extensões"


def _infer_cal_tipo_edital(title: str) -> str:
    t_low = title.lower()
    if "galeria" in t_low or "ocupação" in t_low or "ocupacao" in t_low:
        return "Ocupação de Galerias"
    if "residência" in t_low or "residencia" in t_low:
        return "Residência Artística"
    if "mostra" in t_low or "exposição" in t_low or "exposicao" in t_low or "foto" in t_low:
        return "Mostra Cultural"
    if "rede cuc" in t_low or "cuc" in t_low:
        return "Ocupação Cultural Rede CUC"
    if "bolsa" in t_low or "extensão" in t_low or "extensao" in t_low:
        return "Bolsa Artística / Extensão"
    if "chamada" in t_low:
        return "Chamada Cultural"
    return "Edital Cultural"


def parse_ddc_cuc_page(
    html: str,
    page_url: str,
    default_title: str,
    reference_year: Optional[int] = None,
) -> Dict[str, Any]:
    """Analisa uma página de edital da Rede CUC / CAL no portal da DDC/DEX."""
    curr_yr = reference_year or _current_year()
    soup = BeautifulSoup(html, "html.parser")

    # Extrai o título principal
    title_elem = soup.find("h1", class_=lambda c: c and "entry-title" in c) or soup.find("h1")
    title = _clean_str(title_elem.get_text()) if title_elem else default_title

    m_yr = YEAR_PATTERN.search(title) or YEAR_PATTERN.search(page_url)
    ed_yr = int(m_yr.group(1)) if m_yr else curr_yr

    # Conteúdo principal
    content = soup.find("div", class_=lambda c: c and ("entry-content" in c or "page-content" in c)) or soup
    body_text = _clean_str(content.get_text(" ", strip=True))

    # Extrai todos os documentos da página
    docs: List[Dict[str, Any]] = []
    seen_urls = set()
    has_resultado_final = False

    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"].strip())
        text = _clean_str(a.get_text(strip=True)) or href.split("/")[-1]
        if not _is_doc(href) and not any(k in href.lower() for k in [".pdf", ".docx", ".doc"]):
            continue
        if any(x in href.lower() for x in ["estatuto", "regimento", "politica_de_cookies", "resolucao_cplad", "mprazer", "telefones"]):
            continue
        if href in seen_urls:
            continue
        seen_urls.add(href)

        doc_tipo = classify_cal_document(text, href)
        if doc_tipo == "resultado_final":
            has_resultado_final = True

        docs.append({
            "titulo": text,
            "link": href,
            "tipo": doc_tipo,
        })

    date_pub = _extract_date_str(body_text[:500], ed_yr)
    status = "fechado" if (has_resultado_final or ed_yr < curr_yr) else "aberto"
    tipo_cat = _infer_cal_tipo(title, body_text)
    tipo_ed = _infer_cal_tipo_edital(title)

    desc = f"Edital e chamada de ocupação artística e cultural da Casa da Cultura da América Latina (CAL) / Rede CUC: {title}."
    resumo = f"Edital publicado pela CAL / DDC ({ed_yr}): {title}."

    return {
        "titulo": title,
        "assunto": f"Cultura e Artes / CAL — {tipo_ed}",
        "tipo": tipo_cat,
        "tipo_edital": tipo_ed,
        "programa": "Casa da Cultura da América Latina (CAL/UnB)",
        "descricao": desc,
        "resumo": resumo,
        "unidade": "CAL",
        "campus": "Darcy Ribeiro",
        "link": page_url,
        "link_inscricao": None,
        "data_publicacao": date_pub,
        "inicio_inscricao": None,
        "fim_inscricao": None,
        "status": status,
        "ano": ed_yr,
        "documentos": docs,
    }


def parse_ida_article_page(
    html: str,
    article_url: str,
    default_title: str,
    reference_year: Optional[int] = None,
) -> Dict[str, Any]:
    """Analisa um artigo de edital do Instituto de Artes (ida.unb.br/edita/ida/...)."""
    curr_yr = reference_year or _current_year()
    soup = BeautifulSoup(html, "html.parser")

    title_elem = soup.find(["h1", "h2"], class_=lambda c: c and "item-title" in c) or soup.find("h2")
    title = _clean_str(title_elem.get_text()) if title_elem else default_title

    m_yr = YEAR_PATTERN.search(title) or YEAR_PATTERN.search(article_url)
    ed_yr = int(m_yr.group(1)) if m_yr else curr_yr

    content = soup.find("div", itemprop="articleBody") or soup.find("div", class_="item-page") or soup
    body_text = _clean_str(content.get_text(" ", strip=True))

    docs: List[Dict[str, Any]] = []
    seen_urls = set()
    has_resultado_final = False
    link_inscricao: Optional[str] = None

    for a in soup.find_all("a", href=True):
        href = urljoin(article_url, a["href"].strip())
        text = _clean_str(a.get_text(strip=True)) or href.split("/")[-1]

        # Detecta links de formulário externo / inscrição (ex: FUNAPE, Google Forms)
        if any(x in href.lower() for x in ["processo_seletivo", "forms.gle", "docs.google.com/forms", "inscricao", "inscricoes"]):
            link_inscricao = href

        if not _is_doc(href) and not any(k in href.lower() for k in [".pdf", ".docx", ".doc"]):
            continue
        if any(x in href.lower() for x in ["estatuto", "regimento", "politica_de_cookies", "resolucao_cplad", "mprazer", "telefones"]):
            continue
        if href in seen_urls:
            continue
        seen_urls.add(href)

        doc_tipo = classify_cal_document(text, href)
        if doc_tipo == "resultado_final":
            has_resultado_final = True

        docs.append({
            "titulo": text,
            "link": href,
            "tipo": doc_tipo,
        })

    date_pub = _extract_date_str(body_text[:500], ed_yr)
    status = "fechado" if (has_resultado_final or ed_yr < curr_yr) else "aberto"
    tipo_cat = _infer_cal_tipo(title, body_text)
    tipo_ed = _infer_cal_tipo_edital(title)

    desc = f"Edital e processo seletivo do Instituto de Artes (IdA/UnB): {title}."
    resumo = f"Edital publicado pelo Instituto de Artes (IdA) ({ed_yr}): {title}."

    return {
        "titulo": title,
        "assunto": f"Artes e Cultura / IdA — {tipo_ed}",
        "tipo": tipo_cat,
        "tipo_edital": tipo_ed,
        "programa": "Instituto de Artes (IdA/UnB)",
        "descricao": desc,
        "resumo": resumo,
        "unidade": "CAL",
        "campus": "Darcy Ribeiro",
        "link": article_url,
        "link_inscricao": link_inscricao,
        "data_publicacao": date_pub,
        "inicio_inscricao": None,
        "fim_inscricao": None,
        "status": status,
        "ano": ed_yr,
        "documentos": docs,
    }


def parse_ddc_editais_listing(
    html: str,
    base_url: str = DDC_EDITAIS_URL,
    reference_year: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Extrai chamadas e links de editais da página geral de editais da DDC (ddc.unb.br/editais)."""
    curr_yr = reference_year or _current_year()
    soup = BeautifulSoup(html, "html.parser")
    editais: List[Dict[str, Any]] = []

    content = soup.find("div", class_=lambda c: c and ("entry-content" in c or "page-content" in c)) or soup

    for a in content.find_all("a", href=True):
        href = urljoin(base_url, a["href"].strip())
        text = _clean_str(a.get_text(strip=True))
        if not text or len(text) < 4:
            continue
        if any(x in href.lower() for x in ["estatuto", "regimento", "politica_de_cookies", "telefones"]):
            continue

        if any(k in text.lower() or k in href.lower() for k in ["edital", "chamada", "selecao", "exposicao", "foto central", "cuc"]):
            m_yr = YEAR_PATTERN.search(text) or YEAR_PATTERN.search(href)
            ed_yr = int(m_yr.group(1)) if m_yr else curr_yr
            date_pub = _extract_date_str(text, ed_yr)
            doc_tipo = classify_cal_document(text, href)
            status = "fechado" if (doc_tipo == "resultado_final" or ed_yr < curr_yr) else "aberto"
            tipo_cat = _infer_cal_tipo(text)
            tipo_ed = _infer_cal_tipo_edital(text)

            docs = [{
                "titulo": text,
                "link": href,
                "tipo": doc_tipo,
            }] if _is_doc(href) else []

            editais.append({
                "titulo": text,
                "assunto": f"Cultura e Artes / CAL — {tipo_ed}",
                "tipo": tipo_cat,
                "tipo_edital": tipo_ed,
                "programa": "Casa da Cultura da América Latina (CAL/DDC)",
                "descricao": f"Chamada e oportunidade cultural da Casa da Cultura da América Latina (CAL): {text}.",
                "resumo": f"Edital e chamada cultural DDC/CAL ({ed_yr}): {text}.",
                "unidade": "CAL",
                "campus": "Darcy Ribeiro",
                "link": href,
                "link_inscricao": None,
                "data_publicacao": date_pub,
                "inicio_inscricao": None,
                "fim_inscricao": None,
                "status": status,
                "ano": ed_yr,
                "documentos": docs,
            })

    return editais


class CALScraper(BaseScraper):
    """Scraper para editais da Casa da Cultura da América Latina (CAL) e Instituto de Artes (IdA)."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self._url_to_docs_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

    @property
    def orgao_origem(self) -> str:
        return "CAL"

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
        """Coleta editais e chamadas de ocupação e cultura da CAL e do Instituto de Artes."""
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
                # 1. Tenta acessar o domínio cal.unb.br com tolerância a HTTP 500/indisponibilidade
                try:
                    resp_cal = client.get(CAL_BASE_URL)
                    if resp_cal.status_code == 200:
                        soup = BeautifulSoup(resp_cal.text, "html.parser")
                        for a in soup.find_all("a", href=True):
                            t = _clean_str(a.get_text(strip=True))
                            h = urljoin(str(resp_cal.url), a["href"].strip())
                            if any(k in t.lower() or k in h.lower() for k in ["edital", "chamada", "galeria", "residencia"]):
                                if h not in seen_links:
                                    seen_links.add(h)
                                    m_yr = YEAR_PATTERN.search(t) or YEAR_PATTERN.search(h)
                                    ey = int(m_yr.group(1)) if m_yr else curr_year
                                    editais.append({
                                        "titulo": t,
                                        "assunto": "Cultura e Galerias / CAL",
                                        "tipo": _infer_cal_tipo(t),
                                        "tipo_edital": _infer_cal_tipo_edital(t),
                                        "programa": "Casa da Cultura da América Latina (CAL/UnB)",
                                        "descricao": f"Edital e chamada da CAL: {t}.",
                                        "resumo": f"Edital CAL ({ey}): {t}.",
                                        "unidade": "CAL",
                                        "campus": "Darcy Ribeiro",
                                        "link": h,
                                        "link_inscricao": None,
                                        "data_publicacao": f"01/01/{ey}",
                                        "inicio_inscricao": None,
                                        "fim_inscricao": None,
                                        "status": "aberto" if ey >= curr_year else "fechado",
                                        "ano": ey,
                                        "documentos": [],
                                    })
                except httpx.HTTPError as exc:
                    logger.warning(f"[CAL] Servidor cal.unb.br temporariamente indisponível ({exc}); utilizando fontes DDC/DEX e IdA.")

                # 2. Coleta dos editais específicos da Rede CUC (Casas Universitárias de Cultura / CAL)
                cuc_pages = [
                    (DDC_CUC_2026_URL, "Edital Rede CUC 2026 — Ocupação das Galerias da CAL e Casas de Cultura"),
                    (DDC_CUC_2025_URL, "Edital Rede CUC 2025 — Ocupação das Galerias da CAL e Casas de Cultura"),
                ]
                for cuc_url, default_t in cuc_pages:
                    try:
                        resp_cuc = client.get(cuc_url)
                        if resp_cuc.status_code == 200:
                            item = parse_ddc_cuc_page(resp_cuc.text, str(resp_cuc.url), default_title=default_t, reference_year=curr_year)
                            self._cache_set(item["link"], item.get("documentos", []))
                            norm_t = re.sub(r"[^a-z0-9]+", "", item["titulo"].lower())
                            if item["link"] not in seen_links and norm_t not in seen_titles:
                                if year is None or item.get("ano") == year:
                                    seen_links.add(item["link"])
                                    seen_titles.add(norm_t)
                                    editais.append(item)
                    except httpx.HTTPError as exc:
                        logger.warning(f"[CAL] Erro ao consultar {cuc_url}: {exc}")

                # 3. Coleta da listagem geral de editais e chamadas da DDC (ddc.unb.br/editais)
                try:
                    resp_ddc = client.get(DDC_EDITAIS_URL)
                    if resp_ddc.status_code == 200:
                        ddc_items = parse_ddc_editais_listing(resp_ddc.text, base_url=str(resp_ddc.url), reference_year=curr_year)
                        for item in ddc_items:
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
                    logger.warning(f"[CAL] Erro ao consultar {DDC_EDITAIS_URL}: {exc}")

                # 4. Coleta dos editais do Instituto de Artes (ida.unb.br/edita/ida)
                try:
                    resp_ida = client.get(IDA_EDITAIS_URL)
                    if resp_ida.status_code == 200:
                        soup_ida = BeautifulSoup(resp_ida.text, "html.parser")
                        ida_articles: List[Tuple[str, str]] = []
                        for h in soup_ida.find_all(["h2", "h3"]):
                            a = h.find("a", href=True)
                            if a:
                                art_url = urljoin(str(resp_ida.url), a["href"].strip())
                                art_t = _clean_str(a.get_text(strip=True))
                                if "/edita/ida/" in art_url and art_url not in seen_links:
                                    ida_articles.append((art_url, art_t))

                        for art_url, art_t in ida_articles:
                            try:
                                art_resp = client.get(art_url)
                                if art_resp.status_code == 200:
                                    ida_item = parse_ida_article_page(art_resp.text, str(art_resp.url), default_title=art_t, reference_year=curr_year)
                                    self._cache_set(ida_item["link"], ida_item.get("documentos", []))
                                    norm_t = re.sub(r"[^a-z0-9]+", "", ida_item["titulo"].lower())
                                    if ida_item["link"] not in seen_links and norm_t not in seen_titles:
                                        if year is None or ida_item.get("ano") == year:
                                            seen_links.add(ida_item["link"])
                                            seen_titles.add(norm_t)
                                            editais.append(ida_item)
                            except httpx.HTTPError as a_exc:
                                logger.warning(f"[CAL/IdA] Erro ao consultar artigo {art_url}: {a_exc}")
                except httpx.HTTPError as exc:
                    logger.warning(f"[CAL/IdA] Erro ao consultar {IDA_EDITAIS_URL}: {exc}")

        except Exception as exc:
            logger.error(f"[CAL] Erro geral na coleta: {exc}")
            return editais

        return editais

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Recupera ou extrai documentos vinculados a um edital da CAL/IdA."""
        if not edital_url:
            return []

        cached = self._cache_get(edital_url)
        if cached is not None:
            return cached

        if _is_doc(edital_url):
            doc = [{
                "titulo": _clean_str(edital_url.split("/")[-1]),
                "link": edital_url,
                "tipo": classify_cal_document(edital_url, edital_url),
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
                        if _is_doc(h):
                            docs.append({
                                "titulo": t,
                                "link": h,
                                "tipo": classify_cal_document(t, h),
                            })
                    self._cache_set(edital_url, docs)
                    return docs
        except Exception as exc:
            logger.warning(f"[CAL] Erro ao buscar documentos em {edital_url}: {exc}")

        return []


cal_scraper = CALScraper()

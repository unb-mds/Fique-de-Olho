"""Scraper para o CDT (Centro de Apoio ao Desenvolvimento Tecnológico da UnB).

Coleta chamadas públicas e editais de inovação, incubação de startups
(Multincubadora), Fábrica de Spin-off, Programa PRISMA, PRISMA Mulher
(Mulheres Inovadoras), empresas juniores e bolsas de projetos tecnológicos.

Fontes oficiais:
- Portal de Chamadas Públicas CDT: https://cdt.unb.br/pt-br/chamadas
- Edital de Fluxo Contínuo Multincubadora: https://cdt.unb.br/pt-br/chamadas/409-chamadas-publicas-2024/683-edital-de-fluxo-continuo-para-incubacao-de-empreendimentos-inovadores-na-multincubadora-da-unb
"""

from __future__ import annotations

from datetime import datetime, timezone
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

CDT_BASE_URL = "https://cdt.unb.br"
CDT_CHAMADAS_URL = f"{CDT_BASE_URL}/pt-br/chamadas"
CDT_MULTINCUBADORA_URL = (
    f"{CDT_BASE_URL}/pt-br/chamadas/409-chamadas-publicas-2024/"
    "683-edital-de-fluxo-continuo-para-incubacao-de-empreendimentos-inovadores-na-multincubadora-da-unb"
)

DEFAULT_TIMEOUT = 20.0
CACHE_TTL_SECONDS = 300.0
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Fique-de-Olho/1.0"

EDITAL_YEAR_PATTERN = re.compile(r"\b\d{1,4}/(20\d{2})\b")
GENERAL_YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")
DATE_SLASH_PATTERN = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
DATE_PT_PATTERN = re.compile(
    r"\b(\d{1,2}\s+de\s+[A-Za-zÀ-ÿ]+\s+de\s+\d{4})\b",
    re.IGNORECASE,
)
DATE_PT_SHORT_PATTERN = re.compile(
    r"\b(\d{1,2}\s+de\s+(?:janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro))\b",
    re.IGNORECASE,
)


def _current_year() -> int:
    """Retorna o ano corrente em UTC para execuções periódicas."""
    return datetime.now(timezone.utc).year


def classify_cdt_document(title: str, link: str) -> str:
    """Classifica um documento vinculado a um edital do CDT."""
    lower = f"{title} {link}".lower()
    if any(k in lower for k in ["resultado final", "resultado_final", "resultado-final", "resultado fina", "homologacao", "homologação"]):
        return "resultado_final"
    if any(k in lower for k in ["resultado preliminar", "resultado_preliminar", "resultado provisorio", "resultado provisório", "1ª etapa", "2ª etapa"]):
        return "resultado_provisorio"
    if any(k in lower for k in ["retificacao", "retificação", "retificado", "retifica", "prorrogacao", "prorrogação", "suspensao", "suspensão"]):
        return "retificacao"
    return classify_document(title, link)


def classify_cdt_edital(titulo: str, texto: str = "") -> Dict[str, str]:
    """Determina o tipo, tipo_edital e programa de uma chamada pública do CDT/UnB."""
    combined = f"{titulo} {texto}".lower()

    if "prisma mulher" in combined or "mulheres inovadoras" in combined:
        return {
            "tipo": "Inovação e Empreendedorismo Feminino",
            "tipo_edital": "Inovação / Programa PRISMA Mulher",
            "programa": "PRISMA Mulher",
        }
    if "prisma" in combined:
        return {
            "tipo": "Inovação e Apoio a Projetos",
            "tipo_edital": "Inovação / Programa PRISMA",
            "programa": "Programa PRISMA",
        }
    if any(k in combined for k in ["spinoff", "spin-off", "incubação", "incubacao", "multincubadora", "hotel de projetos", "startup"]):
        return {
            "tipo": "Incubação de Startups e Spin-offs",
            "tipo_edital": "Empreendedorismo / Multincubadora e Spin-off",
            "programa": "Multincubadora / Fábrica de Spin-off",
        }
    if any(k in combined for k in ["empresa júnior", "empresa junior", "pró-júnior", "pro-junior", "pró jr", "pro jr"]):
        return {
            "tipo": "Empresas Juniores",
            "tipo_edital": "Empreendedorismo / Empresas Juniores",
            "programa": "Programa Pró-Júnior",
        }
    if any(k in combined for k in ["bolsa", "bolsista", "seleção de pesquisadores", "selecao de pesquisadores"]):
        return {
            "tipo": "Bolsas de Inovação e P&D",
            "tipo_edital": "Pesquisa e Inovação / Bolsa CDT",
            "programa": "Pesquisa e Desenvolvimento CDT",
        }
    return {
        "tipo": "Inovação e Desenvolvimento Tecnológico",
        "tipo_edital": "Inovação / Chamada Pública CDT",
        "programa": "CDT/UnB",
    }


def _extract_docs_and_meta_from_node(node: Any, base_url: str) -> Dict[str, Any]:
    """Extrai documentos anexos, datas e descrição a partir de um bloco HTML do CDT."""
    documentos: List[Dict[str, Any]] = []
    seen_docs = set()
    has_final = False
    has_suspension = False
    data_pub = ""
    link_inscricao = ""

    for a in node.find_all("a", href=True):
        href = str(a["href"]).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue

        full_url = urljoin(base_url, href)
        text = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
        lower_href = full_url.lower()
        lower_text = text.lower()

        if "forms.office.com" in lower_href or "forms.gle" in lower_href or "formulário de inscrição" in lower_text:
            link_inscricao = full_url
            continue

        is_doc = (
            lower_href.endswith((".pdf", ".doc", ".docx", ".zip"))
            or "/images/cdt/" in lower_href
            or "/images/editais_cdt/" in lower_href
            or "/images/cedes/" in lower_href
            or "/attachments/" in lower_href
        )
        if not is_doc:
            continue

        if full_url in seen_docs:
            continue
        seen_docs.add(full_url)

        # Verifica se há data ao lado do link no elemento pai
        parent_text = a.parent.get_text(" ", strip=True) if a.parent else ""
        m_date = DATE_SLASH_PATTERN.search(parent_text) or DATE_SLASH_PATTERN.search(text)
        doc_date = m_date.group(1) if m_date else ""
        if not data_pub and doc_date:
            data_pub = doc_date

        doc_title = text or "Documento Oficial CDT"
        doc_type = classify_cdt_document(doc_title, full_url)
        if doc_type == "resultado_final":
            has_final = True
        if "suspensão" in lower_text or "suspensao" in lower_text:
            has_suspension = True

        documentos.append({
            "titulo": doc_title,
            "link": full_url,
            "data": doc_date,
            "tipo": doc_type,
        })

    # Extração de parágrafos descritivos
    paragraphs: List[str] = []
    for p in node.find_all("p"):
        t = re.sub(r"\s+", " ", p.get_text(" ", strip=True)).strip()
        if len(t) > 40 and not any(t.lower().startswith(prefix) for prefix in ["edital de abertura", "resultado", "1ª retificação", "anexo"]):
            if t not in paragraphs:
                paragraphs.append(t)

    descricao_texto = " ".join(paragraphs[:2]).strip()
    short_date = ""

    if not data_pub:
        full_text = node.get_text(" ", strip=True)
        m_slash = DATE_SLASH_PATTERN.search(full_text)
        if m_slash:
            data_pub = m_slash.group(1)
        else:
            m_pt = DATE_PT_PATTERN.search(full_text)
            if m_pt:
                data_pub = m_pt.group(1)
            else:
                m_short = DATE_PT_SHORT_PATTERN.search(full_text)
                if m_short:
                    short_date = m_short.group(1)

    return {
        "documentos": documentos,
        "has_final": has_final,
        "has_suspension": has_suspension,
        "data_publicacao": data_pub,
        "short_date": short_date,
        "link_inscricao": link_inscricao,
        "descricao_texto": descricao_texto,
    }


def parse_cdt_chamadas_html(
    html: str,
    base_url: str = CDT_BASE_URL,
    reference_year: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Extrai todos os editais e chamadas públicas listados em uma página de /pt-br/chamadas."""
    curr_year = reference_year or _current_year()
    soup = BeautifulSoup(html or "", "html.parser")
    blog = soup.find("div", class_=lambda c: c and "blog" in c.split()) or soup
    editais: List[Dict[str, Any]] = []
    seen_links = set()

    posts = blog.find_all("div", itemprop="blogPost")
    for post in posts:
        h2_name = post.find(["h2", "h3"], itemprop="name") or post.find(["h2", "h3"])
        if not h2_name:
            continue

        a_title = h2_name.find("a", href=True)
        titulo = re.sub(r"\s+", " ", h2_name.get_text(" ", strip=True)).strip()
        if not titulo:
            continue

        if a_title:
            link = urljoin(base_url, str(a_title["href"]).strip())
        else:
            slug = re.sub(r"[^a-z0-9]+", "-", titulo.lower()).strip("-")[:60]
            link = f"{CDT_CHAMADAS_URL}#{slug}"

        if link in seen_links:
            continue
        seen_links.add(link)

        # Verifica se há cabeçalho de data anterior na linha (items-row)
        row_parent = post.find_parent("div", class_=lambda c: c and "items-row" in c)
        header_date = ""
        if row_parent:
            prev_h2 = row_parent.find_previous_sibling("h2")
            if prev_h2:
                m_pt = DATE_PT_PATTERN.search(prev_h2.get_text(" ", strip=True))
                if m_pt:
                    header_date = m_pt.group(1)

        meta = _extract_docs_and_meta_from_node(post, base_url=base_url)
        data_pub = meta["data_publicacao"] or header_date

        # Ano do edital
        ano: Optional[int] = None
        m_ed_year = EDITAL_YEAR_PATTERN.search(titulo)
        if m_ed_year:
            ano = int(m_ed_year.group(1))
        else:
            m_gen_year = GENERAL_YEAR_PATTERN.search(titulo) or GENERAL_YEAR_PATTERN.search(data_pub) or GENERAL_YEAR_PATTERN.search(link)
            if m_gen_year:
                ano = int(m_gen_year.group(1))

        if not data_pub:
            if meta.get("short_date") and ano:
                data_pub = f"{meta['short_date']} de {ano}"
            elif ano:
                data_pub = f"01/01/{ano}"
            else:
                data_pub = f"01/01/{curr_year}"

        if ano is None:
            ano = curr_year

        cat_info = classify_cdt_edital(titulo, meta["descricao_texto"])
        is_closed = (
            meta["has_final"]
            or meta["has_suspension"]
            or "resultado final" in titulo.lower()
            or (ano is not None and ano < (curr_year - 1) and "fluxo contínuo" not in titulo.lower())
        )
        status = "fechado" if is_closed else "aberto"

        assunto = f"Chamada Pública CDT/UnB ({cat_info['programa']}) - {titulo}"
        descricao = meta["descricao_texto"] or f"Chamada pública conduzida pelo Centro de Apoio ao Desenvolvimento Tecnológico (CDT/UnB) no âmbito do programa {cat_info['programa']}: {titulo}."

        editais.append({
            "titulo": titulo,
            "assunto": assunto,
            "tipo": cat_info["tipo"],
            "tipo_edital": cat_info["tipo_edital"],
            "programa": cat_info["programa"],
            "descricao": descricao,
            "resumo": descricao,
            "unidade": "CDT",
            "link": link,
            "link_inscricao": meta["link_inscricao"],
            "data_publicacao": data_pub,
            "status": status,
            "ano": ano,
            "documentos": meta["documentos"],
        })

    return editais


def parse_cdt_article_html(
    html: str,
    page_url: str,
    reference_year: Optional[int] = None,
) -> Dict[str, Any]:
    """Extrai dados completos e PDFs de uma página individual de edital do CDT."""
    curr_year = reference_year or _current_year()
    soup = BeautifulSoup(html or "", "html.parser")
    container = (
        soup.find("div", class_="item-page")
        or soup.find("div", itemprop="articleBody")
        or soup.find("div", id="content")
        or soup
    )

    h_el = container.find(["h1", "h2"]) or soup.find(["h1", "h2"])
    titulo = re.sub(r"\s+", " ", h_el.get_text(" ", strip=True)).strip() if h_el else "Edital CDT/UnB"

    meta = _extract_docs_and_meta_from_node(container, base_url=page_url)
    data_pub = meta["data_publicacao"]

    ano: Optional[int] = None
    m_year = EDITAL_YEAR_PATTERN.search(titulo) or GENERAL_YEAR_PATTERN.search(titulo) or GENERAL_YEAR_PATTERN.search(page_url) or GENERAL_YEAR_PATTERN.search(data_pub)
    if m_year:
        ano = int(m_year.group(1))

    if not data_pub:
        if meta.get("short_date") and ano:
            data_pub = f"{meta['short_date']} de {ano}"
        elif ano:
            data_pub = f"01/01/{ano}"
        else:
            data_pub = f"01/01/{curr_year}"

    if ano is None:
        ano = curr_year

    cat_info = classify_cdt_edital(titulo, meta["descricao_texto"])
    is_closed = (
        meta["has_final"]
        or meta["has_suspension"]
        or (ano is not None and ano < (curr_year - 1) and "fluxo contínuo" not in titulo.lower())
    )
    status = "fechado" if is_closed else "aberto"

    assunto = f"Chamada Pública CDT/UnB ({cat_info['programa']}) - {titulo}"
    descricao = meta["descricao_texto"] or f"Edital do Centro de Apoio ao Desenvolvimento Tecnológico da UnB ({cat_info['programa']}): {titulo}."

    return {
        "titulo": titulo,
        "assunto": assunto,
        "tipo": cat_info["tipo"],
        "tipo_edital": cat_info["tipo_edital"],
        "programa": cat_info["programa"],
        "descricao": descricao,
        "resumo": descricao,
        "unidade": "CDT",
        "link": page_url,
        "link_inscricao": meta["link_inscricao"],
        "data_publicacao": data_pub,
        "status": status,
        "ano": ano,
        "documentos": meta["documentos"],
    }


class CDTScraper(BaseScraper):
    """Implementação do scraper para o CDT (Centro de Desenvolvimento Tecnológico da UnB)."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT, cache_ttl: float = CACHE_TTL_SECONDS) -> None:
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._url_to_docs_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

    @property
    def orgao_origem(self) -> str:
        """Identificador institucional do órgão."""
        return "CDT"

    def _cache_set(self, url: str, docs: List[Dict[str, Any]]) -> None:
        if url:
            self._url_to_docs_cache[url] = (time.monotonic(), docs)

    def _cache_get(self, url: str) -> Optional[List[Dict[str, Any]]]:
        entry = self._url_to_docs_cache.get(url)
        if not entry:
            return None
        ts, docs = entry
        if (time.monotonic() - ts) > self.cache_ttl:
            self._url_to_docs_cache.pop(url, None)
            return None
        return docs

    def fetch_editais(
        self,
        year: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Coleta todas as chamadas públicas e editais de incubação e inovação do CDT/UnB.

        Args:
            year: Ano de referência para filtragem opcional (ex: 2026, 2025).
            max_pages: Limite máximo de páginas de /pt-br/chamadas a percorrer (None para todas as 29 páginas).

        Returns:
            Lista de dicionários padronizados de editais do CDT.
        """
        self._url_to_docs_cache.clear()
        editais: List[Dict[str, Any]] = []
        seen_links = set()
        seen_title_keys = set()

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                # 1. Percorre a listagem paginada de chamadas públicas (/pt-br/chamadas?start=0, 10, ...)
                page_idx = 0
                max_offset = 280  # 29 páginas (0 a 280 de 10 em 10)

                while page_idx * 10 <= max_offset:
                    if max_pages is not None and page_idx >= max_pages:
                        break

                    offset = page_idx * 10
                    url = f"{CDT_CHAMADAS_URL}?start={offset}" if offset > 0 else CDT_CHAMADAS_URL
                    try:
                        resp = client.get(url)
                        if resp.status_code != 200:
                            break
                        page_items = parse_cdt_chamadas_html(resp.text, base_url=str(resp.url))
                        if not page_items:
                            break
                    except httpx.HTTPError as exc:
                        logger.warning(f"Erro ao consultar página start={offset} do CDT: {exc}")
                        break

                    page_years: List[int] = []
                    for item in page_items:
                        if item["link"]:
                            self._cache_set(item["link"], item["documentos"])
                        if item.get("ano"):
                            page_years.append(item["ano"])

                        if year is not None and item.get("ano") is not None and item["ano"] != year:
                            continue

                        title_key = (re.sub(r"\s+", " ", item["titulo"].lower()).strip(), item.get("ano"))
                        if item["link"] not in seen_links and title_key not in seen_title_keys:
                            seen_links.add(item["link"])
                            seen_title_keys.add(title_key)
                            editais.append(item)

                    # Otimização cronológica: se filtramos por ano e a página inteira é anterior ao ano buscado
                    if year is not None and page_years and max(page_years) < year:
                        break

                    page_idx += 1

                # 2. Garante a inclusão do Edital de Fluxo Contínuo da Multincubadora de Empresas
                if CDT_MULTINCUBADORA_URL not in seen_links:
                    try:
                        resp_inc = client.get(CDT_MULTINCUBADORA_URL)
                        if resp_inc.status_code == 200:
                            inc_edital = parse_cdt_article_html(resp_inc.text, str(resp_inc.url))
                            if inc_edital["link"]:
                                self._cache_set(inc_edital["link"], inc_edital["documentos"])
                            inc_title_key = (re.sub(r"\s+", " ", inc_edital["titulo"].lower()).strip(), inc_edital.get("ano"))
                            if (year is None or inc_edital.get("ano") == year) and inc_title_key not in seen_title_keys:
                                seen_links.add(inc_edital["link"])
                                seen_title_keys.add(inc_title_key)
                                editais.append(inc_edital)
                    except httpx.HTTPError as exc:
                        logger.warning(f"Erro ao consultar edital da Multincubadora CDT: {exc}")

        except Exception as exc:
            logger.error(f"Erro geral no scraper do CDT: {exc}")
            return editais

        return editais

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai todos os documentos PDF vinculados a uma página de edital do CDT."""
        if not edital_url:
            return []

        cached = self._cache_get(edital_url)
        if cached is not None:
            return cached

        if edital_url.lower().endswith(".pdf"):
            return [{
                "titulo": "Documento Oficial CDT",
                "link": edital_url,
                "tipo": classify_cdt_document(edital_url, edital_url),
            }]

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                resp = client.get(edital_url)
                if resp.status_code == 200:
                    parsed = parse_cdt_article_html(resp.text, str(resp.url))
                    docs = parsed.get("documentos", [])
                    self._cache_set(edital_url, docs)
                    return docs
        except Exception as exc:
            logger.warning(f"Erro ao extrair documentos do CDT em {edital_url}: {exc}")

        return []


cdt_scraper = CDTScraper()

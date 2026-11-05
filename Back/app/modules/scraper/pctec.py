"""Scraper para o PCTec (Parque Científico e Tecnológico da UnB).

Coleta editais de ocupação e cessão de uso de áreas/laboratórios no Parque
Tecnológico para startups e Empresas de Base Tecnológica (EBTs), chamadas de
Residência Tecnológica (Saúde Digital / Ocean UnB, Residência em TIC 53),
seleção de bolsistas e chamadas de Laboratórios Multiusuários de IA e
Supercomputação.

Fontes oficiais:
- Página Oficial de Ofertas Públicas / Chamadas: https://pctec.unb.br/chamadas/
- API REST WordPress de Páginas do PCTec: https://pctec.unb.br/wp-json/wp/v2/pages
"""

from __future__ import annotations

import html as html_lib
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

logger = logging.getLogger(__name__)

PCTEC_BASE_URL = "https://pctec.unb.br"
PCTEC_CHAMADAS_URL = f"{PCTEC_BASE_URL}/chamadas/"
PCTEC_PAGES_API_URL = f"{PCTEC_BASE_URL}/wp-json/wp/v2/pages"

DEFAULT_TIMEOUT = 20.0
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Fique-de-Olho/1.0"

EDITAL_YEAR_PATTERN = re.compile(r"\b\d{1,4}[./](20\d{2})\b")
GENERAL_YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")


def _clean_text(raw: str) -> str:
    """Remove tags HTML, decodifica entidades e normaliza espaços."""
    if not raw:
        return ""
    unescaped = html_lib.unescape(raw)
    text = BeautifulSoup(unescaped, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def normalize_pctec_url(url: str, base_url: str = PCTEC_BASE_URL) -> str:
    """Normaliza URLs do PCTec, substituindo domínios internos de homologação pelo domínio público."""
    if not url:
        return ""
    full = urljoin(base_url, url.strip())
    return full.replace("https://pctec.sites.homologa.unb.br", PCTEC_BASE_URL).replace(
        "http://pctec.sites.homologa.unb.br", PCTEC_BASE_URL
    )


def classify_pctec_document(title: str, link: str) -> str:
    """Classifica um documento vinculado a um edital do PCTec."""
    lower = f"{title} {link}".lower()
    if any(k in lower for k in ["resultado final", "resultado_final", "resultado-final", "resultado fase ii", "homologacao", "homologação"]):
        return "resultado_final"
    if any(k in lower for k in ["resultado preliminar", "resultado_preliminar", "resultado provisorio", "resultado provisório", "resultado fase i", "resultado de habilitação", "resultado da fase de habilitação", "resultado_habilitacao"]):
        return "resultado_provisorio"
    if any(k in lower for k in ["retificacao", "retificação", "retificado", "rev2", "prorrogacao", "prorrogação", "aditivo"]):
        return "retificacao"
    return classify_document(title, link)


def classify_pctec_edital(titulo: str, texto: str = "") -> Dict[str, str]:
    """Determina o tipo, tipo_edital e programa de um edital do PCTec/UnB."""
    combined = f"{titulo} {texto}".lower()

    if any(k in combined for k in ["residência", "residencia", "bolsista", "ocean", "saúde digital", "saude digital"]) or re.search(r"\btic\b", combined):
        return {
            "tipo": "Residência Tecnológica e Bolsas P&D",
            "tipo_edital": "Inovação / Residência Tecnológica e Bolsas",
            "programa": "Residência Tecnológica PCTec/UnB",
        }
    if any(k in combined for k in ["laboratório", "laboratorio", "supercomputação", "supercomputacao", "inteligência artificial", "inteligencia artificial", "multiusuário", "multiusuario"]):
        return {
            "tipo": "Infraestrutura de Pesquisa e IA",
            "tipo_edital": "Inovação / Ocupação de Laboratórios e IA",
            "programa": "Laboratórios Multiusuários e IA",
        }
    if any(k in combined for k in ["chamamento público", "chamamento publico", "fluxo contínuo", "fluxo continuo", "uso contínuo", "uso continuo", "concorrência", "concorrencia", "pré-qualificação", "pre-qualificacao", "cessão de uso", "cessao de uso", "área de", "area de"]):
        return {
            "tipo": "Ocupação e Residência de Empresas no Parque",
            "tipo_edital": "Parque Tecnológico / Chamamento de Empresas e Laboratórios",
            "programa": "Residência Empresarial PCTec",
        }
    return {
        "tipo": "Inovação e Parceria Tecnológica",
        "tipo_edital": "Parque Tecnológico / Chamada PCTec",
        "programa": "PCTec/UnB",
    }


def parse_pctec_edital_page_html(
    html: str,
    page_url: str,
    default_title: str = "",
    default_status: Optional[str] = None,
    data_publicacao: str = "",
) -> Dict[str, Any]:
    """Extrai metadados, descrição e todos os anexos PDF de uma página de edital do PCTec."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup.select("header, footer, nav"):
        tag.decompose()

    container = (
        soup.find("div", class_="entry-content")
        or soup.find("div", class_="elementor")
        or soup.find("main")
        or soup
    )

    titulo = default_title
    if not titulo:
        h_el = container.find(["h1", "h2", "h3"]) or soup.find(["h1", "h2"])
        if h_el:
            titulo = _clean_text(h_el.get_text(" ", strip=True))
    titulo = titulo or "Edital PCTec/UnB"

    documentos: List[Dict[str, Any]] = []
    seen_docs = set()
    has_final = False

    for a in container.find_all("a", href=True):
        raw_href = str(a["href"]).strip()
        if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:")):
            continue

        full_url = normalize_pctec_url(raw_href, base_url=page_url)
        lower_href = full_url.lower()
        if not (lower_href.endswith((".pdf", ".doc", ".docx", ".zip")) or "/wp-content/uploads/" in lower_href):
            continue

        if full_url in seen_docs:
            continue
        seen_docs.add(full_url)

        doc_title = _clean_text(a.get_text(" ", strip=True)) or "Documento Oficial PCTec"
        doc_type = classify_pctec_document(doc_title, full_url)
        if doc_type == "resultado_final":
            has_final = True

        documentos.append({
            "titulo": doc_title,
            "link": full_url,
            "tipo": doc_type,
        })

    paragraphs: List[str] = []
    for p in container.find_all("p"):
        t = _clean_text(p.get_text(" ", strip=True))
        if len(t) > 45 and t not in paragraphs:
            paragraphs.append(t)
    descricao_texto = " ".join(paragraphs[:2]).strip()

    # Determinação do ano
    ano: Optional[int] = None
    m_ed_year = EDITAL_YEAR_PATTERN.search(titulo)
    if m_ed_year:
        ano = int(m_ed_year.group(1))
    else:
        m_gen_year = GENERAL_YEAR_PATTERN.search(titulo) or GENERAL_YEAR_PATTERN.search(page_url)
        if m_gen_year:
            ano = int(m_gen_year.group(1))
        elif data_publicacao and len(data_publicacao) >= 4 and data_publicacao[:4].isdigit():
            ano = int(data_publicacao[:4])

    if default_status in ("aberto", "fechado"):
        status = default_status
    else:
        status = "fechado" if (has_final or (ano is not None and ano < 2024)) else "aberto"

    cat_info = classify_pctec_edital(titulo, descricao_texto)
    assunto = f"Chamada Pública PCTec/UnB ({cat_info['programa']}) - {titulo}"
    descricao = (
        descricao_texto
        or f"Edital do Parque Científico e Tecnológico da Universidade de Brasília ({cat_info['programa']}): {titulo}."
    )

    return {
        "titulo": titulo,
        "assunto": assunto,
        "tipo": cat_info["tipo"],
        "tipo_edital": cat_info["tipo_edital"],
        "programa": cat_info["programa"],
        "descricao": descricao,
        "resumo": descricao,
        "unidade": "PCTEC",
        "link": normalize_pctec_url(page_url),
        "data_publicacao": data_publicacao or (f"{ano}-01-01" if ano else ""),
        "status": status,
        "ano": ano,
        "documentos": documentos,
    }


def parse_pctec_chamadas_overview_html(html: str, base_url: str = PCTEC_BASE_URL) -> List[Dict[str, Any]]:
    """Extrai a lista de editais abertos e encerrados da página Ofertas Públicas (/chamadas/) do PCTec."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup.select("header, footer, nav"):
        tag.decompose()

    container = (
        soup.find("div", class_="entry-content")
        or soup.find("div", class_="elementor")
        or soup.find("main")
        or soup
    )

    items: List[Dict[str, Any]] = []
    seen_links = set()
    current_status = "aberto"
    pending_historical_group: Optional[Dict[str, Any]] = None

    for el in container.find_all(["h2", "h3", "li", "p"]):
        # Evita duplicar elementos contenedores que possuem filhos de bloco
        if el.name in ("li", "p") and el.find(["li", "p", "h2", "h3"]):
            continue

        text = _clean_text(el.get_text(" ", strip=True))
        if not text:
            continue

        lower_text = text.lower()
        if el.name in ("h2", "h3"):
            if "encerrado" in lower_text:
                current_status = "fechado"
                pending_historical_group = None
                continue
            if "aberto" in lower_text or "oferta" in lower_text:
                current_status = "aberto"
                pending_historical_group = None
                continue

        # Ignora parágrafos puramente introdutórios sem links e sem menção a Edital nº
        links = el.find_all("a", href=True)
        if not links:
            if re.search(r"Edital\s+de\s+(?:Pré-Qualificação|Concorrência)\s+n[º°.]?\s*\d+/\d{4}", text, re.IGNORECASE):
                m_year = EDITAL_YEAR_PATTERN.search(text) or GENERAL_YEAR_PATTERN.search(text)
                ano = int(m_year.group(1)) if m_year else None
                slug = re.sub(r"[^a-z0-9]+", "-", lower_text).strip("-")
                group_link = f"{PCTEC_CHAMADAS_URL}#{slug}"
                cat_info = classify_pctec_edital(text)
                assunto = f"Chamada Pública PCTec/UnB ({cat_info['programa']}) - {text}"
                descricao = f"Edital histórico do Parque Científico e Tecnológico da UnB ({cat_info['programa']}): {text}."
                pending_historical_group = {
                    "titulo": text,
                    "assunto": assunto,
                    "tipo": cat_info["tipo"],
                    "tipo_edital": cat_info["tipo_edital"],
                    "programa": cat_info["programa"],
                    "descricao": descricao,
                    "resumo": descricao,
                    "unidade": "PCTEC",
                    "link": group_link,
                    "data_publicacao": f"{ano}-01-01" if ano else "",
                    "status": "fechado",
                    "ano": ano,
                    "documentos": [],
                    "is_complete": True,
                }
                if group_link not in seen_links:
                    seen_links.add(group_link)
                    items.append(pending_historical_group)
            continue

        # Se os links apontam direto para PDFs de resultado de um edital histórico anterior (2014/2015)
        first_href = normalize_pctec_url(str(links[0]["href"]), base_url=base_url)
        if first_href.lower().endswith(".pdf"):
            if pending_historical_group is not None:
                for a in links:
                    doc_url = normalize_pctec_url(str(a["href"]), base_url=base_url)
                    doc_title = _clean_text(a.get_text(" ", strip=True)) or text
                    pending_historical_group["documentos"].append({
                        "titulo": doc_title,
                        "link": doc_url,
                        "tipo": classify_pctec_document(doc_title, doc_url),
                    })
                continue

        # Caso padrão: item que aponta para uma página dedicada de edital no PCTec
        pending_historical_group = None
        target_url = first_href
        if target_url in seen_links:
            continue
        seen_links.add(target_url)

        m_year = EDITAL_YEAR_PATTERN.search(text) or GENERAL_YEAR_PATTERN.search(text) or GENERAL_YEAR_PATTERN.search(target_url)
        ano = int(m_year.group(1)) if m_year else None
        cat_info = classify_pctec_edital(text)
        assunto = f"Chamada Pública PCTec/UnB ({cat_info['programa']}) - {text}"
        descricao = f"Edital do Parque Científico e Tecnológico da Universidade de Brasília ({cat_info['programa']}): {text}."

        items.append({
            "titulo": text,
            "assunto": assunto,
            "tipo": cat_info["tipo"],
            "tipo_edital": cat_info["tipo_edital"],
            "programa": cat_info["programa"],
            "descricao": descricao,
            "resumo": descricao,
            "unidade": "PCTEC",
            "link": target_url,
            "data_publicacao": f"{ano}-01-01" if ano else "",
            "status": current_status,
            "ano": ano,
            "documentos": [],
            "is_complete": False,
        })

    return items


class PCTecScraper(BaseScraper):
    """Implementação do scraper para o PCTec (Parque Científico e Tecnológico da UnB)."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self._url_to_docs_cache: Dict[str, List[Dict[str, Any]]] = {}

    @property
    def orgao_origem(self) -> str:
        """Identificador institucional do órgão."""
        return "PCTEC"

    def fetch_editais(
        self,
        year: Optional[int] = None,
        max_details: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Coleta todos os editais e ofertas públicas do PCTec/UnB.

        Args:
            year: Ano de referência para filtragem opcional (ex: 2026, 2025, 2024).
            max_details: Limite opcional de páginas individuais de editais a inspecionar.

        Returns:
            Lista de dicionários padronizados de editais do PCTec.
        """
        editais: List[Dict[str, Any]] = []
        seen_links = set()

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                # 1. Obtém a página central de Ofertas Públicas (/chamadas/) via API WP ou HTML direto
                overview_html = ""
                try:
                    resp_api = client.get(PCTEC_PAGES_API_URL, params={"slug": "chamadas"})
                    if resp_api.status_code == 200:
                        data = resp_api.json()
                        if isinstance(data, list) and data:
                            overview_html = (data[0].get("content") or {}).get("rendered") or ""
                except (httpx.HTTPError, ValueError):
                    overview_html = ""

                if not overview_html:
                    try:
                        resp_html = client.get(PCTEC_CHAMADAS_URL)
                        if resp_html.status_code == 200:
                            overview_html = resp_html.text
                    except httpx.HTTPError as exc:
                        logger.warning(f"Erro ao consultar página de chamadas do PCTec: {exc}")
                        return editais

                overview_items = parse_pctec_chamadas_overview_html(overview_html, base_url=PCTEC_BASE_URL)

                # 2. Para cada item listado, resolve a página de detalhes (via slug na API WP ou GET HTML)
                inspected_count = 0
                for item in overview_items:
                    link = item["link"]
                    if item.get("is_complete"):
                        item_clean = {k: v for k, v in item.items() if k != "is_complete"}
                        self._url_to_docs_cache[link] = item_clean["documentos"]
                        if year is not None and item_clean.get("ano") is not None and item_clean["ano"] != year:
                            continue
                        if link not in seen_links:
                            seen_links.add(link)
                            editais.append(item_clean)
                        continue

                    if max_details is not None and inspected_count >= max_details:
                        item_clean = {k: v for k, v in item.items() if k != "is_complete"}
                        if year is not None and item_clean.get("ano") is not None and item_clean["ano"] != year:
                            continue
                        if link not in seen_links:
                            seen_links.add(link)
                            editais.append(item_clean)
                        continue

                    inspected_count += 1
                    slug = urlparse(link).path.strip("/").split("/")[-1]
                    detail_parsed: Optional[Dict[str, Any]] = None

                    if slug:
                        try:
                            resp_pg = client.get(PCTEC_PAGES_API_URL, params={"slug": slug})
                            if resp_pg.status_code == 200:
                                pg_list = resp_pg.json()
                                if isinstance(pg_list, list) and pg_list:
                                    pg_obj = pg_list[0]
                                    pg_html = (pg_obj.get("content") or {}).get("rendered") or ""
                                    pg_date = str(pg_obj.get("date") or "")[:10]
                                    detail_parsed = parse_pctec_edital_page_html(
                                        pg_html,
                                        page_url=link,
                                        default_title=item["titulo"],
                                        default_status=item["status"],
                                        data_publicacao=pg_date,
                                    )
                        except (httpx.HTTPError, ValueError):
                            detail_parsed = None

                    if detail_parsed is None:
                        try:
                            resp_page = client.get(link)
                            if resp_page.status_code == 200:
                                detail_parsed = parse_pctec_edital_page_html(
                                    resp_page.text,
                                    page_url=link,
                                    default_title=item["titulo"],
                                    default_status=item["status"],
                                )
                        except httpx.HTTPError as exc:
                            logger.warning(f"Erro ao inspecionar página de edital PCTec {link}: {exc}")

                    final_item = detail_parsed or {k: v for k, v in item.items() if k != "is_complete"}
                    if item.get("ano") and not final_item.get("ano"):
                        final_item["ano"] = item["ano"]

                    self._url_to_docs_cache[link] = final_item.get("documentos", [])

                    if year is not None and final_item.get("ano") is not None and final_item["ano"] != year:
                        continue

                    if link not in seen_links:
                        seen_links.add(link)
                        editais.append(final_item)

        except Exception as exc:
            logger.error(f"Erro geral no scraper do PCTec: {exc}")
            return editais

        return editais

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai todos os documentos PDF vinculados a uma página de edital do PCTec."""
        if not edital_url:
            return []

        norm_url = normalize_pctec_url(edital_url)
        if norm_url in self._url_to_docs_cache:
            return self._url_to_docs_cache[norm_url]

        if norm_url.lower().endswith(".pdf"):
            return [{
                "titulo": "Documento Oficial PCTec",
                "link": norm_url,
                "tipo": classify_pctec_document(norm_url, norm_url),
            }]

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                slug = urlparse(norm_url).path.strip("/").split("/")[-1]
                if slug and slug != "chamadas":
                    try:
                        resp_pg = client.get(PCTEC_PAGES_API_URL, params={"slug": slug})
                        if resp_pg.status_code == 200:
                            pg_list = resp_pg.json()
                            if isinstance(pg_list, list) and pg_list:
                                pg_html = (pg_list[0].get("content") or {}).get("rendered") or ""
                                parsed = parse_pctec_edital_page_html(pg_html, page_url=norm_url)
                                docs = parsed.get("documentos", [])
                                self._url_to_docs_cache[norm_url] = docs
                                return docs
                    except (httpx.HTTPError, ValueError):
                        pass

                resp = client.get(norm_url)
                if resp.status_code == 200:
                    parsed = parse_pctec_edital_page_html(resp.text, page_url=str(resp.url))
                    docs = parsed.get("documentos", [])
                    self._url_to_docs_cache[norm_url] = docs
                    return docs
        except Exception as exc:
            logger.warning(f"Erro ao extrair documentos do PCTec em {edital_url}: {exc}")

        return []


pctec_scraper = PCTecScraper()

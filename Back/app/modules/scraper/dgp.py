"""Scraper para o DGP Central (Decanato de Gestão de Pessoas da UnB) e Estágio UnB."""

from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

logger = logging.getLogger(__name__)

DGP_BASE_URL = "https://dgp.unb.br"
ESTAGIO_BASE_URL = "https://estagio.unb.br"
ESTAGIO_PROCESSO_SELETIVO_URL = (
    f"{ESTAGIO_BASE_URL}/index.php?option=com_content&view=category&layout=blog&id=214&Itemid=707"
)
DGP_SEARCH_URL = (
    f"{DGP_BASE_URL}/?searchword=edital&ordering=newest&searchphrase=all&option=com_search"
)

DEFAULT_TIMEOUT = 15.0
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Fique-de-Olho/1.0"

DATE_PAREN_PATTERN = re.compile(r"\((\d{1,2}/\d{1,2}/\d{4})\)")
DATE_GENERAL_PATTERN = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")


def parse_dgp_article_html(html: str, page_url: str, default_tipo: str = "Estágio") -> Dict[str, Any]:
    """Extrai metadados e documentos PDF a partir de uma página de edital do DGP ou Estágio."""
    soup = BeautifulSoup(html, "html.parser")

    # Extração do Título
    h_elem = (
        soup.find(["h1", "h2"], class_=lambda c: c and ("title" in c or "header" in c))
        or soup.find("h2")
        or soup.find("h1")
    )
    titulo = h_elem.get_text(" ", strip=True) if h_elem else ""
    if not titulo and soup.title:
        t_clean = soup.title.string.strip()
        t_clean = t_clean.replace("UnB Estágio -", "").replace("Decanato de Gestão de Pessoas -", "").strip()
        titulo = t_clean

    titulo = re.sub(r"\s+", " ", titulo).strip()

    # Localiza corpo do artigo
    item_page = (
        soup.find("div", class_="item-page")
        or soup.find("div", itemprop="articleBody")
        or soup.find("div", id="content")
        or soup
    )

    documentos: List[Dict[str, Any]] = []
    seen_docs = set()
    data_pub = ""
    has_final = False

    for a in item_page.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)
        if not href or href.startswith("#") or "javascript:" in href:
            continue

        lower_href = href.lower()
        if any(ext in lower_href for ext in [".pdf", "/processo_seletivo/", "/pgd/", "download", "document"]):
            full_link = urljoin(page_url, href)
            if full_link not in seen_docs:
                seen_docs.add(full_link)
                m = DATE_PAREN_PATTERN.search(text) or DATE_GENERAL_PATTERN.search(text)
                doc_date = m.group(1) if m else ""
                if not data_pub and doc_date:
                    data_pub = doc_date

                lower_text = text.lower()
                if any(k in lower_text for k in ["resultado final", "homologação", "homologacao", "convocação final"]):
                    has_final = True

                documentos.append({
                    "titulo": text or "Documento Oficial DGP/Estágio",
                    "link": full_link,
                    "data": doc_date,
                    "tipo": classify_document(text, full_link),
                })

    # Busca data no texto do artigo se ainda não identificada
    if not data_pub:
        text_content = item_page.get_text(" ", strip=True)
        m_txt = DATE_GENERAL_PATTERN.search(text_content)
        if m_txt:
            data_pub = m_txt.group(1)

    # Identificação do ano
    ano: Optional[int] = None
    if data_pub and len(data_pub) >= 10:
        try:
            ano = int(data_pub[-4:])
        except ValueError:
            pass

    if ano is None:
        m_year = re.search(r"\b(20\d{2})\b", titulo)
        if m_year:
            ano = int(m_year.group(1))

    # Identificação de unidade
    unidade = ""
    parts = [p.strip() for p in titulo.split("-")]
    if len(parts) >= 2:
        candidate = parts[-1]
        if any(c.isupper() for c in candidate) and len(candidate) <= 25:
            unidade = candidate
    if not unidade:
        m_uni = re.search(r"-\s*([A-Z0-9/\s]{2,20})(?:\s*$|\s*-)", titulo)
        if m_uni:
            unidade = m_uni.group(1).strip()

    status = "fechado" if has_final else "aberto"

    return {
        "titulo": titulo,
        "tipo_edital": default_tipo,
        "unidade": unidade,
        "link": page_url,
        "data_publicacao": data_pub,
        "status": status,
        "ano": ano,
        "documentos": documentos,
    }


def parse_estagio_category_html(html: str, base_url: str = ESTAGIO_BASE_URL) -> List[Dict[str, str]]:
    """Extrai os links de artigos e editais de processo seletivo do estagio.unb.br."""
    soup = BeautifulSoup(html, "html.parser")
    links: List[Dict[str, str]] = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)
        if not href or "Itemid=101" in href:
            continue

        if "catid=214" in href or "edital-de-abertura" in href or "edital-de-condicoes" in href:
            full_url = urljoin(base_url, href)
            if full_url not in seen and "option=com_content" in full_url and "view=article" in full_url:
                seen.add(full_url)
                links.append({
                    "titulo": text,
                    "link": full_url,
                })

    return links


class DGPScraper(BaseScraper):
    """Implementação do scraper para o DGP Central e Coordenadoria de Estágio da UnB."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout

    @property
    def orgao_origem(self) -> str:
        return "DGP"

    def fetch_editais(
        self,
        year: Optional[int] = None,
        max_pages: Optional[int] = None,
        max_details: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Consulta os editais de estágio remunerado interno e seleções do DGP da UnB.

        Args:
            year: Ano de referência para filtragem (opcional).
            max_pages: Limite de páginas de paginação do estagio.unb.br a consultar.
            max_details: Limite de artigos para inspeção profunda de PDFs.

        Returns:
            Lista de editais padronizados com metadados e documentos anexos.
        """
        editais: List[Dict[str, Any]] = []
        seen_urls = set()

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                article_targets: List[Dict[str, Any]] = []

                # 1. Coleta na Coordenadoria de Estágio do DGP (estagio.unb.br)
                # Consulta as páginas de processos seletivos de estágio da UnB
                page_offsets = [0, 10, 20, 30, 40, 50, 60, 70]
                if max_pages is not None:
                    page_offsets = page_offsets[:max_pages]

                for offset in page_offsets:
                    cat_url = f"{ESTAGIO_PROCESSO_SELETIVO_URL}&limitstart={offset}" if offset > 0 else ESTAGIO_PROCESSO_SELETIVO_URL
                    try:
                        resp = client.get(cat_url)
                        if resp.status_code == 200:
                            items = parse_estagio_category_html(resp.text, base_url=str(resp.url))
                            for it in items:
                                if it["link"] not in seen_urls:
                                    seen_urls.add(it["link"])
                                    it["tipo"] = "Estágio"
                                    article_targets.append(it)
                    except httpx.HTTPError as exc:
                        logger.warning(f"Erro ao consultar estagio.unb.br página com offset {offset}: {exc}")
                        continue

                # 2. Coleta chamadas e editais do DGP Central (dgp.unb.br)
                try:
                    resp_dgp = client.get(DGP_SEARCH_URL)
                    if resp_dgp.status_code == 200:
                        soup_dgp = BeautifulSoup(resp_dgp.text, "html.parser")
                        for dt in soup_dgp.find_all("dt", class_="result-title"):
                            a = dt.find("a", href=True)
                            if a:
                                h = urljoin(str(resp_dgp.url), a["href"])
                                t = a.get_text(" ", strip=True)
                                if h not in seen_urls and ("noticias" in h or "edital" in h.lower()):
                                    seen_urls.add(h)
                                    article_targets.append({
                                        "titulo": t,
                                        "link": h,
                                        "tipo": "Processo Seletivo Interno / PGD",
                                    })
                except httpx.HTTPError as exc:
                    logger.warning(f"Erro ao consultar busca de editais no dgp.unb.br: {exc}")

                # 3. Inspeciona cada artigo para extrair PDFs e datas completas
                targets_to_inspect = article_targets[:max_details] if max_details is not None else article_targets
                for target in targets_to_inspect:
                    link = target["link"]
                    tipo = target.get("tipo", "Estágio")
                    try:
                        resp = client.get(link)
                        if resp.status_code == 200:
                            parsed = parse_dgp_article_html(resp.text, link, default_tipo=tipo)
                            if not parsed["titulo"] and target.get("titulo"):
                                parsed["titulo"] = target["titulo"]

                            if year is not None and parsed.get("ano") is not None and parsed["ano"] != year:
                                continue

                            editais.append(parsed)
                    except httpx.HTTPError as exc:
                        logger.warning(f"Erro ao inspecionar artigo em {link}: {exc}")
                        continue

        except Exception as exc:
            logger.error(f"Erro geral no scraper DGP: {exc}")
            return editais

        return editais

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai todos os documentos e anexos PDF de um edital do DGP ou Estágio."""
        if edital_url.lower().endswith(".pdf") or "download" in edital_url.lower():
            return [{"titulo": "Documento Oficial DGP/Estágio", "link": edital_url, "tipo": classify_document(edital_url, edital_url)}]

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                resp = client.get(edital_url)
                if resp.status_code == 200:
                    parsed = parse_dgp_article_html(resp.text, str(resp.url))
                    return parsed.get("documentos", [])
        except Exception as exc:
            logger.error(f"Erro ao extrair documentos de {edital_url} no DGP: {exc}")

        return []


dgp_scraper = DGPScraper()

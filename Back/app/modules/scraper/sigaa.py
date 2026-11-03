"""Scraper para os processos seletivos públicos do SIGAA UnB (PPGs, Graduação e Extensão)."""

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

logger = logging.getLogger(__name__)

SIGAA_BASE_URL = "https://sigaa.unb.br"
SIGAA_PROCESSOS_URL = "https://sigaa.unb.br/sigaa/public/processo_seletivo/lista.jsf"

SIGAA_NIVEIS_URLS = [
    ("S", "https://sigaa.unb.br/sigaa/public/processo_seletivo/lista.jsf?nivel=S&aba=p-stricto"),
    ("G", "https://sigaa.unb.br/sigaa/public/processo_seletivo/lista.jsf?nivel=G&aba=p-graduacao"),
    ("T", "https://sigaa.unb.br/sigaa/public/processo_seletivo/lista.jsf?nivel=T&aba=p-tecnico"),
    ("L", "https://sigaa.unb.br/sigaa/public/processo_seletivo/lista.jsf?nivel=L&aba=p-lato"),
]

DEFAULT_TIMEOUT = 15.0
USER_AGENT = "Fique-de-Olho/1.0 (MD-UnB Academic Scraper)"

DATE_INTERVAL_PATTERN = re.compile(
    r"(\d{1,2}/\d{1,2}/\d{4})\s*(?:a|até|-)\s*(\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE,
)
DATE_SINGLE_PATTERN = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")


def parse_sigaa_html(html: str, base_url: str = SIGAA_BASE_URL) -> List[Dict[str, Any]]:
    """Extrai os editais e processos seletivos contidos nas tabelas do SIGAA.

    Args:
        html: Código HTML da página do SIGAA.
        base_url: URL base para resolução de links relativos.

    Returns:
        Lista de editais estruturados.
    """
    soup = BeautifulSoup(html, "html.parser")
    editais: List[Dict[str, Any]] = []
    seen = set()

    # Localiza tabelas de listagem padrão do SIGAA (listagem ou formulario)
    tables = soup.find_all("table", class_=lambda c: c and ("listagem" in c or "formulario" in c))
    if not tables:
        tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if not cells or len(cells) < 2:
                continue

            row_text = row.get_text(" ", strip=True)
            if "Nenhum processo seletivo" in row_text or "CPF:" in row_text:
                continue

            # Busca links de editais ou detalhes
            links = row.find_all("a", href=True)
            if not links:
                continue

            target_link = None
            for a in links:
                href = a["href"].strip()
                t = a.get_text(" ", strip=True)
                if any(k in href.lower() or k in t.lower() for k in ["processo", "edital", "detalhe", "verarquivo", "inscricao"]):
                    target_link = a
                    break
            if not target_link:
                target_link = links[0]

            href = target_link["href"].strip()
            full_url = urljoin(base_url, href)
            if full_url in seen:
                continue
            seen.add(full_url)

            titulo = target_link.get_text(" ", strip=True)
            if not titulo or len(titulo) < 3:
                titulo = row_text[:120].strip()

            # Extração de datas
            inicio_inscricao = ""
            fim_inscricao = ""
            data_pub = ""

            interval_match = DATE_INTERVAL_PATTERN.search(row_text)
            if interval_match:
                inicio_inscricao = interval_match.group(1)
                fim_inscricao = interval_match.group(2)
                data_pub = inicio_inscricao
            else:
                single_match = DATE_SINGLE_PATTERN.search(row_text)
                if single_match:
                    data_pub = single_match.group(1)

            # Extração do ano
            ano: Optional[int] = None
            if fim_inscricao and len(fim_inscricao) >= 10:
                ano = int(fim_inscricao[-4:])
            elif data_pub and len(data_pub) >= 10:
                ano = int(data_pub[-4:])

            # Documentos vinculados na própria linha
            documentos: List[Dict[str, Any]] = []
            for a in links:
                h = a["href"].strip()
                t = a.get_text(" ", strip=True) or "Edital/Arquivo SIGAA"
                if any(doc_k in h.lower() for doc_k in [".pdf", "verarquivo", "documento"]):
                    doc_url = urljoin(base_url, h)
                    documentos.append({
                        "titulo": t,
                        "link": doc_url,
                        "tipo": classify_document(t, doc_url),
                    })

            status = "aberto" if ("aberto" in row_text.lower() or "inscreva-se" in row_text.lower()) else "fechado"

            editais.append({
                "titulo": titulo,
                "link": full_url,
                "data_publicacao": data_pub,
                "inicio_inscricao": inicio_inscricao,
                "fim_inscricao": fim_inscricao,
                "status": status,
                "documentos": documentos,
                "ano": ano,
            })

    return editais


class SIGAAScraper(BaseScraper):
    """Implementação do scraper para processos seletivos públicos do SIGAA UnB."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout

    @property
    def orgao_origem(self) -> str:
        return "SIGAA"

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Consulta os processos seletivos públicos disponíveis no SIGAA UnB."""
        editais: List[Dict[str, Any]] = []
        seen_urls = set()

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                for nivel, url in SIGAA_NIVEIS_URLS:
                    try:
                        resp = client.get(url)
                        if resp.status_code != 200:
                            continue
                        parsed = parse_sigaa_html(resp.text, base_url=str(resp.url))
                        for ed in parsed:
                            ed["nivel"] = nivel
                            ed_url = ed.get("link", "")
                            if ed_url and ed_url not in seen_urls:
                                seen_urls.add(ed_url)
                                if year is not None and ed.get("ano") is not None and ed["ano"] != year:
                                    continue
                                editais.append(ed)
                    except httpx.HTTPError as exc:
                        logger.warning(f"Erro ao consultar SIGAA nível {nivel}: {exc}")
                        continue
        except Exception as exc:
            logger.error(f"Erro ao conectar ao SIGAA UnB: {exc}")
            return editais

        return editais

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai os documentos PDF associados a um processo seletivo do SIGAA."""
        if edital_url.lower().endswith(".pdf") or "verarquivo" in edital_url.lower():
            return [{"titulo": "Documento Oficial SIGAA", "link": edital_url, "tipo": classify_document(edital_url, edital_url)}]

        documentos: List[Dict[str, Any]] = []
        seen = set()

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                resp = client.get(edital_url)
                if resp.status_code != 200:
                    return documentos

                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    h = a["href"].strip()
                    if ".pdf" in h.lower() or "verarquivo" in h.lower():
                        full_h = urljoin(str(resp.url), h)
                        if full_h in seen:
                            continue
                        seen.add(full_h)
                        t = a.get_text(" ", strip=True) or "Documento Processo Seletivo SIGAA"
                        documentos.append({
                            "titulo": t,
                            "link": full_h,
                            "tipo": classify_document(t, full_h),
                        })
        except Exception as exc:
            logger.error(f"Erro ao extrair documentos de {edital_url} no SIGAA: {exc}")

        return documentos


sigaa_scraper = SIGAAScraper()

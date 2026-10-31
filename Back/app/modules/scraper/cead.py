"""Scraper para o Centro de Educação a Distância da UnB (CEAD / UAB).

Coleta editais e chamadas de tutoria, professores formadores e seleções
discentes da Universidade Aberta do Brasil utilizando a API REST oficial do Tainacan.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

logger = logging.getLogger(__name__)

CEAD_BASE_URL = "https://cead.unb.br"
CEAD_COLLECTION_ID = 8428
CEAD_API_ITEMS_URL = f"{CEAD_BASE_URL}/wp-json/tainacan/v2/collection/{CEAD_COLLECTION_ID}/items"
CEAD_API_ATTACHMENTS_URL = f"{CEAD_BASE_URL}/wp-json/tainacan/v2/items"
DEFAULT_TIMEOUT = 15.0
USER_AGENT = "Fique-de-Olho/1.0"


def _extract_meta_value(metadata: Dict[str, Any], key: str) -> Optional[str]:
    """Extrai o valor de um campo de metadado do Tainacan."""
    if not isinstance(metadata, dict):
        return None
    field = metadata.get(key)
    if not isinstance(field, dict):
        return None
    val = field.get("value")
    if val is not None:
        if isinstance(val, list):
            # Termos múltiplos / taxonomia
            names = [item.get("name") for item in val if isinstance(item, dict) and item.get("name")]
            if names:
                return " | ".join(names)
        return str(val).strip()
    return field.get("value_as_string")


class CEADScraper(BaseScraper):
    """Implementação do scraper para o Centro de Educação a Distância (CEAD / UAB)."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self._url_to_id_cache: Dict[str, int] = {}

    @property
    def orgao_origem(self) -> str:
        """Identificador institucional do órgão."""
        return "CEAD"

    def fetch_editais(
        self,
        year: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Busca todos os editais do CEAD consumindo a API REST do Tainacan.

        Args:
            year: Ano de referência para filtragem (opcional).
            max_pages: Limite de páginas a consultar (None para todas).

        Returns:
            Lista de dicionários padronizados com metadados do edital.
        """
        editais: List[Dict[str, Any]] = []
        page = 1

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                while True:
                    url = f"{CEAD_API_ITEMS_URL}?perpage=96&order=DESC&orderby=date&paged={page}"
                    try:
                        resp = client.get(url)
                        if resp.status_code != 200:
                            break
                        data = resp.json()
                    except httpx.HTTPError as exc:
                        logger.warning(f"Erro ao consultar página {page} do CEAD: {exc}")
                        break

                    items = data.get("items", [])
                    if not items:
                        break

                    total_pages = int(resp.headers.get("x-wp-totalpages", 1))

                    for item in items:
                        item_id = item.get("id")
                        title = item.get("title") or "Edital CEAD"
                        url_item = item.get("url") or ""
                        if url_item and item_id:
                            self._url_to_id_cache[url_item] = item_id

                        meta = item.get("metadata", {}) or {}

                        # Extração de campos estruturados do CEAD
                        ano_meta = _extract_meta_value(meta, "ano")
                        ano_edital: Optional[int] = None
                        if ano_meta and ano_meta.isdigit():
                            ano_edital = int(ano_meta)

                        # Filtro por ano se solicitado
                        if year is not None and ano_edital is not None and ano_edital != year:
                            continue

                        data_pub = _extract_meta_value(meta, "data-de-publicacao")
                        if not data_pub and item.get("creation_date"):
                            data_pub = str(item.get("creation_date"))[:10]

                        fim_inscricao = _extract_meta_value(meta, "fim-das-inscricoes")
                        status_bruto = _extract_meta_value(meta, "status-do-edital") or ""
                        descricao = _extract_meta_value(meta, "descricao-4") or ""
                        publico_alvo = _extract_meta_value(meta, "publico-alvo-2")
                        curso = _extract_meta_value(meta, "curso")
                        numero = _extract_meta_value(meta, "numero")

                        # Normalização de status
                        status_normalizado = "aberto" if status_bruto.lower() in ["em andamento", "aberto"] else "fechado"

                        edital_dict: Dict[str, Any] = {
                            "titulo": title,
                            "link": url_item,
                            "data_publicacao": data_pub or "",
                            "inicio_inscricao": data_pub or "",
                            "fim_inscricao": fim_inscricao or "",
                            "status": status_normalizado,
                            "status_original": status_bruto,
                            "descricao": descricao,
                            "resumo": descricao,
                            "curso": curso,
                            "publico_alvo": publico_alvo,
                            "numero": numero,
                            "ano": ano_edital,
                            "item_id": item_id,
                        }
                        editais.append(edital_dict)

                    if max_pages is not None and page >= max_pages:
                        break
                    if page >= total_pages:
                        break
                    page += 1

        except Exception as exc:
            logger.error(f"Falha ao conectar à API do CEAD: {exc}")
            return editais

        return editais

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai os documentos e anexos PDF vinculados ao edital do CEAD.

        Args:
            edital_url: URL da página do edital.

        Returns:
            Lista de documentos contendo título, link e classificação.
        """
        documentos: List[Dict[str, Any]] = []

        # 1. Tenta recuperar o ID via cache em memória
        item_id = self._url_to_id_cache.get(edital_url)

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                # 2. Se o ID não estiver no cache, consulta o HTML da página do edital
                if not item_id:
                    try:
                        resp_page = client.get(edital_url)
                        if resp_page.status_code == 200:
                            match = re.search(r"/tainacan-items/\d+/(\d+)/", resp_page.text)
                            if match:
                                item_id = int(match.group(1))
                                self._url_to_id_cache[edital_url] = item_id
                    except httpx.HTTPError:
                        pass

                # 3. Se temos o item_id, consulta o endpoint de anexos do Tainacan
                if item_id:
                    attachments_url = f"{CEAD_API_ATTACHMENTS_URL}/{item_id}/attachments"
                    try:
                        resp_att = client.get(attachments_url)
                        if resp_att.status_code == 200:
                            attachments = resp_att.json()
                            if isinstance(attachments, list):
                                for att in attachments:
                                    pdf_url = att.get("url") or ""
                                    if not pdf_url:
                                        continue
                                    doc_title = att.get("title") or "Documento Anexo"
                                    documentos.append({
                                        "titulo": doc_title,
                                        "link": pdf_url,
                                        "tipo": classify_document(doc_title, pdf_url),
                                    })
                                if documentos:
                                    return documentos
                    except httpx.HTTPError as exc:
                        logger.warning(f"Erro ao buscar anexos na API do CEAD para item {item_id}: {exc}")

                # 4. Fallback: Parse tradicional do HTML para links com .pdf
                try:
                    resp_fallback = client.get(edital_url)
                    if resp_fallback.status_code == 200:
                        soup = BeautifulSoup(resp_fallback.text, "html.parser")
                        for a in soup.find_all("a", href=True):
                            href = a["href"].strip()
                            if ".pdf" in href.lower() or "tainacan-items" in href.lower():
                                full_url = urljoin(CEAD_BASE_URL, href)
                                if any(ign in href.lower() for ign in ["regimento", "cookies"]):
                                    continue
                                doc_title = a.get_text(" ", strip=True) or "Documento Oficial"
                                documentos.append({
                                    "titulo": doc_title,
                                    "link": full_url,
                                    "tipo": classify_document(doc_title, full_url),
                                })
                except httpx.HTTPError:
                    pass

        except Exception as exc:
            logger.error(f"Erro ao extrair documentos do edital {edital_url}: {exc}")

        return documentos


# Instância padrão para o registro central
cead_scraper = CEADScraper()

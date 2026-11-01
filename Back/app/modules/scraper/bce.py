"""Scraper para editais e normativos da Biblioteca Central da UnB (BCE) via API REST do Tainacan."""

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

logger = logging.getLogger(__name__)

BCE_BASE_URL = "https://repositorioadm.unb.br"
BCE_EDITAIS_URL = "https://repositorioadm.unb.br/editais/"
BCE_COLLECTION_ID = 12913
BCE_API_ITEMS_URL = f"https://repositorioadm.unb.br/wp-json/tainacan/v2/collection/{BCE_COLLECTION_ID}/items"
BCE_API_ATTACHMENTS_URL = "https://repositorioadm.unb.br/wp-json/tainacan/v2/items"

DEFAULT_TIMEOUT = 15.0
USER_AGENT = "Fique-de-Olho/1.0"

DATE_PATTERN = re.compile(
    r"\b(\d{1,2}\s+de\s+[A-Za-zÀ-ÿ]+\s+de\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})\b",
    re.IGNORECASE,
)


def _extract_meta_value(metadata: Dict[str, Any], key: str, prefer_iso: bool = False) -> Optional[str]:
    """Extrai valor em texto de um campo de metadados do Tainacan.

    Args:
        metadata: Dicionário de metadados do item Tainacan.
        key: Chave do metadado (ex: 'assunto-8', 'data-de-publicacao').
        prefer_iso: Se True, dá preferência ao campo 'value' (formato YYYY-MM-DD para datas).

    Returns:
        String limpa ou None se ausente/vazio.
    """
    entry = metadata.get(key)
    if not entry or not isinstance(entry, dict):
        return None

    if prefer_iso:
        val = entry.get("value")
        if val and isinstance(val, str) and val.strip():
            return val.strip()

    val_str = entry.get("value_as_string")
    if val_str and isinstance(val_str, str) and val_str.strip():
        return val_str.strip()

    val = entry.get("value")
    if val is not None:
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, (int, float)):
            return str(val)

    return None


def parse_bce_html(html: str, base_url: str = BCE_BASE_URL) -> List[Dict[str, Any]]:
    """Extrai editais via parsing HTML legado (mantido para compatibilidade e fallback)."""
    soup = BeautifulSoup(html, "html.parser")
    editais: List[Dict[str, Any]] = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)

        if not text or len(text) < 4:
            continue

        if any(ign in text.lower() for ign in ["pular para", "governo", "regimento", "cookies", "tutorial", "mapa"]):
            continue

        full_url = urljoin(base_url, href)

        is_edital = any(k in text.lower() for k in ["edital", "chamada", "normativo", "seleção"]) or "edital" in href.lower()
        if not is_edital:
            continue

        if full_url in seen:
            continue
        seen.add(full_url)

        date_match = DATE_PATTERN.search(text)
        data_pub = date_match.group(0) if date_match else ""

        editais.append({
            "titulo": text,
            "link": full_url,
            "data_publicacao": data_pub,
        })

    return editais


class BCEScraper(BaseScraper):
    """Implementação do scraper para a Biblioteca Central (BCE) via API REST do Tainacan."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self._url_to_id_cache: Dict[str, int] = {}
        self._url_to_item_cache: Dict[str, Dict[str, Any]] = {}

    @property
    def orgao_origem(self) -> str:
        return "BCE"

    def fetch_editais(
        self,
        year: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Busca editais da BCE consumindo a API REST oficial do Repositório Administrativo (Tainacan).

        Args:
            year: Ano de referência para filtragem (opcional).
            max_pages: Limite de páginas a consultar (None para todas).

        Returns:
            Lista de dicionários padronizados com metadados estruturados dos editais.
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
                    url = f"{BCE_API_ITEMS_URL}?perpage=96&order=DESC&orderby=date&paged={page}"
                    try:
                        resp = client.get(url)
                        if resp.status_code != 200:
                            break
                        data = resp.json()
                    except (httpx.HTTPError, ValueError) as exc:
                        logger.warning(f"Erro ao consultar página {page} do Tainacan BCE: {exc}")
                        break

                    items = data.get("items", []) if isinstance(data, dict) else []
                    if not items:
                        break

                    total_pages = int(resp.headers.get("x-wp-totalpages", 1))

                    for item in items:
                        item_id = item.get("id")
                        meta = item.get("metadata", {}) or {}

                        title = item.get("title") or _extract_meta_value(meta, "titulo-6") or "Edital BCE"
                        url_item = item.get("url") or ""

                        if url_item and item_id:
                            self._url_to_id_cache[url_item] = item_id
                            self._url_to_item_cache[url_item] = {
                                "id": item_id,
                                "document": item.get("document"),
                                "document_type": item.get("document_type"),
                                "title": title,
                            }

                        data_pub_iso = _extract_meta_value(meta, "data-de-publicacao", prefer_iso=True)
                        data_pub_extenso = _extract_meta_value(meta, "data-de-publicacao", prefer_iso=False)

                        if not data_pub_iso and item.get("creation_date"):
                            data_pub_iso = str(item.get("creation_date"))[:10]

                        # Extração do ano
                        ano_edital: Optional[int] = None
                        if data_pub_iso and len(data_pub_iso) >= 4 and data_pub_iso[:4].isdigit():
                            ano_edital = int(data_pub_iso[:4])

                        # Filtro por ano se solicitado
                        if year is not None and ano_edital is not None and ano_edital != year:
                            continue

                        assunto = _extract_meta_value(meta, "assunto-8") or ""
                        objeto = _extract_meta_value(meta, "descricao-5") or ""
                        unidades_origem = _extract_meta_value(meta, "unidades-de-origem") or "Biblioteca Central (BCE)"
                        tipo_doc = _extract_meta_value(meta, "tipo-7") or "Edital"

                        edital_dict: Dict[str, Any] = {
                            "titulo": title,
                            "link": url_item,
                            "data_publicacao": data_pub_iso or "",
                            "data_publicacao_extenso": data_pub_extenso or "",
                            "assunto": assunto,
                            "objeto": objeto,
                            "descricao": objeto,
                            "resumo": objeto,
                            "unidades_origem": unidades_origem,
                            "tipo_documento": tipo_doc,
                            "ano": ano_edital,
                            "item_id": item_id,
                            "document_type": item.get("document_type"),
                            "document": item.get("document"),
                        }
                        editais.append(edital_dict)

                    if max_pages is not None and page >= max_pages:
                        break
                    if page >= total_pages:
                        break
                    page += 1

        except Exception as exc:
            logger.error(f"Falha ao conectar à API do Tainacan BCE: {exc}")
            return editais

        return editais

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai documentos PDF vinculados a uma chamada da BCE.

        Prioriza o endpoint oficial /attachments da API REST do Tainacan.
        Para itens legados cujo arquivo PDF foi inserido diretamente no campo document,
        recupera a URL direta do PDF. Mantém fallback HTML para URLs externas.

        Args:
            edital_url: URL da página do edital ou link direto do documento.

        Returns:
            Lista de documentos contendo titulo, link e tipo classificado.
        """
        if edital_url.lower().endswith(".pdf"):
            return [{"titulo": "Documento Oficial BCE", "link": edital_url, "tipo": classify_document(edital_url, edital_url)}]

        documentos: List[Dict[str, Any]] = []
        seen_links = set()

        # 1. Recupera identificador do item (via cache ou regex)
        item_id = self._url_to_id_cache.get(edital_url)
        cached_item = self._url_to_item_cache.get(edital_url)

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
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

                # 2. Consulta endpoint oficial de anexos do Tainacan
                if item_id:
                    attachments_url = f"{BCE_API_ATTACHMENTS_URL}/{item_id}/attachments"
                    try:
                        resp_att = client.get(attachments_url)
                        if resp_att.status_code == 200:
                            attachments = resp_att.json()
                            if isinstance(attachments, list):
                                for att in attachments:
                                    pdf_url = att.get("url") or ""
                                    if not pdf_url:
                                        continue
                                    if pdf_url in seen_links:
                                        continue
                                    seen_links.add(pdf_url)
                                    doc_title = att.get("title") or "Documento Anexo BCE"
                                    documentos.append({
                                        "titulo": doc_title,
                                        "link": pdf_url,
                                        "tipo": classify_document(doc_title, pdf_url),
                                    })
                    except (httpx.HTTPError, ValueError) as exc:
                        logger.warning(f"Erro ao buscar anexos na API Tainacan para item {item_id}: {exc}")

                # 3. Fallback de documentos diretos (campo document com URL em itens legados)
                if cached_item:
                    doc_direct = cached_item.get("document")
                    if isinstance(doc_direct, str) and doc_direct.startswith("http") and doc_direct.lower().endswith(".pdf"):
                        if doc_direct not in seen_links:
                            seen_links.add(doc_direct)
                            doc_title = cached_item.get("title") or "Documento Oficial BCE"
                            documentos.append({
                                "titulo": doc_title,
                                "link": doc_direct,
                                "tipo": classify_document(doc_title, doc_direct),
                            })

                if documentos:
                    return documentos

                # 4. Fallback final: Parse tradicional do HTML da página
                try:
                    resp_fallback = client.get(edital_url)
                    if resp_fallback.status_code == 200:
                        soup = BeautifulSoup(resp_fallback.text, "html.parser")
                        for a in soup.find_all("a", href=True):
                            h = a["href"].strip()
                            if ".pdf" in h.lower() or "tainacan-items" in h.lower():
                                full_h = urljoin(str(resp_fallback.url), h)
                                if full_h in seen_links or any(ign in h.lower() for ign in ["regimento", "cookies"]):
                                    continue
                                seen_links.add(full_h)
                                t = a.get_text(" ", strip=True) or "Documento Oficial BCE"
                                documentos.append({
                                    "titulo": t,
                                    "link": full_h,
                                    "tipo": classify_document(t, full_h),
                                })
                except httpx.HTTPError:
                    pass

        except Exception as exc:
            logger.error(f"Erro ao extrair documentos da BCE em {edital_url}: {exc}")

        return documentos


bce_scraper = BCEScraper()

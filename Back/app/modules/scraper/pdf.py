"""Módulo agnóstico de download e extração de PDFs com pdfplumber.

Projetado para processar editais e documentos de múltiplos órgãos e decanatos da UnB
(DEG, DPG, DEX, DPI, DAC, INT, PROIC, DACES, BCE, etc.) a partir de URLs, fluxos de
bytes ou arquivos locais.
"""

from __future__ import annotations

import io
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Union

import httpx
import pdfplumber

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
DEFAULT_USER_AGENT = "Fique-de-Olho/1.0 (+https://github.com/unb-mds/Fique-de-Olho)"


class PDFExtractionError(Exception):
    """Exceção base para erros do módulo de extração de PDF."""


class PDFDownloadError(PDFExtractionError):
    """Lançada quando o download do PDF falha (timeout, erro de rede, HTTP 4xx/5xx)."""


class PDFCorruptedError(PDFExtractionError):
    """Lançada quando os bytes do PDF não representam um documento PDF legível ou válido."""


@dataclass
class PDFPageExtraction:
    """Representa o conteúdo extraído de uma página individual do PDF."""

    index: int
    text: str
    tables: List[List[List[Optional[str]]]] = field(default_factory=list)
    char_count: int = 0

    def __post_init__(self) -> None:
        self.char_count = len(self.text)


@dataclass
class PDFDocumentExtraction:
    """Representa a extração completa e estruturada de um documento PDF."""

    source: str
    num_pages: int
    full_text: str
    pages: List[PDFPageExtraction] = field(default_factory=list)
    tables: List[List[List[Optional[str]]]] = field(default_factory=list)
    has_text_layer: bool = False
    char_count: int = 0

    def __post_init__(self) -> None:
        self.char_count = len(self.full_text)
        self.has_text_layer = bool(self.full_text and self.full_text.strip())


def normalize_extracted_text(text: Optional[str]) -> str:
    """Normaliza o texto extraído removendo espaços redundantes e normalizando quebras."""
    if not text:
        return ""

    # Normalização de compatibilidade Unicode mantendo acentos
    normalized = unicodedata.normalize("NFC", text)
    # Uniformiza quebras de linha Windows e Unix
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    # Remove espaços em branco redundantes mantendo quebras de parágrafo
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.split("\n")]
    # Remove excesso de linhas vazias consecutivas
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return result.strip()


def download_pdf(
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
) -> bytes:
    """Baixa um arquivo PDF a partir de uma URL remota.

    Args:
        url: URL completa para o arquivo PDF.
        timeout: Limite de tempo em segundos para download.
        user_agent: Header User-Agent para identificação da requisição.

    Returns:
        bytes: Conteúdo binário do PDF.

    Raises:
        PDFDownloadError: Caso o download falhe por timeout, erro HTTP ou conexão.
    """
    try:
        response = httpx.get(
            url,
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": user_agent},
        )
        response.raise_for_status()
        return response.content
    except httpx.HTTPStatusError as exc:
        msg = f"Falha HTTP {exc.response.status_code} ao baixar PDF de {url}"
        logger.warning(msg)
        raise PDFDownloadError(msg) from exc
    except httpx.RequestError as exc:
        msg = f"Erro de conexão/timeout ao baixar PDF de {url}: {exc}"
        logger.warning(msg)
        raise PDFDownloadError(msg) from exc
    except Exception as exc:
        msg = f"Erro inesperado ao baixar PDF de {url}: {exc}"
        logger.warning(msg)
        raise PDFDownloadError(msg) from exc


def extract_pdf_from_bytes(
    data: Union[bytes, io.BytesIO],
    source_name: str = "memory",
) -> PDFDocumentExtraction:
    """Extrai texto e tabelas de um PDF a partir de fluxo de bytes em memória.

    Args:
        data: Binário do PDF ou objeto BytesIO.
        source_name: Identificador legível da origem do documento (URL ou path).

    Returns:
        PDFDocumentExtraction: Estrutura completa de texto e tabelas por página.

    Raises:
        PDFCorruptedError: Se os bytes forem inválidos ou corrompidos.
    """
    stream = io.BytesIO(data) if isinstance(data, bytes) else data

    try:
        with pdfplumber.open(stream) as pdf:
            pages_extracted: List[PDFPageExtraction] = []
            all_tables: List[List[List[Optional[str]]]] = []
            full_text_chunks: List[str] = []

            for idx, page in enumerate(pdf.pages, start=1):
                raw_text = page.extract_text() or ""
                cleaned_text = normalize_extracted_text(raw_text)

                # Extrai tabelas com tratamento seguro
                page_tables: List[List[List[Optional[str]]]] = []
                try:
                    raw_tables = page.extract_tables() or []
                    for table in raw_tables:
                        if table:
                            page_tables.append(table)
                            all_tables.append(table)
                except Exception as table_err:
                    logger.debug(f"Aviso ao extrair tabelas da página {idx} de {source_name}: {table_err}")

                pages_extracted.append(
                    PDFPageExtraction(
                        index=idx,
                        text=cleaned_text,
                        tables=page_tables,
                    )
                )

                if cleaned_text:
                    full_text_chunks.append(cleaned_text)

            full_text = "\n\n".join(full_text_chunks)

            return PDFDocumentExtraction(
                source=source_name,
                num_pages=len(pdf.pages),
                full_text=full_text,
                pages=pages_extracted,
                tables=all_tables,
            )

    except (pdfplumber.pdfminer.pdfparser.PDFSyntaxError, Exception) as exc:
        msg = f"Não foi possível abrir o PDF '{source_name}': formato inválido ou corrompido ({exc})"
        logger.warning(msg)
        raise PDFCorruptedError(msg) from exc


def extract_pdf_from_url(
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> PDFDocumentExtraction:
    """Baixa e extrai texto e tabelas de um PDF remoto."""
    content = download_pdf(url, timeout=timeout)
    return extract_pdf_from_bytes(content, source_name=url)


def extract_pdf_from_file(
    file_path: Union[str, Path],
) -> PDFDocumentExtraction:
    """Lê e extrai texto e tabelas de um arquivo PDF local."""
    path = Path(file_path)
    if not path.is_file():
        raise PDFExtractionError(f"Arquivo PDF não encontrado: {file_path}")

    with path.open("rb") as f:
        return extract_pdf_from_bytes(f.read(), source_name=str(path))


def extract_pdf(
    source: Union[str, Path, bytes, io.BytesIO],
    timeout: float = DEFAULT_TIMEOUT,
) -> PDFDocumentExtraction:
    """Ponto de entrada unificado para extração de PDF a partir de qualquer origem.

    Aceita:
    - URL HTTP/HTTPS (faz download e extrai);
    - Caminho local no sistema de arquivos (lê e extrai);
    - Bytes ou io.BytesIO em memória (extrai diretamente).
    """
    if isinstance(source, (bytes, io.BytesIO)):
        return extract_pdf_from_bytes(source, source_name="memory")

    if isinstance(source, (str, Path)):
        source_str = str(source).strip()
        if source_str.lower().startswith(("http://", "https://")):
            return extract_pdf_from_url(source_str, timeout=timeout)
        return extract_pdf_from_file(source_str)

    raise PDFExtractionError(f"Tipo de entrada não suportado para extração: {type(source)}")

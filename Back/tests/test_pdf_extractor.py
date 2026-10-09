"""Testes unitários para o módulo de extração de PDF (pdfplumber)."""

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.modules.scraper.pdf import (
    PDFCorruptedError,
    PDFDocumentExtraction,
    PDFDownloadError,
    PDFExtractionError,
    download_pdf,
    extract_pdf,
    extract_pdf_from_bytes,
    extract_pdf_from_file,
    extract_pdf_from_url,
    normalize_extracted_text,
)

# PDF mínimo válido em bytes com camada de texto
VALID_MINIMAL_PDF = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 58 >> stream
BT /F1 12 Tf 100 700 Td (UNIVERSIDADE DE BRASILIA - EDITAL DEG 2026) Tj ET
endstream endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000373 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
448
%%EOF"""

# PDF válido de 2 páginas
TWO_PAGE_PDF = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R 6 0 R] /Count 2 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 38 >> stream
BT /F1 12 Tf 100 700 Td (Pagina 1 - Cronograma) Tj ET
endstream endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
6 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 7 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
7 0 obj << /Length 36 >> stream
BT /F1 12 Tf 100 700 Td (Pagina 2 - Inscricao) Tj ET
endstream endobj
xref
0 8
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000122 00000 n 
0000000273 00000 n 
0000000360 00000 n 
0000000435 00000 n 
0000000586 00000 n 
trailer << /Size 8 /Root 1 0 R >>
startxref
671
%%EOF"""

# PDF sem texto (apenas folha em branco simulando digitalizado sem OCR)
BLANK_PDF = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer << /Size 4 /Root 1 0 R >>
startxref
192
%%EOF"""


def test_normalize_extracted_text():
    raw = "  Universidade   de   Brasilia \r\n\r\n\r\n\r\n  Edital   01/2026 \t\t  "
    result = normalize_extracted_text(raw)
    assert "Universidade de Brasilia" in result
    assert "Edital 01/2026" in result
    assert "\r" not in result
    assert "\n\n\n" not in result


def test_extract_pdf_from_bytes_success():
    doc = extract_pdf_from_bytes(VALID_MINIMAL_PDF, source_name="edital_deg.pdf")

    assert isinstance(doc, PDFDocumentExtraction)
    assert doc.num_pages == 1
    assert "UNIVERSIDADE DE BRASILIA - EDITAL DEG 2026" in doc.full_text
    assert doc.has_text_layer is True
    assert doc.char_count > 0
    assert len(doc.pages) == 1
    assert doc.pages[0].index == 1
    assert "UNIVERSIDADE DE BRASILIA" in doc.pages[0].text


def test_extract_pdf_multi_page():
    doc = extract_pdf_from_bytes(TWO_PAGE_PDF, source_name="multi_page.pdf")

    assert doc.num_pages == 2
    assert "Pagina 1 - Cronograma" in doc.pages[0].text
    assert "Pagina 2 - Inscricao" in doc.pages[1].text
    assert "Pagina 1" in doc.full_text and "Pagina 2" in doc.full_text


def test_extract_pdf_blank_or_scanned():
    doc = extract_pdf_from_bytes(BLANK_PDF, source_name="blank.pdf")

    assert doc.num_pages == 1
    assert doc.full_text == ""
    assert doc.has_text_layer is False
    assert doc.char_count == 0


def test_extract_pdf_corrupted_bytes():
    corrupted = b"Nao sou um arquivo PDF valido"
    with pytest.raises(PDFCorruptedError) as exc_info:
        extract_pdf_from_bytes(corrupted, source_name="invalid.pdf")
    assert "formato inválido ou corrompido" in str(exc_info.value)


@patch("app.modules.scraper.pdf.httpx.get")
def test_download_pdf_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.content = VALID_MINIMAL_PDF
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    data = download_pdf("https://deg.unb.br/editais/edital_01.pdf")
    assert data == VALID_MINIMAL_PDF
    mock_get.assert_called_once()


@patch("app.modules.scraper.pdf.httpx.get")
def test_download_pdf_http_404_error(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_get.side_effect = httpx.HTTPStatusError("404 Not Found", request=MagicMock(), response=mock_resp)

    with pytest.raises(PDFDownloadError) as exc_info:
        download_pdf("https://deg.unb.br/edital_inexistente.pdf")
    assert "Falha HTTP 404" in str(exc_info.value)


@patch("app.modules.scraper.pdf.httpx.get")
def test_download_pdf_timeout_error(mock_get):
    mock_get.side_effect = httpx.TimeoutException("Timeout")

    with pytest.raises(PDFDownloadError) as exc_info:
        download_pdf("https://deg.unb.br/edital_timeout.pdf")
    assert "Erro de conexão/timeout" in str(exc_info.value)


@patch("app.modules.scraper.pdf.download_pdf")
def test_extract_pdf_from_url_success(mock_download):
    mock_download.return_value = VALID_MINIMAL_PDF

    doc = extract_pdf_from_url("https://dpg.unb.br/editais/mestrado.pdf")
    assert doc.source == "https://dpg.unb.br/editais/mestrado.pdf"
    assert doc.has_text_layer is True
    assert "UNIVERSIDADE DE BRASILIA" in doc.full_text


def test_extract_pdf_from_file_success(tmp_path: Path):
    pdf_file = tmp_path / "edital_local.pdf"
    pdf_file.write_bytes(VALID_MINIMAL_PDF)

    doc = extract_pdf_from_file(pdf_file)
    assert doc.num_pages == 1
    assert "UNIVERSIDADE DE BRASILIA" in doc.full_text


def test_extract_pdf_from_file_not_found():
    with pytest.raises(PDFExtractionError) as exc:
        extract_pdf_from_file("/caminho/inexistente/edital.pdf")
    assert "não encontrado" in str(exc.value)


def test_extract_pdf_unified_entrypoint(tmp_path: Path):
    # Testando com Bytes
    doc_bytes = extract_pdf(VALID_MINIMAL_PDF)
    assert doc_bytes.has_text_layer is True

    # Testando com arquivo local
    local_file = tmp_path / "local.pdf"
    local_file.write_bytes(TWO_PAGE_PDF)
    doc_file = extract_pdf(local_file)
    assert doc_file.num_pages == 2

    # Testando tipo inválido
    with pytest.raises(PDFExtractionError):
        extract_pdf(12345)  # type: ignore

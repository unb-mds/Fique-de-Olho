"""Módulo de Scraper: responsável pela coleta (BeautifulSoup) e extração de PDFs (pdfplumber)."""

from app.modules.scraper.pdf import (
    PDFCorruptedError,
    PDFDocumentExtraction,
    PDFDownloadError,
    PDFExtractionError,
    PDFPageExtraction,
    download_pdf,
    extract_pdf,
    extract_pdf_from_bytes,
    extract_pdf_from_file,
    extract_pdf_from_url,
    normalize_extracted_text,
)
from app.modules.scraper.pipeline import run_pipeline, upsert_edital

__all__ = [
    "run_pipeline",
    "upsert_edital",
    "extract_pdf",
    "extract_pdf_from_bytes",
    "extract_pdf_from_file",
    "extract_pdf_from_url",
    "download_pdf",
    "normalize_extracted_text",
    "PDFExtractionError",
    "PDFDownloadError",
    "PDFCorruptedError",
    "PDFDocumentExtraction",
    "PDFPageExtraction",
]

"""Módulo de Scraper: responsável pela coleta (BeautifulSoup) e extração de PDFs (pdfplumber)."""

from app.modules.scraper.parser import (
    CAMPUS_UNB,
    ORGAOS_UNB,
    CronogramaEtapa,
    EditalMetadados,
    detect_campus,
    detect_orgao_emissor,
    parse_data_interval,
    parse_edital_metadados,
)
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
    "EditalMetadados",
    "CronogramaEtapa",
    "parse_edital_metadados",
    "parse_data_interval",
    "detect_orgao_emissor",
    "detect_campus",
    "ORGAOS_UNB",
    "CAMPUS_UNB",
]

"""Módulo de Scraper: responsável pela coleta (BeautifulSoup) e extração de PDFs (pdfplumber)."""

from app.modules.scraper.pipeline import run_pipeline, upsert_edital

__all__ = ["run_pipeline", "upsert_edital"]

"""Módulo de Scraper: responsável pela coleta (BeautifulSoup) e extração de PDFs (pdfplumber)."""

from typing import Dict, Optional

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.bce import BCEScraper, bce_scraper
from app.modules.scraper.cdt import CDTScraper, cdt_scraper
from app.modules.scraper.cead import CEADScraper, cead_scraper
from app.modules.scraper.cebraspe import CebraspeScraper, cebraspe_scraper
from app.modules.scraper.concursos import ConcursosScraper, concursos_scraper
from app.modules.scraper.dac import DACScraper, dac_scraper
from app.modules.scraper.daces import DACESScraper, daces_scraper
from app.modules.scraper.deg import DEGScraper, deg_scraper
from app.modules.scraper.dex import DEXScraper, dex_scraper
from app.modules.scraper.dgp import DGPScraper, dgp_scraper
from app.modules.scraper.dpg import DPGScraper, dpg_scraper
from app.modules.scraper.dpi import DPIScraper, dpi_scraper
from app.modules.scraper.fal import FALScraper, fal_scraper
from app.modules.scraper.finatec import FinatecScraper, finatec_scraper
from app.modules.scraper.hub import HUBScraper, hub_scraper
from app.modules.scraper.int_scraper import INTScraper, int_scraper
from app.modules.scraper.pctec import PCTecScraper, pctec_scraper
from app.modules.scraper.proic import PROICScraper, proic_scraper
from app.modules.scraper.sigaa import SIGAAScraper, sigaa_scraper
from app.modules.scraper.unb_idiomas import UnBIdiomasScraper, unb_idiomas_scraper
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

# Registro centralizado de scrapers por órgão da UnB
SCRAPERS_REGISTRY: Dict[str, BaseScraper] = {
    "DEG": deg_scraper,
    "DPG": dpg_scraper,
    "INT": int_scraper,
    "DEX": dex_scraper,
    "DPI": dpi_scraper,
    "DAC": dac_scraper,
    "PROIC": proic_scraper,
    "DACES": daces_scraper,
    "BCE": bce_scraper,
    "CEAD": cead_scraper,
    "SIGAA": sigaa_scraper,
    "CEBRASPE": cebraspe_scraper,
    "UNB_IDIOMAS": unb_idiomas_scraper,
    "CONCURSOS": concursos_scraper,
    "DGP": dgp_scraper,
    "FINATEC": finatec_scraper,
    "CDT": cdt_scraper,
    "PCTEC": pctec_scraper,
    "HUB": hub_scraper,
    "FAL": fal_scraper,
}


def get_scraper(orgao: str) -> Optional[BaseScraper]:
    """Retorna a instância do scraper correspondente à sigla do órgão."""
    return SCRAPERS_REGISTRY.get(orgao.upper().strip())


__all__ = [
    "BaseScraper",
    "DEGScraper",
    "deg_scraper",
    "DPGScraper",
    "dpg_scraper",
    "INTScraper",
    "int_scraper",
    "DEXScraper",
    "dex_scraper",
    "DPIScraper",
    "dpi_scraper",
    "DACScraper",
    "dac_scraper",
    "PROICScraper",
    "proic_scraper",
    "DACESScraper",
    "daces_scraper",
    "BCEScraper",
    "bce_scraper",
    "CEADScraper",
    "cead_scraper",
    "SIGAAScraper",
    "sigaa_scraper",
    "CebraspeScraper",
    "cebraspe_scraper",
    "UnBIdiomasScraper",
    "unb_idiomas_scraper",
    "ConcursosScraper",
    "concursos_scraper",
    "DGPScraper",
    "dgp_scraper",
    "FinatecScraper",
    "finatec_scraper",
    "CDTScraper",
    "cdt_scraper",
    "PCTecScraper",
    "pctec_scraper",
    "HUBScraper",
    "hub_scraper",
    "FALScraper",
    "fal_scraper",
    "SCRAPERS_REGISTRY",
    "get_scraper",
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
]

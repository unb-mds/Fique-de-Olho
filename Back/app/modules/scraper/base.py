"""Interface base abstrata para scrapers de editais da UnB.

Padroniza a coleta de dados para múltiplos órgãos e decanatos da Universidade de Brasília:
DEG, DPG, DEX, DPI, DAC, INT, PROIC, DACES, BCE, etc.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.modules.scraper.pdf import download_pdf


class BaseScraper(ABC):
    """Classe base abstrata para padronização de scrapers de portais de editais da UnB."""

    @property
    @abstractmethod
    def orgao_origem(self) -> str:
        """Identificador do órgão/decanato de origem (ex: 'DEG', 'DPG', 'DEX', 'DAC', etc.)."""
        raise NotImplementedError

    @abstractmethod
    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Busca e extrai a listagem de editais do portal correspondente ao órgão.

        Args:
            year: Ano de referência para filtragem da listagem (ex: 2026, 2025).
                  Se None, busca a página mais recente do portal.

        Returns:
            List[Dict[str, Any]]: Lista de dicionários contendo ao menos:
                - 'titulo': str
                - 'link': str (URL da página do edital)
                - 'data_publicacao': str ou datetime
        """
        raise NotImplementedError

    @abstractmethod
    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai os links e metadados de arquivos anexos/PDFs de um edital específico.

        Args:
            edital_url: URL da página do edital no portal do órgão.

        Returns:
            List[Dict[str, Any]]: Lista de documentos encontrados contendo:
                - 'titulo': str
                - 'link': str (URL do arquivo PDF)
                - 'tipo': str ('original', 'resultado_final', 'retificacao', etc.)
        """
        raise NotImplementedError

    def download_documento(self, url: str, timeout: float = 15.0) -> bytes:
        """Utilitário compartilhado para download do binário de um documento via stream."""
        return download_pdf(url, timeout=timeout)

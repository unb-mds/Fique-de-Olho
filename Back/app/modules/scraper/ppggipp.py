import html as html_lib
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

logger = logging.getLogger(__name__)


class PPGGIPPScraper(BaseScraper):
    """
    Scraper para o portal do Programa de Pós-Graduação em Governança e Inovação em
    Políticas Públicas (PPGGIPP / PPGIPP - FACE/UnB).
    URL base: https://ppggipp.unb.br/

    Estratégia:
    1. Raspagem estruturada da página oficial de editais (`/editais-ppggipp`),
       organizando chamadas públicas e editais por ano (2022–2026+) e agrupando
       editais de abertura, anexos, retificações, homologações, convocações e
       resultados preliminares/finais.
    2. Varredura complementar da seção de informes (`/informes-ppggipp-2`) para
       capturar novos avisos de editais ou chamadas públicas recém-publicados.
    """

    BASE_URL = "https://ppggipp.unb.br"
    EDITAIS_PAGE_URL = "https://ppggipp.unb.br/editais-ppggipp"
    INFORMES_PAGE_URL = "https://ppggipp.unb.br/informes-ppggipp-2"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    EXCLUDED_PDF_PATTERNS = (
        "mprazer.pdf",
        "estatuto_e_regimento",
        "regimento_geral",
        "telefones unb",
    )

    def __init__(self, timeout: float = 20.0, cache_ttl: float = 300.0):
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        self._docs_by_page: Dict[str, List[Dict[str, str]]] = {}

    @property
    def orgao_origem(self) -> str:
        return "PPGGIPP"

    def clear_cache(self) -> None:
        """Limpa o cache em memória do scraper."""
        self._cache.clear()
        self._docs_by_page.clear()

    def _get_cached(self, key: str) -> Optional[List[Dict[str, Any]]]:
        entry = self._cache.get(key)
        if not entry:
            return None
        ts, data = entry
        if (time.monotonic() - ts) > self.cache_ttl:
            del self._cache[key]
            return None
        return [dict(item) for item in data]

    def _set_cached(self, key: str, data: List[Dict[str, Any]]) -> None:
        self._cache[key] = (time.monotonic(), [dict(item) for item in data])

    @staticmethod
    def _clean_text(text: str) -> str:
        if not text:
            return ""
        unescaped = html_lib.unescape(text)
        cleaned = BeautifulSoup(unescaped, "html.parser").get_text(" ", strip=True)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return re.sub(r"^[-–—•\s]+", "", cleaned).strip()

    @staticmethod
    def _is_pdf_url(href: str) -> bool:
        if not href:
            return False
        parsed = urlparse(href.strip())
        path = (parsed.path or "").lower()
        return path.endswith(".pdf") or ".pdf" in path

    @classmethod
    def _is_excluded_pdf(cls, label: str, url: str) -> bool:
        combined = f"{label} {url}".lower()
        return any(pat in combined for pat in cls.EXCLUDED_PDF_PATTERNS)

    @staticmethod
    def _is_opening_edital_label(label: str) -> bool:
        """
        Identifica se o texto do link corresponde ao documento de abertura de um
        Edital ou Chamada Pública (e não a uma retificação, resultado ou etapa).
        """
        norm = (label or "").strip().lower()
        if any(
            norm.startswith(prefix)
            for prefix in (
                "retificação",
                "retificacao",
                "prorrogação",
                "prorrogacao",
                "resultado",
                "homologação",
                "homologacao",
                "convocação",
                "convocacao",
                "cronograma",
                "anexo",
                "errata",
                "comissão",
                "comissao",
            )
        ):
            return False
        return bool(
            re.match(r"^(?:edital\s+n[º°o\.]?|chamada\s+p[úu]blica)", norm, re.IGNORECASE)
        )

    @staticmethod
    def _is_explicit_chamada_header(text: str) -> bool:
        norm = (text or "").strip()
        return bool(
            re.match(
                r"^(?:CHAMADA\s+P[ÚU]BLICA|EDITAL\s+(?:PPG|N[º°O\.]))",
                norm,
                re.IGNORECASE,
            )
        )

    @staticmethod
    def _make_doc(url_pdf: str, label: str = "") -> Dict[str, str]:
        filename = urlparse(url_pdf).path.rsplit("/", 1)[-1]
        classification_hint = f"{label} {filename}".strip()
        hint_lower = classification_hint.lower()
        if any(k in hint_lower for k in ("preliminar", "provis", "homologacao", "homologação", "1ª etapa", "2ª etapa", "3ª etapa")):
            if "definitivo" not in hint_lower and "final" not in hint_lower and "pós-recurso" not in hint_lower and "pos-recurso" not in hint_lower:
                classification_hint = f"{classification_hint} provisório"
        if any(k in hint_lower for k in ("definitivo", "final", "convocação", "convocacao")):
            if "retificação" not in hint_lower and "retificacao" not in hint_lower:
                classification_hint = f"{classification_hint} resultado final"
        if any(k in hint_lower for k in ("prorrogação", "prorrogacao", "errata", "adendo")):
            classification_hint = f"{classification_hint} retificação"

        tipo_doc = classify_document(classification_hint, url_pdf)
        return {
            "titulo": label or filename or "Documento PDF",
            "link": url_pdf,
            "url_pdf": url_pdf,
            "tipo": tipo_doc,
            "tipo_documento": tipo_doc,
        }

    @staticmethod
    def _infer_categoria(title: str, text: str = "") -> str:
        norm = f"{title} {text}".lower()
        if "bolsista" in norm or "bolsa" in norm:
            return "bolsa"
        if "pesquisa" in norm or "ted" in norm or "procap" in norm:
            return "pos-graduacao"
        return "pos-graduacao"

    @staticmethod
    def _infer_status(year_val: Optional[int], doc_types: List[str]) -> str:
        if "resultado_final" in doc_types:
            return "fechado"
        if year_val is not None and year_val < 2026:
            return "fechado"
        return "aberto"

    def _build_edital_dict(
        self,
        title: str,
        year_val: Optional[int],
        docs: List[Dict[str, str]],
        extra_summary: str = "",
        page_url: str = "",
    ) -> Dict[str, Any]:
        target_page = page_url or self.EDITAIS_PAGE_URL
        url_pdf = docs[0]["url_pdf"] if docs else None
        for d in docs:
            if d["tipo_documento"] == "original":
                url_pdf = d["url_pdf"]
                break

        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50] or "edital"
        identificador = f"PPGGIPP-{year_val or 'GERAL'}-{slug}"
        anchor_url = f"{target_page}#{slug}"
        self._docs_by_page[anchor_url] = docs
        self._docs_by_page[target_page] = self._docs_by_page.get(target_page, []) + docs

        doc_types = [d["tipo_documento"] for d in docs]
        categoria = self._infer_categoria(title, extra_summary)
        data_pub = f"{year_val:04d}-01-01" if year_val else None

        resumo_parts = [title]
        if extra_summary and extra_summary.lower() != title.lower():
            resumo_parts.append(extra_summary)
        resumo = " — ".join(resumo_parts)

        return {
            "identificador_origem": identificador,
            "titulo": title,
            "resumo": resumo[:500],
            "descricao": resumo[:500],
            "texto_completo": " | ".join([resumo] + [d["titulo"] for d in docs])[:2500],
            "link": target_page,
            "url_pagina": target_page,
            "url_pdf": url_pdf,
            "orgao_origem": self.orgao_origem,
            "orgao_emissor": self.orgao_origem,
            "campus": "Darcy Ribeiro",
            "tipo": categoria,
            "categoria": categoria,
            "assunto": categoria,
            "ano": year_val,
            "data_publicacao": data_pub,
            "inicio_inscricao": None,
            "fim_inscricao": None,
            "status": self._infer_status(year_val, doc_types),
            "documentos": docs,
        }

    def _parse_editais_page(self, html_text: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html_text, "html.parser")
        for tag in soup.select("header, footer, nav, script, style"):
            tag.decompose()

        container = soup.select_one(".item-page, article, main") or soup
        blocks = container.find_all(["p", "h2", "h3", "h4", "li"])

        current_year: Optional[int] = None
        explicit_group: Optional[Dict[str, Any]] = None
        year_groups: List[Dict[str, Any]] = []
        pending_docs: List[Dict[str, str]] = []
        results: List[Dict[str, Any]] = []

        def flush_year_section() -> None:
            nonlocal explicit_group, year_groups, pending_docs
            if explicit_group and explicit_group.get("docs"):
                year_groups.append(explicit_group)
            explicit_group = None

            if pending_docs:
                if year_groups:
                    year_groups[-1]["docs"].extend(pending_docs)
                else:
                    year_groups.append(
                        {
                            "title": pending_docs[0]["titulo"],
                            "year": current_year,
                            "docs": list(pending_docs),
                            "summary": "",
                        }
                    )
                pending_docs = []

            for grp in year_groups:
                if grp.get("docs"):
                    results.append(
                        self._build_edital_dict(
                            title=grp["title"],
                            year_val=grp["year"],
                            docs=grp["docs"],
                            extra_summary=grp.get("summary", ""),
                            page_url=self.EDITAIS_PAGE_URL,
                        )
                    )
            year_groups = []

        for blk in blocks:
            txt = self._clean_text(blk.get_text(" ", strip=True))
            if not txt:
                continue

            # Detecta cabeçalho de ano (ex.: "2026", "2025", "2024", "2023", "2022")
            if re.match(r"^20\d{2}$", txt):
                flush_year_section()
                current_year = int(txt)
                continue

            # Extrai links PDF presentes no bloco
            pdf_links: List[Tuple[str, str]] = []
            for a_tag in blk.find_all("a", href=True):
                href = (a_tag.get("href") or "").strip()
                if not self._is_pdf_url(href):
                    continue
                full_url = urljoin(self.EDITAIS_PAGE_URL, href)
                label = self._clean_text(a_tag.get_text(" ", strip=True)) or txt
                if self._is_excluded_pdf(label, full_url):
                    continue
                pdf_links.append((label, full_url))

            # Bloco de texto sem PDF que abre uma Chamada Pública explícita (ex.: 2026)
            if not pdf_links:
                if self._is_explicit_chamada_header(txt):
                    if explicit_group and explicit_group.get("docs"):
                        year_groups.append(explicit_group)
                    explicit_group = {
                        "title": txt,
                        "year": current_year,
                        "docs": [],
                        "summary": "",
                    }
                continue

            # Processa links PDF do bloco
            for label, full_url in pdf_links:
                doc_entry = self._make_doc(full_url, label)

                if explicit_group is not None:
                    if not explicit_group["docs"]:
                        doc_entry["tipo_documento"] = "original"
                        if not explicit_group["summary"]:
                            explicit_group["summary"] = label
                    explicit_group["docs"].append(doc_entry)
                    continue

                if self._is_opening_edital_label(label):
                    doc_entry["tipo_documento"] = "original"
                    # Se havia documentos de acompanhamento acumulados antes (ordem cronológica reversa),
                    # eles pertencem a este edital de abertura
                    combined_docs = [doc_entry] + pending_docs
                    pending_docs = []
                    year_groups.append(
                        {
                            "title": label,
                            "year": current_year,
                            "docs": combined_docs,
                            "summary": "",
                        }
                    )
                else:
                    pending_docs.append(doc_entry)

        flush_year_section()
        return results

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retorna os editais e chamadas públicas do PPGGIPP/FACE/UnB.
        """
        cache_key = f"editais:{year if year is not None else 'all'}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        collected: List[Dict[str, Any]] = []
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.DEFAULT_HEADERS) as client:
                response = client.get(self.EDITAIS_PAGE_URL)
                response.raise_for_status()
                collected.extend(self._parse_editais_page(response.text))
        except Exception as exc:
            logger.warning("Falha ao raspar editais do PPGGIPP (%s): %s", self.EDITAIS_PAGE_URL, exc)

        if year is not None:
            filtered: List[Dict[str, Any]] = []
            for ed in collected:
                ed_year = ed.get("ano")
                pub = str(ed.get("data_publicacao") or "")
                if ed_year == year or pub.startswith(str(year)) or str(year) in ed.get("titulo", ""):
                    filtered.append(ed)
            collected = filtered

        self._set_cached(cache_key, collected)
        return [dict(item) for item in collected]

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """
        Retorna os documentos PDF associados a uma página de edital ou link direto.
        """
        if not edital_url:
            return []

        if self._is_pdf_url(edital_url):
            return [self._make_doc(edital_url)]

        if edital_url in self._docs_by_page:
            return [dict(d) for d in self._docs_by_page[edital_url]]

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.DEFAULT_HEADERS) as client:
                response = client.get(edital_url)
                response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup.select("header, footer, nav, script, style"):
                tag.decompose()
            docs: List[Dict[str, str]] = []
            seen_urls: Set[str] = set()
            for a_tag in soup.find_all("a", href=True):
                href = (a_tag.get("href") or "").strip()
                if not self._is_pdf_url(href):
                    continue
                full_url = urljoin(edital_url, href)
                if full_url in seen_urls:
                    continue
                label = self._clean_text(a_tag.get_text(" ", strip=True))
                if self._is_excluded_pdf(label, full_url):
                    continue
                seen_urls.add(full_url)
                docs.append(self._make_doc(full_url, label))
            self._docs_by_page[edital_url] = docs
            return [dict(d) for d in docs]
        except Exception as exc:
            logger.warning("Erro ao extrair documentos de %s no PPGGIPP: %s", edital_url, exc)
            return []

    def download_documento(self, url: str, timeout: float = 15.0) -> bytes:
        """Baixa os bytes de um documento público do PPGGIPP."""
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=self.DEFAULT_HEADERS) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content


ppggipp_scraper = PPGGIPPScraper()

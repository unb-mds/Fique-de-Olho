import html as html_lib
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

logger = logging.getLogger(__name__)


class DAFScraper(BaseScraper):
    """
    Scraper para o Decanato de Administração e Finanças (DAF/UnB) e
    área pública do SIPAC/SIG (`https://daf.unb.br/` e `https://sig.unb.br/public/`).

    Estratégia combinada:
    1. Portal público DAF (`https://daf.unb.br/editais-daf` para Editais Internos e Seleções DAF
       e `https://daf.unb.br/editais` para Pregões Eletrônicos, Licitações e Compras Públicas),
       agrupando edital de abertura, anexos, publicações no DOU, retificações e resultados.
    2. Consulta pública sem autenticação ao portal público do SIPAC (`https://sig.unb.br/public/`):
       - `listaEditais.do?tipo=1&aba=p-comunicados` (Editais de Licitação em Andamento)
       - `listaEditais.do?tipo=2&aba=p-editais-atas&buscaTodas=true&acao=544` (Atas de Registro de Preços Vigentes)
       Se qualquer endpoint do SIPAC exigir autenticação/SSO (`autenticacao.unb.br` / CAS),
       retornar `401`/`403` ou falhar, o erro é isolado com log informativo sem tentar bypass.
    """

    BASE_URL = "https://daf.unb.br"
    EDITAIS_DAF_URL = "https://daf.unb.br/editais-daf"
    PREGOES_URL = "https://daf.unb.br/editais"

    SIG_PUBLIC_BASE_URL = "https://sig.unb.br/public/"
    SIG_EDITAIS_ANDAMENTO_URL = "https://sig.unb.br/public/listaEditais.do?tipo=1&aba=p-comunicados"
    SIG_ATAS_VIGENTES_URL = (
        "https://sig.unb.br/public/listaEditais.do?tipo=2&aba=p-editais-atas&buscaTodas=true&acao=544"
    )

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    def __init__(self, timeout: float = 20.0, cache_ttl: float = 300.0):
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        self._docs_by_page: Dict[str, List[Dict[str, str]]] = {}

    @property
    def orgao_origem(self) -> str:
        return "DAF"

    def clear_cache(self) -> None:
        """Limpa o cache em memória do scraper."""
        self._cache.clear()
        self._docs_by_page.clear()

    def _get_client(self, timeout: Optional[float] = None, follow_redirects: bool = True) -> httpx.Client:
        return httpx.Client(
            timeout=timeout or self.timeout,
            follow_redirects=follow_redirects,
            verify=False,
            headers=self.DEFAULT_HEADERS,
        )

    @staticmethod
    def _clean_text(text: str) -> str:
        if not text:
            return ""
        unescaped = html_lib.unescape(text)
        return re.sub(r"\s+", " ", unescaped).strip()

    @classmethod
    def _normalize_daf_url(cls, href: str, base_url: str = BASE_URL) -> str:
        if not href:
            return ""
        href = href.strip()
        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            return ""
        # Corrige links malformados do tipo "https://images//licitacoes2023/..." presentes no HTML do DAF
        if href.startswith(("https://images/", "http://images/")):
            cleaned_path = re.sub(r"^https?://images/+", "/images/", href)
            return f"{cls.BASE_URL}{cleaned_path}"
        full = urljoin(base_url, href)
        if full.startswith("http://daf.unb.br"):
            full = "https://" + full[len("http://") :]
        return full

    @classmethod
    def _is_document_url(cls, url: str) -> bool:
        if not url:
            return False
        low = url.lower().split("?")[0]
        if low.endswith((".pdf", ".doc", ".docx", ".zip", ".xls", ".xlsx")):
            return True
        if "veredital.do" in url.lower() or "idarquivo=" in url.lower() or "visualizaata.do" in url.lower():
            return True
        return False

    @classmethod
    def _is_direct_pdf(cls, url: str) -> bool:
        if not url:
            return False
        low = url.lower().split("?")[0]
        return low.endswith(".pdf") or "veredital.do" in url.lower()

    @classmethod
    def _extract_year(cls, *texts: Optional[str]) -> Optional[int]:
        for text in texts:
            if not text:
                continue
            m_ed = re.search(r"\b\d{1,5}\s*[/\-._]\s*(20\d{2})\b", text)
            if m_ed:
                return int(m_ed.group(1))
            m_lic = re.search(r"licitacoes(20\d{2})", text.lower())
            if m_lic:
                return int(m_lic.group(1))
            years = [int(m) for m in re.findall(r"\b(20\d{2})\b", text) if 2018 <= int(m) <= 2030]
            if years:
                return max(years)
        return None

    @classmethod
    def _make_doc(cls, title: str, url: str) -> Dict[str, str]:
        clean_title = cls._clean_text(title) or "Documento DAF"
        classify_hint = re.sub(r"preliminar", "provisório", clean_title, flags=re.IGNORECASE)
        doc_type = classify_document(classify_hint, url)
        return {
            "titulo": clean_title,
            "link": url,
            "url_pdf": url,
            "tipo": doc_type,
            "tipo_documento": doc_type,
        }

    def _build_edital_dict(
        self,
        *,
        identificador_origem: str,
        titulo: str,
        url_pagina: str,
        data_publicacao: str,
        ano: Optional[int],
        tipo: str,
        resumo: str = "",
        documentos: Optional[List[Dict[str, str]]] = None,
        status: Optional[str] = None,
        inicio_inscricao: Optional[str] = None,
        fim_inscricao: Optional[str] = None,
    ) -> Dict[str, Any]:
        docs = documentos or []
        direct_pdf = next(
            (d["url_pdf"] for d in docs if self._is_direct_pdf(d.get("url_pdf", ""))),
            docs[0]["url_pdf"] if docs else (url_pagina if self._is_direct_pdf(url_pagina) else None),
        )
        if not status:
            if any(d.get("tipo_documento") == "resultado_final" for d in docs) or "homologado" in resumo.lower():
                status = "fechado"
            else:
                status = "aberto"

        clean_resumo = self._clean_text(resumo) or titulo
        if docs:
            self._docs_by_page[url_pagina] = docs

        return {
            "identificador_origem": identificador_origem,
            "titulo": self._clean_text(titulo),
            "link": url_pagina,
            "url_pagina": url_pagina,
            "url_pdf": direct_pdf,
            "orgao_origem": self.orgao_origem,
            "orgao_emissor": self.orgao_origem,
            "campus": "Darcy Ribeiro",
            "tipo": tipo,
            "categoria": tipo,
            "assunto": tipo,
            "resumo": clean_resumo[:800],
            "descricao": clean_resumo[:800],
            "status": status,
            "data_publicacao": data_publicacao,
            "inicio_inscricao": inicio_inscricao,
            "fim_inscricao": fim_inscricao,
            "ano": ano,
            "documentos": docs,
        }

    def _parse_editais_daf_html(self, html: str, page_url: str = EDITAIS_DAF_URL) -> List[Dict[str, Any]]:
        """
        Analisa `https://daf.unb.br/editais-daf` (Editais Internos DAF), agrupando
        cada edital de abertura com suas convocações, anexos, retificações e resultados.
        """
        soup = BeautifulSoup(html, "html.parser")
        content = soup.select_one("div.item-page, main, article, #content") or soup
        groups: List[Dict[str, Any]] = []
        current_group: Optional[Dict[str, Any]] = None

        for a_tag in content.find_all("a", href=True):
            href = self._normalize_daf_url(a_tag.get("href", ""), base_url=page_url)
            if not self._is_document_url(href):
                continue

            text = self._clean_text(a_tag.get_text(" ", strip=True))
            if not text:
                continue

            low = text.lower()
            is_followup = (
                any(
                    kw in low
                    for kw in (
                        "resultado",
                        "retificação",
                        "retificacao",
                        "convocação",
                        "convocacao",
                        "anexo",
                        "errata",
                        "homologação",
                        "homologacao",
                    )
                )
                and not re.match(r"^edital\s+daf\s+n[.º°o]?\s*\d+", low)
            ) or any(
                kw in low
                for kw in ("resultado preliminar", "resultado provisório", "resultado final", "convocação para")
            )

            doc = self._make_doc(text, href)

            if is_followup and current_group is not None:
                if not any(d["url_pdf"] == href for d in current_group["docs"]):
                    current_group["docs"].append(doc)
                continue

            current_group = {
                "title": text,
                "primary_href": href,
                "docs": [doc],
            }
            groups.append(current_group)

        results: List[Dict[str, Any]] = []
        for idx, grp in enumerate(groups, start=1):
            title = grp["title"]
            docs = grp["docs"]
            ano = self._extract_year(title, grp["primary_href"])
            pub_date = f"{ano}-01-01" if ano else datetime.now().strftime("%Y-%m-%d")
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50] or str(idx)
            canonical_url = f"{page_url.rstrip('/')}#{slug}"

            results.append(
                self._build_edital_dict(
                    identificador_origem=f"daf-interno-{slug}",
                    titulo=title,
                    url_pagina=canonical_url,
                    data_publicacao=pub_date,
                    ano=ano,
                    tipo="Edital Interno DAF",
                    resumo=f"{title} ({len(docs)} documento(s) vinculado(s))",
                    documentos=docs,
                )
            )

        return results

    def _parse_pregoes_daf_html(self, html: str, page_url: str = PREGOES_URL) -> List[Dict[str, Any]]:
        """
        Analisa `https://daf.unb.br/editais` (Pregões Eletrônicos e Licitações DAF),
        agrupando cada Pregão Eletrônico com sua publicação no DOU e anexos.
        """
        soup = BeautifulSoup(html, "html.parser")
        content = soup.select_one("div.item-page, main, article, #content") or soup
        groups: List[Dict[str, Any]] = []
        current_group: Optional[Dict[str, Any]] = None

        for a_tag in content.find_all("a", href=True):
            href = self._normalize_daf_url(a_tag.get("href", ""), base_url=page_url)
            if not self._is_document_url(href):
                continue

            text = self._clean_text(a_tag.get_text(" ", strip=True))
            if not text:
                continue

            low = text.lower()
            is_opening = low.startswith(("pregão", "pregao", "edital")) and "publicação dou" not in low and "anexo" not in low

            doc = self._make_doc(text, href)
            if not is_opening and current_group is not None:
                if not any(d["url_pdf"] == href for d in current_group["docs"]):
                    current_group["docs"].append(doc)
                continue

            # Tenta obter a descrição do pregão no texto do elemento pai/irmão
            parent_text = self._clean_text(a_tag.parent.get_text(" ", strip=True)) if a_tag.parent else text
            current_group = {
                "title": text,
                "primary_href": href,
                "context": parent_text,
                "docs": [doc],
            }
            groups.append(current_group)

        results: List[Dict[str, Any]] = []
        for idx, grp in enumerate(groups, start=1):
            title = grp["title"]
            docs = grp["docs"]
            ano = self._extract_year(title, grp["primary_href"], grp["context"])
            pub_date = f"{ano}-01-01" if ano else datetime.now().strftime("%Y-%m-%d")
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50] or str(idx)
            canonical_url = f"{page_url.rstrip('/')}#{slug}"

            results.append(
                self._build_edital_dict(
                    identificador_origem=f"daf-pregao-{slug}",
                    titulo=title,
                    url_pagina=canonical_url,
                    data_publicacao=pub_date,
                    ano=ano,
                    tipo="Licitação / Pregão Eletrônico",
                    resumo=grp["context"] or title,
                    documentos=docs,
                )
            )

        return results

    def _parse_sig_public_table_html(self, html: str, source_url: str, default_tipo: str) -> List[Dict[str, Any]]:
        """
        Analisa as tabelas públicas de licitações e atas de registro de preços do SIPAC/SIG
        (`https://sig.unb.br/public/listaEditais.do`).
        """
        soup = BeautifulSoup(html, "html.parser")
        results: List[Dict[str, Any]] = []

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue

            for tr in rows[1:]:
                cols = [self._clean_text(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
                if not cols or len(cols) < 4:
                    continue
                if "não há editais" in cols[0].lower() or cols[0].lower() == "licitação":
                    continue

                licitacao_code = cols[0]  # Ex.: "PR 90011/2026" ou "PE 90005/2026"
                valor_est = cols[1] if len(cols) > 1 else ""
                valor_lic = cols[2] if len(cols) > 2 else ""
                status_raw = cols[3] if len(cols) > 3 else ""
                vigencia = cols[5] if len(cols) > 5 else ""
                descricao = cols[6] if len(cols) > 6 else ""

                # Extrai links da linha (visualização da ata e download de edital)
                docs: List[Dict[str, str]] = []
                row_page_url = source_url
                for a_tag in tr.find_all("a", href=True):
                    href = urljoin(self.SIG_PUBLIC_BASE_URL, a_tag["href"].strip())
                    if "autenticacao.unb.br" in href.lower():
                        continue
                    if "veredital.do" in href.lower() or "idarquivo=" in href.lower():
                        doc_label = f"Edital / Arquivo ({licitacao_code})"
                        if not any(d["url_pdf"] == href for d in docs):
                            docs.append(self._make_doc(doc_label, href))
                        if "view=visualiza" in href:
                            row_page_url = href
                    elif "visualizaata.do" in href.lower():
                        doc_label = f"Ata de Registro de Preços ({licitacao_code})"
                        if not any(d["url_pdf"] == href for d in docs):
                            docs.append(self._make_doc(doc_label, href))
                        if row_page_url == source_url:
                            row_page_url = href

                ano = self._extract_year(licitacao_code, vigencia)
                pub_date = None
                m_vig = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", vigencia)
                if m_vig:
                    pub_date = m_vig.group(1)
                elif ano:
                    pub_date = f"{ano}-01-01"
                else:
                    pub_date = datetime.now().strftime("%Y-%m-%d")

                inicio_vig: Optional[str] = None
                fim_vig: Optional[str] = None
                vig_dates = re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", vigencia)
                if len(vig_dates) >= 2:
                    inicio_vig, fim_vig = vig_dates[0], vig_dates[1]

                titulo = f"{licitacao_code} - {descricao}".strip(" -") if descricao else licitacao_code
                resumo_parts = [f"Licitação: {licitacao_code}"]
                if descricao:
                    resumo_parts.append(f"Objeto: {descricao}")
                if status_raw:
                    resumo_parts.append(f"Situação: {status_raw}")
                if valor_lic and valor_lic != "-":
                    resumo_parts.append(f"Valor Licitado: {valor_lic}")
                elif valor_est and valor_est != "-":
                    resumo_parts.append(f"Valor Estimado: {valor_est}")

                slug = re.sub(r"[^a-z0-9]+", "-", licitacao_code.lower()).strip("-")
                status_norm = "fechado" if "homologado" in status_raw.lower() or "encerrad" in status_raw.lower() else "aberto"

                results.append(
                    self._build_edital_dict(
                        identificador_origem=f"sipac-public-{slug}",
                        titulo=titulo,
                        url_pagina=row_page_url,
                        data_publicacao=pub_date,
                        ano=ano,
                        tipo=default_tipo,
                        resumo=" | ".join(resumo_parts),
                        documentos=docs,
                        status=status_norm,
                        inicio_inscricao=inicio_vig,
                        fim_inscricao=fim_vig,
                    )
                )

        return results

    def _fetch_from_sig_public(self) -> List[Dict[str, Any]]:
        """
        Consulta os endpoints públicos do SIPAC/SIG sem seguir redirecionamentos para SSO.
        """
        results: List[Dict[str, Any]] = []
        endpoints = (
            (self.SIG_EDITAIS_ANDAMENTO_URL, "Licitação SIPAC"),
            (self.SIG_ATAS_VIGENTES_URL, "Ata de Registro de Preços / Licitação SIPAC"),
        )

        with self._get_client(follow_redirects=False) as client:
            for url, tipo_label in endpoints:
                try:
                    resp = client.get(url)
                    if resp.status_code in (301, 302, 303, 307, 308):
                        location = resp.headers.get("location", "")
                        logger.info(
                            f"Endpoint SIPAC ({url}) redirecionou para '{location}' (possível SSO); ignorando com segurança."
                        )
                        continue
                    if resp.status_code in (401, 403):
                        logger.warning(f"Endpoint SIPAC ({url}) retornou HTTP {resp.status_code}; ignorando.")
                        continue
                    if resp.status_code != 200 or not resp.text:
                        logger.warning(f"Endpoint SIPAC ({url}) retornou HTTP {resp.status_code}.")
                        continue
                    results.extend(self._parse_sig_public_table_html(resp.text, source_url=url, default_tipo=tipo_label))
                except Exception as e:
                    logger.warning(f"Falha ao consultar área pública do SIPAC ({url}): {e}")

        return results

    def fetch_editais(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Coleta editais internos DAF, pregões eletrônicos DAF e licitações/atas públicas do SIPAC.
        """
        cache_key = f"editais:{year if year is not None else 'all'}"
        now = time.time()
        if cache_key in self._cache:
            ts, cached = self._cache[cache_key]
            if now - ts < self.cache_ttl:
                return [dict(item) for item in cached]

        combined: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()

        with self._get_client() as client:
            # 1. Editais Internos DAF (`https://daf.unb.br/editais-daf`)
            try:
                resp_daf = client.get(self.EDITAIS_DAF_URL)
                if resp_daf.status_code == 200 and resp_daf.text:
                    for item in self._parse_editais_daf_html(resp_daf.text, page_url=self.EDITAIS_DAF_URL):
                        if item["identificador_origem"] not in seen_ids:
                            seen_ids.add(item["identificador_origem"])
                            combined.append(item)
            except Exception as e:
                logger.warning(f"Erro ao raspar editais internos do DAF ({self.EDITAIS_DAF_URL}): {e}")

            # 2. Pregões Eletrônicos e Licitações DAF (`https://daf.unb.br/editais`)
            try:
                resp_preg = client.get(self.PREGOES_URL)
                if resp_preg.status_code == 200 and resp_preg.text:
                    for item in self._parse_pregoes_daf_html(resp_preg.text, page_url=self.PREGOES_URL):
                        if item["identificador_origem"] not in seen_ids:
                            seen_ids.add(item["identificador_origem"])
                            combined.append(item)
            except Exception as e:
                logger.warning(f"Erro ao raspar pregões do DAF ({self.PREGOES_URL}): {e}")

        # 3. Área pública do SIPAC (`https://sig.unb.br/public/...`) isolada contra falhas/SSO
        for item in self._fetch_from_sig_public():
            if item["identificador_origem"] not in seen_ids:
                seen_ids.add(item["identificador_origem"])
                combined.append(item)

        if year is not None:
            combined = [item for item in combined if item.get("ano") == year]

        self._cache[cache_key] = (now, [dict(item) for item in combined])
        return combined

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """
        Retorna os documentos associados a um edital/pregão do DAF ou ata pública do SIPAC.
        """
        if not edital_url:
            return []

        if edital_url in self._docs_by_page and self._docs_by_page[edital_url]:
            return [dict(d) for d in self._docs_by_page[edital_url]]

        if self._is_document_url(edital_url):
            filename = edital_url.rstrip("/").split("/")[-1]
            return [self._make_doc(filename, edital_url)]

        target_url = edital_url.split("#")[0]
        try:
            with self._get_client(follow_redirects=False) as client:
                resp = client.get(target_url)
                if resp.status_code in (301, 302, 303, 307, 308, 401, 403):
                    return []
                resp.raise_for_status()
        except Exception as e:
            logger.error(f"Erro ao buscar documentos do edital DAF ({edital_url}): {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        content = soup.select_one("div.item-page, main, article, #content") or soup
        docs: List[Dict[str, str]] = []
        seen: Set[str] = set()
        for a_tag in content.find_all("a", href=True):
            href = self._normalize_daf_url(a_tag.get("href", ""), base_url=target_url)
            if not self._is_document_url(href) or href in seen:
                continue
            seen.add(href)
            label = self._clean_text(a_tag.get_text(" ", strip=True)) or href.split("/")[-1]
            docs.append(self._make_doc(label, href))

        self._docs_by_page[edital_url] = docs
        return [dict(d) for d in docs]

    def download_documento(self, url: str, timeout: float = 15.0) -> bytes:
        with self._get_client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content


daf_scraper = DAFScraper()

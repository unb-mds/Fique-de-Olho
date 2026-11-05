"""Scraper para os processos seletivos públicos do SIGAA UnB (PPGs, Graduação e Extensão)."""

from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document

logger = logging.getLogger(__name__)

SIGAA_BASE_URL = "https://sigaa.unb.br"
SIGAA_PROCESSOS_URL = "https://sigaa.unb.br/sigaa/public/processo_seletivo/lista.jsf"
SIGAA_PPG_LISTA_URL = "https://sigaa.unb.br/sigaa/public/curso/lista.jsf?nivel=S&aba=p-stricto"
SIGAA_EXTENSAO_URL = "https://sigaa.unb.br/sigaa/public/extensao/paginaListaPeriodosInscricoesAtividadesPublico.jsf?semuni=false&aba=p-extensao"

SIGAA_NIVEIS_URLS = [
    ("S", "https://sigaa.unb.br/sigaa/public/processo_seletivo/lista.jsf?nivel=S&aba=p-stricto"),
    ("G", "https://sigaa.unb.br/sigaa/public/processo_seletivo/lista.jsf?nivel=G&aba=p-graduacao"),
    ("T", "https://sigaa.unb.br/sigaa/public/processo_seletivo/lista.jsf?nivel=T&aba=p-tecnico"),
    ("L", "https://sigaa.unb.br/sigaa/public/processo_seletivo/lista.jsf?nivel=L&aba=p-lato"),
]

DEFAULT_TIMEOUT = 15.0
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Fique-de-Olho/1.0"

DATE_INTERVAL_PATTERN = re.compile(
    r"(\d{1,2}/\d{1,2}/\d{4})\s*(?:a|à|até|-|–)\s*(\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE,
)
DATE_SINGLE_PATTERN = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")


def parse_sigaa_html(html: str, base_url: str = SIGAA_BASE_URL) -> List[Dict[str, Any]]:
    """Extrai os editais e processos seletivos contidos nas tabelas públicas do SIGAA."""
    soup = BeautifulSoup(html, "html.parser")
    editais: List[Dict[str, Any]] = []
    seen = set()

    # Localiza tabelas de listagem padrão do SIGAA
    tables = soup.find_all("table", class_=lambda c: c and ("listagem" in c or "formulario" in c))
    if not tables:
        tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if not cells or len(cells) < 2:
                continue

            row_text = row.get_text(" ", strip=True)
            if "Nenhum processo seletivo" in row_text or "CPF:" in row_text:
                continue

            links = row.find_all("a", href=True)
            if not links:
                continue

            target_link = None
            for a in links:
                href = a["href"].strip()
                t = a.get_text(" ", strip=True)
                if any(k in href.lower() or k in t.lower() for k in ["processo", "edital", "detalhe", "verarquivo", "inscricao"]):
                    target_link = a
                    break
            if not target_link:
                target_link = links[0]

            href = target_link["href"].strip()
            full_url = urljoin(base_url, href)
            if full_url in seen:
                continue
            seen.add(full_url)

            titulo = target_link.get_text(" ", strip=True)
            if not titulo or len(titulo) < 3:
                titulo = row_text[:120].strip()

            inicio_inscricao = ""
            fim_inscricao = ""
            data_pub = ""

            interval_match = DATE_INTERVAL_PATTERN.search(row_text)
            if interval_match:
                inicio_inscricao = interval_match.group(1)
                fim_inscricao = interval_match.group(2)
                data_pub = inicio_inscricao
            else:
                single_match = DATE_SINGLE_PATTERN.search(row_text)
                if single_match:
                    data_pub = single_match.group(1)

            ano: Optional[int] = None
            if fim_inscricao and len(fim_inscricao) >= 10:
                ano = int(fim_inscricao[-4:])
            elif data_pub and len(data_pub) >= 10:
                ano = int(data_pub[-4:])

            documentos: List[Dict[str, Any]] = []
            for a in links:
                h = a["href"].strip()
                t = a.get_text(" ", strip=True) or "Edital/Arquivo SIGAA"
                if any(doc_k in h.lower() for doc_k in [".pdf", "verarquivo", "documento"]):
                    doc_url = urljoin(base_url, h)
                    documentos.append({
                        "titulo": t,
                        "link": doc_url,
                        "tipo": classify_document(t, doc_url),
                    })

            status = "aberto" if ("aberto" in row_text.lower() or "inscreva-se" in row_text.lower()) else "fechado"

            editais.append({
                "titulo": titulo,
                "assunto": f"Processo Seletivo Acadêmico - {titulo}",
                "tipo": "Processo Seletivo Acadêmico",
                "tipo_edital": "Processo Seletivo / Pós-Graduação",
                "descricao": f"Processo seletivo acadêmico publicado no portal SIGAA da Universidade de Brasília: {titulo}.",
                "resumo": f"Processo seletivo acadêmico publicado no portal SIGAA da Universidade de Brasília: {titulo}.",
                "link": full_url,
                "data_publicacao": data_pub,
                "inicio_inscricao": inicio_inscricao,
                "fim_inscricao": fim_inscricao,
                "status": status,
                "documentos": documentos,
                "ano": ano,
            })

    return editais


def parse_sigaa_ppg_processos_html(html: str, ppg_nome: str, ppg_id: str) -> List[Dict[str, Any]]:
    """Extrai os editais de mestrado e doutorado a partir da página pública de processos do PPG.

    URL de origem: https://sigaa.unb.br/sigaa/public/programa/processo_seletivo.jsf?lc=pt_BR&id={ppg_id}
    """
    soup = BeautifulSoup(html, "html.parser")
    editais: List[Dict[str, Any]] = []

    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        for row in rows:
            text = row.get_text(" ", strip=True)
            if not text or "Período" in text or "Processos Seletivos" in text:
                continue

            # Intervalo de datas
            interval_match = DATE_INTERVAL_PATTERN.search(text)
            inicio_inscricao = ""
            fim_inscricao = ""
            ano: Optional[int] = None

            if interval_match:
                inicio_inscricao = interval_match.group(1)
                fim_inscricao = interval_match.group(2)
                try:
                    ano = int(fim_inscricao.split("/")[-1])
                except (ValueError, IndexError):
                    pass

            # Extração limpa do título
            spans = row.find_all("span", class_="destaqueProcessoeletivo")
            titulo = ""
            for s in spans:
                if "data" not in s.get("class", []):
                    titulo = s.get_text(" ", strip=True)
                    break

            if not titulo:
                a_tag = row.find("a")
                if a_tag:
                    titulo = a_tag.get_text(" ", strip=True)
                else:
                    titulo = text[:100].strip()

            # Limpa ruídos de quebra de linha e sufixos de datas redundantes no título
            titulo = re.sub(r"\s*\(\s*\d{1,2}/\d{1,2}/\d{4}[\s\S]*?\)", "", titulo)
            titulo = re.sub(r"\s+", " ", titulo).strip()

            # Extração do ID do processo via onclick JSF
            proc_id = ""
            a_elem = row.find("a", onclick=True)
            if a_elem:
                m_id = re.search(r"'id'\s*:\s*'(\d+)'", a_elem.get("onclick", ""))
                if m_id:
                    proc_id = m_id.group(1)

            # Cálculo de status baseado na data limite de inscrição
            status = "fechado"
            if fim_inscricao:
                try:
                    d, m, y = map(int, fim_inscricao.split("/"))
                    dt_fim = datetime(y, m, d, 23, 59, 59, tzinfo=timezone.utc)
                    if dt_fim >= datetime.now(timezone.utc):
                        status = "aberto"
                except Exception:
                    status = "aberto" if ano and ano >= 2026 else "fechado"

            url_programa = f"https://sigaa.unb.br/sigaa/public/programa/processo_seletivo.jsf?lc=pt_BR&id={ppg_id}"

            editais.append({
                "titulo": titulo,
                "assunto": f"Processo Seletivo de Pós-Graduação (Mestrado/Doutorado) - {ppg_nome}",
                "tipo": "Pós-Graduação",
                "tipo_edital": "Pós-Graduação / Mestrado e Doutorado",
                "descricao": f"Edital de seleção para cursos de pós-graduação stricto sensu (Mestrado/Doutorado) no programa {ppg_nome}.",
                "resumo": f"Edital de seleção para cursos de pós-graduação stricto sensu no programa {ppg_nome}.",
                "link": url_programa,
                "programa": ppg_nome,
                "inicio_inscricao": inicio_inscricao,
                "fim_inscricao": fim_inscricao,
                "data_publicacao": inicio_inscricao,
                "status": status,
                "ano": ano,
                "processo_id": proc_id,
            })

    return editais


def parse_sigaa_extensao_html(html: str) -> List[Dict[str, Any]]:
    """Extrai cursos e eventos de extensão com períodos de inscrição abertos no SIGAA."""
    soup = BeautifulSoup(html, "html.parser")
    editais: List[Dict[str, Any]] = []
    table = soup.find("table", class_=lambda c: c and "listagem" in c)
    if not table:
        return editais

    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 7:
            continue

        col0 = tds[0].get_text(" ", strip=True)
        if "Coordena" not in col0 and "Realiza" not in col0:
            continue

        tipo = tds[1].get_text(" ", strip=True) or "EXTENSÃO"
        area = tds[2].get_text(" ", strip=True)
        unidade = tds[3].get_text(" ", strip=True)
        campus = tds[4].get_text(" ", strip=True)
        periodo_insc = tds[5].get_text(" ", strip=True)
        periodo_atv = tds[6].get_text(" ", strip=True)

        titulo_limpo = col0.split("Coordena")[0].split("Realiza")[0].strip()
        titulo_limpo = re.sub(r"\s+", " ", titulo_limpo)

        m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})\s*a\s*(\d{1,2}/\d{1,2}/\d{4})", periodo_insc)
        inicio_inscricao = m.group(1) if m else ""
        fim_inscricao = m.group(2) if m else ""

        ano: Optional[int] = None
        if fim_inscricao and len(fim_inscricao) >= 10:
            try:
                ano = int(fim_inscricao[-4:])
            except ValueError:
                pass
        elif inicio_inscricao and len(inicio_inscricao) >= 10:
            try:
                ano = int(inicio_inscricao[-4:])
            except ValueError:
                pass

        editais.append({
            "titulo": f"[{tipo}] {titulo_limpo}",
            "assunto": f"Ação / Curso de Extensão Comunitária - {titulo_limpo}",
            "tipo": "Extensão",
            "tipo_edital": "Extensão",
            "categoria": f"Extensão / {tipo}",
            "descricao": f"Ação de extensão comunitária ({tipo}) registrada no SIGAA da UnB pela unidade {unidade}. Área: {area}.",
            "resumo": f"Ação de extensão comunitária ({tipo}) registrada no SIGAA da UnB pela unidade {unidade}.",
            "link": SIGAA_EXTENSAO_URL,
            "programa": f"{unidade} ({campus})" if campus else unidade,
            "area_tematica": area,
            "inicio_inscricao": inicio_inscricao,
            "fim_inscricao": fim_inscricao,
            "data_publicacao": inicio_inscricao,
            "status": "aberto",
            "ano": ano,
            "periodo_realizacao": periodo_atv,
            "documentos": [],
        })

    return editais


class SIGAAScraper(BaseScraper):
    """Implementação do scraper para processos seletivos públicos do SIGAA UnB."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self._programas_cache: List[Tuple[str, str]] = []

    @property
    def orgao_origem(self) -> str:
        return "SIGAA"

    def fetch_programas_pos_graduacao(self, client: httpx.Client) -> List[Tuple[str, str]]:
        """Mapeia os 110 Programas de Pós-Graduação (PPGs) ativos na UnB via SIGAA."""
        if self._programas_cache:
            return self._programas_cache

        programas: List[Tuple[str, str]] = []
        try:
            resp = client.get(SIGAA_PPG_LISTA_URL)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    h = a["href"]
                    m = re.search(r"id=(\d+)", h)
                    if m and "portal.jsf" in h:
                        prog_id = m.group(1)
                        prog_name = a.get_text(" ", strip=True)
                        programas.append((prog_id, prog_name))
                if programas:
                    self._programas_cache = programas
        except Exception as exc:
            logger.warning(f"Erro ao mapear programas de pós-graduação no SIGAA: {exc}")

        return programas

    def fetch_editais(
        self,
        year: Optional[int] = None,
        max_programs: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Consulta os processos seletivos públicos e os editais de PPGs no SIGAA UnB.

        Args:
            year: Ano de referência para filtragem (opcional).
            max_programs: Limite de programas a consultar (None para todos os 110).

        Returns:
            Lista de editais padronizados com títulos, programas, datas e status.
        """
        editais: List[Dict[str, Any]] = []
        seen_keys = set()

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                # 1. Consulta o catálogo geral de processos abertos (Graduação, Técnico e Geral)
                for nivel, url in SIGAA_NIVEIS_URLS:
                    try:
                        resp = client.get(url)
                        if resp.status_code == 200:
                            parsed = parse_sigaa_html(resp.text, base_url=str(resp.url))
                            for ed in parsed:
                                ed["nivel"] = nivel
                                key = (ed.get("titulo", ""), ed.get("link", ""))
                                if key not in seen_keys:
                                    seen_keys.add(key)
                                    if year is not None and ed.get("ano") is not None and ed["ano"] != year:
                                        continue
                                    editais.append(ed)
                    except httpx.HTTPError as exc:
                        logger.warning(f"Erro ao consultar SIGAA nível {nivel}: {exc}")
                        continue

                # 2. Consulta os editais dos Programas de Pós-Graduação (PPGs da UnB)
                ppgs = self.fetch_programas_pos_graduacao(client)
                target_ppgs = ppgs[:max_programs] if max_programs is not None else ppgs

                for prog_id, prog_name in target_ppgs:
                    url_ps = f"https://sigaa.unb.br/sigaa/public/programa/processo_seletivo.jsf?lc=pt_BR&id={prog_id}"
                    try:
                        r = client.get(url_ps)
                        if r.status_code == 200 and "processo_seletivo.jsf" in str(r.url):
                            prog_editais = parse_sigaa_ppg_processos_html(r.text, prog_name, prog_id)
                            for ed in prog_editais:
                                key = (ed.get("titulo", ""), prog_id, ed.get("processo_id", ""))
                                if key not in seen_keys:
                                    seen_keys.add(key)
                                    if year is not None and ed.get("ano") is not None and ed["ano"] != year:
                                        continue
                                    editais.append(ed)
                    except httpx.HTTPError:
                        continue

                # 3. Consulta cursos e eventos de extensão com inscrições abertas no SIGAA
                try:
                    resp_ext = client.get(SIGAA_EXTENSAO_URL)
                    if resp_ext.status_code == 200:
                        ext_editais = parse_sigaa_extensao_html(resp_ext.text)
                        for ed in ext_editais:
                            key = (ed.get("titulo", ""), ed.get("inicio_inscricao", ""))
                            if key not in seen_keys:
                                seen_keys.add(key)
                                if year is not None and ed.get("ano") is not None and ed["ano"] != year:
                                    continue
                                editais.append(ed)
                except httpx.HTTPError as exc:
                    logger.warning(f"Erro ao consultar extensão no SIGAA: {exc}")

        except Exception as exc:
            logger.error(f"Erro ao conectar ao SIGAA UnB: {exc}")
            return editais

        return editais

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai os documentos PDF associados a um processo seletivo do SIGAA."""
        if edital_url.lower().endswith(".pdf") or "verarquivo" in edital_url.lower():
            return [{"titulo": "Documento Oficial SIGAA", "link": edital_url, "tipo": classify_document(edital_url, edital_url)}]

        documentos: List[Dict[str, Any]] = []
        seen = set()

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                resp = client.get(edital_url)
                if resp.status_code != 200:
                    return documentos

                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    h = a["href"].strip()
                    if ".pdf" in h.lower() or "verarquivo" in h.lower():
                        full_h = urljoin(str(resp.url), h)
                        if full_h in seen:
                            continue
                        seen.add(full_h)
                        t = a.get_text(" ", strip=True) or "Documento Processo Seletivo SIGAA"
                        documentos.append({
                            "titulo": t,
                            "link": full_h,
                            "tipo": classify_document(t, full_h),
                        })
        except Exception as exc:
            logger.error(f"Erro ao extrair documentos de {edital_url} no SIGAA: {exc}")

        return documentos


sigaa_scraper = SIGAAScraper()

"""Scraper para o HUB-UnB (Hospital Universitário de Brasília / Ebserh / HU Brasil).

Coleta e categoriza todos os editais e chamadas públicas vinculados ao HUB-UnB:
1. Residência Médica (COREME) e Residência Multiprofissional em Saúde (COREMU):
   - Exame Nacional de Residência (ENARE / FGV / Ebserh) e edições anteriores;
   - Editais de transferência interna/externa e vagas remanescentes do HUB-UnB.
2. Iniciação Científica (PIC / HU Brasil - HUB-UnB — edições anuais e resultados).
3. Iniciação Tecnológica (PIT / HU Brasil - HUB-UnB — edições anuais e resultados).
4. Pesquisa, Inovação e Saúde Digital no HUB-UnB (Rede HU+, Saúde Digital, Ocean/TIC).
5. Processos Seletivos Simplificados (PSS), Concursos Públicos e Estágios aplicáveis
   ao HUB-UnB e à Rede Nacional Ebserh em Brasília.

Fontes oficiais:
- Portal Institucional HUB-UnB (Gov.br):
  https://www.gov.br/hubrasil/pt-br/hospitais-universitarios/regiao-centro-oeste/hub-unb
  (redirecionamento oficial de https://www.gov.br/ebserh/pt-br/hospitais-universitarios/regiao-centro-oeste/hub-unb)
- ENARE (Residências): https://www.gov.br/hubrasil/pt-br/ensino-e-pesquisa/exame-nacional-de-residencia-enare
- PSS / Concursos / Estágios: https://www.gov.br/hubrasil/pt-br/acesso-a-informacao/agentes-publicos/concursos-e-selecoes
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import html as html_lib
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
import unicodedata
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.modules.scraper.base import BaseScraper
from app.modules.scraper.deg import classify_document
from app.modules.scraper.ocean import (
    OCEAN_RESIDENCIA_URL,
    extract_ocean_residencia_unb_docs,
)
from app.modules.scraper.parser import parse_data_interval

logger = logging.getLogger(__name__)

HUBRASIL_BASE_URL = "https://www.gov.br/hubrasil/pt-br"
HUB_UNB_BASE_URL = f"{HUBRASIL_BASE_URL}/hospitais-universitarios/regiao-centro-oeste/hub-unb"

# Endpoints de Ensino, Residência, Pesquisa e Inovação do HUB-UnB
HUB_PIC_INDEX_URL = f"{HUB_UNB_BASE_URL}/ensino-e-pesquisa/pesquisa/pic-ebserh"
HUB_PIT_INDEX_URL = (
    f"{HUB_UNB_BASE_URL}/ensino-e-pesquisa/pesquisa/"
    "programa-de-iniciacao-tecnologica-pit-ebserh-hub-unb"
)
HUB_PESQUISA_EDITAIS_URL = f"{HUB_UNB_BASE_URL}/ensino-e-pesquisa/pesquisa/editais"
HUB_JORNADA_CIENTIFICA_URL = f"{HUB_UNB_BASE_URL}/ensino-e-pesquisa/pesquisa/jornanda-cientifica"
HUB_RESIDENCIA_TIC_BASE_URL = (
    f"{HUB_UNB_BASE_URL}/ensino-e-pesquisa/pesquisa/projeto-residencia-em-tic-53-1"
)
HUB_RESIDENCIA_TIC_URL = f"{HUB_RESIDENCIA_TIC_BASE_URL}/editais-e-oportunidades"
HUB_RESIDENCIA_TIC_CURSOS_URL = f"{HUB_RESIDENCIA_TIC_BASE_URL}/cursos-e-atividades-gratuitas"
HUB_COREMU_TRANSFERENCIA_URL = (
    f"{HUB_UNB_BASE_URL}/ensino-e-pesquisa/ensino/pos-graduacao/cursos/transferencia"
)
HUB_COREME_TRANSFERENCIA_URL = (
    f"{HUB_UNB_BASE_URL}/ensino-e-pesquisa/ensino/pos-graduacao/cursos-1/transferencia"
)
HUB_EXTENSAO_URL = (
    f"{HUB_UNB_BASE_URL}/ensino-e-pesquisa/ensino/graduacao/extensao/sobre-a-extensao"
)

# Endpoints de Residência (ENARE / FGV) e Concursos / PSS / Estágios
HUB_ENARE_URL = f"{HUBRASIL_BASE_URL}/ensino-e-pesquisa/exame-nacional-de-residencia-enare"
HUB_ENARE_ANTERIORES_URL = f"{HUB_ENARE_URL}/edicoes-anteriores"
FGV_ENARE_2026_BASE_URL = "https://enare2026.conhecimento.fgv.br"
FGV_ENARE_2026_PUBLICACOES_URL = f"{FGV_ENARE_2026_BASE_URL}/publicacoes/"
HUB_CONCURSOS_BASE_URL = f"{HUBRASIL_BASE_URL}/acesso-a-informacao/agentes-publicos/concursos-e-selecoes"
HUB_PSS_BASE_URL = (
    f"{HUB_CONCURSOS_BASE_URL}/selecoes/processos-seletivos/processo-seletivo-simplificado-pss"
)
HUB_CONCURSOS_ANUAIS_BASE_URL = f"{HUB_CONCURSOS_BASE_URL}/concursos"
HUB_ESTAGIOS_URL = f"{HUB_CONCURSOS_BASE_URL}/estagios"

def _current_year() -> int:
    """Retorna o ano civil atual em UTC para execuções periódicas."""
    return datetime.now(timezone.utc).year


def _build_pss_years(current_year: Optional[int] = None) -> Tuple[int, ...]:
    yr = current_year or _current_year()
    return tuple(range(yr, 2021, -1))


def _build_concursos_years(current_year: Optional[int] = None) -> Tuple[int, ...]:
    yr = current_year or _current_year()
    return tuple(y for y in range(yr, 2021, -1) if y != 2025)


PSS_YEARS: Tuple[int, ...] = _build_pss_years()
CONCURSOS_YEARS: Tuple[int, ...] = _build_concursos_years()

DEFAULT_TIMEOUT = 20.0
CACHE_TTL_SECONDS = 300.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Fique-de-Olho/1.0"
)

DOC_EXTENSIONS = (".pdf", ".doc", ".docx", ".zip", ".odt", ".xlsx", ".xls")
GUIDE_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")
PLAIN_URL_DOC_RE = re.compile(r"https?://[^\s<>\"')]+?\.(?:pdf|docx?|xlsx?|odt|zip)\b", re.IGNORECASE)
EDITAL_YEAR_PATTERN = re.compile(r"\b\d{1,4}[./-](20\d{2})\b")
GENERAL_YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")
DATE_SLASH_PATTERN = re.compile(r"\b(\d{1,2}/\d{1,2}/20\d{2})\b")
DATE_PT_PATTERN = re.compile(
    r"\b(\d{1,2}\s+de\s+(?:janeiro|fevereiro|março|marco|abril|maio|junho|"
    r"julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+20\d{2})\b",
    re.IGNORECASE,
)

MESES_PT_NUM = {
    "janeiro": "01",
    "fevereiro": "02",
    "marco": "03",
    "março": "03",
    "abril": "04",
    "maio": "05",
    "junho": "06",
    "julho": "07",
    "agosto": "08",
    "setembro": "09",
    "outubro": "10",
    "novembro": "11",
    "dezembro": "12",
}

# Padrão estrito para filtrar PSS destinados ao HUB-UnB, Sede Brasília ou Rede Nacional Ebserh
HUB_PSS_MATCH_PATTERN = re.compile(
    r"\bhub[-\s_/]*unb\b|\bnacional\b|\bebserh\s*[/\-]\s*sede\b|\bregiao[-\s]+centro[-\s]+oeste[-\s]+sede\b",
    re.IGNORECASE,
)

REGISTRATION_HOST_PATTERNS = (
    "redcap.ebserh.gov.br",
    "redcap.link",
    "sig.ebserh.gov.br/redepesquisa",
    "forms.office.com",
    "forms.gle",
    "docs.google.com/forms",
    "hospitais.proadi-sus.org.br/editais",
    "grants.nih.gov",
    "nih.gov/grants-funding",
    "gov.uk/international-development-funding",
    "abdi.com.br/industria40",
)

PSS_DOC_SUBFOLDER_SLUGS = (
    "edital-normativo",
    "editais-normativos",
    "editais",
    "resultado",
    "resultados",
    "convocacao",
    "convocacoes",
    "comunicados",
    "area-medica",
    "area-uni-e-multiprofissional",
    "area-uni-e-multiprofissional-1",
)
PSS_LISTING_SUBFOLDER_SLUGS = (
    "edital-normativo",
    "editais-normativos",
    "editais",
    "resultado",
    "resultados",
    "area-medica",
    "area-uni-e-multiprofissional",
    "area-uni-e-multiprofissional-1",
)


def _clean_text(raw: str) -> str:
    """Normaliza espaços, Unicode NFC e decodifica entidades HTML."""
    if not raw:
        return ""
    unescaped = unicodedata.normalize("NFC", html_lib.unescape(raw))
    return re.sub(r"\s+", " ", unescaped).strip()


def normalize_govbr_doc_url(url: str, base_url: str = HUBRASIL_BASE_URL) -> str:
    """Normaliza URLs de documentos no Plone/Gov.br, removendo sufixos '/view' ou '/@@images/...'."""
    if not url:
        return ""
    full = urljoin(base_url, url.strip())
    full = re.sub(r"(\.(?:jpe?g|png))/@@images/.*$", r"\1", full, flags=re.IGNORECASE)
    lower = full.lower()
    for ext in (*DOC_EXTENSIONS, *GUIDE_IMAGE_EXTENSIONS):
        if lower.endswith(f"{ext}/view"):
            return full[:-5]
    return full


def is_document_url(url: str) -> bool:
    """Indica se uma URL aponta para documento anexo (.pdf, .docx, Liferay /documents/d/, @@download, etc.)."""
    if not url:
        return False
    normalized = normalize_govbr_doc_url(url).lower()
    parsed = urlparse(normalized)
    parsed_path = parsed.path.lower().rstrip("/")
    if parsed_path.endswith(DOC_EXTENSIONS):
        return True
    if "/@@download/" in parsed_path:
        return True
    if "portal.mec.gov.br/docman/" in normalized and normalized.endswith("/file"):
        return True
    # Repositórios Liferay de agências de fomento (ex.: FAPDF e FINEP: /documents/d/fap/...-pdf)
    if "/documents/d/" in parsed_path:
        return True
    # Guias visuais e cronogramas oficiais publicados no PIC / PIT do HUB-UnB
    if parsed_path.endswith(GUIDE_IMAGE_EXTENSIONS):
        filename = parsed_path.split("/")[-1]
        if any(k in filename for k in ("guia", "cronograma", "edital", "errata", "retificacao")):
            return True
    return False


def is_hub_relevant_pss(title: str, href: str) -> bool:
    """Filtra Processos Seletivos Simplificados (PSS) aplicáveis ao HUB-UnB / Brasília / Nacional.

    Evita falso positivo com o domínio 'gov.br/hubrasil' avaliando apenas o título
    e o último segmento (slug) da URL.
    """
    slug = urlparse(href or "").path.rstrip("/").split("/")[-1]
    candidate = f"{title} {slug}"
    return bool(HUB_PSS_MATCH_PATTERN.search(candidate))


def _normalize_date_str(raw_date: str, default_year: Optional[int] = None) -> str:
    """Converte datas brasileiras em texto ou barras para o formato padrão DD/MM/YYYY."""
    fallback_yr = default_year or _current_year()
    if not raw_date:
        return f"01/01/{fallback_yr}"

    m_slash = DATE_SLASH_PATTERN.search(raw_date)
    if m_slash:
        parts = m_slash.group(1).split("/")
        return f"{int(parts[0]):02d}/{int(parts[1]):02d}/{parts[2]}"

    m_pt = DATE_PT_PATTERN.search(raw_date)
    if m_pt:
        m_parts = re.match(
            r"(\d{1,2})\s+de\s+([A-Za-zÀ-ÿ]+)\s+de\s+(20\d{2})",
            m_pt.group(1).strip(),
            re.IGNORECASE,
        )
        if m_parts:
            day = int(m_parts.group(1))
            month = MESES_PT_NUM.get(m_parts.group(2).lower(), "01")
            year = m_parts.group(3)
            return f"{day:02d}/{month}/{year}"

    m_iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", raw_date)
    if m_iso:
        return f"{m_iso.group(3)}/{m_iso.group(2)}/{m_iso.group(1)}"

    return f"01/01/{fallback_yr}"


def classify_hub_document(title: str, link: str) -> str:
    """Classifica um documento vinculado a um edital do HUB-UnB."""
    lower = f"{title} {link}".lower()
    is_intermediate_stage = any(
        st in lower
        for st in [
            "preliminar",
            "provisorio",
            "provisório",
            "prova objetiva",
            "gabarito",
            "heteroidentificação",
            "heteroidentificacao",
            "heteroidenficação",
            "heteroidenficacao",
            "biopsicossocial",
            "perícia médica",
            "pericia medica",
            "análise curricular",
            "analise curricular",
            "avaliação de títulos",
            "avaliacao de titulos",
            "prova de títulos",
            "prova de titulos",
            "isenção",
            "isencao",
            "atendimento especial",
            "condição especial",
            "condicao especial",
            "nome social",
            "homologação das inscrições",
            "homologacao das inscricoes",
            "inscrições homologadas",
            "inscricoes homologadas",
            "inscrições deferidas",
            "inscricoes deferidas",
            "inscrição deferida",
            "inscricao deferida",
        ]
    )
    if any(
        k in lower
        for k in [
            "retificacao",
            "retificação",
            "retificado",
            "prorrogacao",
            "prorrogação",
            "prorrogracao",
            "prorrogração",
            "alteracao",
            "alteração",
            "cronograma atualizado",
        ]
    ):
        return "retificacao"
    if any(
        k in lower
        for k in [
            "resultado definitivo",
            "resultado_definitivo",
            "resultado final",
            "resultado_final",
            "resultado-final",
            "homologacao",
            "homologação",
            "convocacao",
            "convocação",
        ]
    ):
        if is_intermediate_stage or "convocação para" in lower or "convocacao para" in lower or "convocação das provas" in lower or "convocacao das provas" in lower:
            return "resultado_provisorio"
        return "resultado_final"
    if is_intermediate_stage or any(
        k in lower
        for k in [
            "resultado preliminar",
            "resultado_preliminar",
            "resultado provisorio",
            "resultado provisório",
            "recursos interpostos",
            "resultado_recursos",
        ]
    ):
        return "resultado_provisorio"
    return classify_document(title, link)


def classify_hub_edital(titulo: str, url: str = "", texto: str = "") -> Dict[str, str]:
    """Determina tipo, tipo_edital e programa de um edital do HUB-UnB."""
    title_url = f"{titulo} {url}".lower()
    combined = f"{titulo} {url} {texto}".lower()

    has_medica = any(
        k in title_url
        for k in ["coreme", "residência médica", "residencia medica", "cursos-1/transferencia", "#residencia-medica"]
    )
    has_multi = any(
        k in title_url
        for k in [
            "coremu",
            "multiprofissional",
            "uniprofissional",
            "cursos/transferencia",
            "#residencia-multiprofissional",
        ]
    )

    if has_medica and not has_multi:
        return {
            "tipo": "Residência Médica (COREME)",
            "tipo_edital": "Saúde / Residência Médica COREME",
            "programa": "Residência Médica HUB-UnB (COREME / ENARE)",
        }

    if has_multi and not has_medica:
        return {
            "tipo": "Residência Multiprofissional em Saúde (COREMU)",
            "tipo_edital": "Saúde / Residência Multiprofissional COREMU",
            "programa": "Residência Multiprofissional HUB-UnB (COREMU / ENARE)",
        }

    if any(
        k in combined
        for k in [
            "enare",
            "exame nacional de residência",
            "exame nacional de residencia",
            "residência médica",
            "residencia medica",
            "residência multiprofissional",
            "residencia multiprofissional",
            "coreme",
            "coremu",
            "pos-graduacao/cursos",
        ]
    ):
        return {
            "tipo": "Residência Médica e Multiprofissional (COREME/COREMU)",
            "tipo_edital": "Saúde / Residência Médica e Multiprofissional",
            "programa": "ENARE e Residências em Saúde HUB-UnB",
        }

    if "/graduacao/extensao" in combined or "atividades de extensão" in combined or "projetos de extensão" in combined:
        return {
            "tipo": "Extensão Hospitalar e Universitária",
            "tipo_edital": "Extensão / Atividades de Extensão HUB-UnB",
            "programa": "Extensão Universitária no HUB-UnB",
        }

    if any(
        k in combined
        for k in [
            "iniciação tecnológica",
            "iniciacao tecnologica",
            "pit/ebserh",
            "pit/hubrasil",
            "pit-ebserh",
            "pit-hu-brasil",
            "edital pit",
        ]
    ) or re.search(r"\bpit\b", combined):
        return {
            "tipo": "Iniciação Tecnológica em Saúde (PIT)",
            "tipo_edital": "Inovação em Saúde / Iniciação Tecnológica PIT",
            "programa": "Programa de Iniciação Tecnológica (PIT/HUB-UnB)",
        }

    if any(
        k in combined
        for k in [
            "iniciação científica",
            "iniciacao cientifica",
            "pic/ebserh",
            "pic/hubrasil",
            "pic-ebserh",
            "pic-hu-brasil",
            "edital pic",
        ]
    ) or re.search(r"\bpic\b", combined):
        return {
            "tipo": "Iniciação Científica em Saúde (PIC)",
            "tipo_edital": "Pesquisa em Saúde / Iniciação Científica PIC",
            "programa": "Programa de Iniciação Científica (PIC/HUB-UnB)",
        }

    if any(
        k in combined
        for k in [
            "processo seletivo simplificado",
            "processo-seletivo-simplificado",
        ]
    ) or re.search(r"\bpss\b", combined):
        return {
            "tipo": "Processo Seletivo Simplificado (PSS)",
            "tipo_edital": "Contratação Temporária / PSS HUB-UnB",
            "programa": "Processo Seletivo Simplificado Ebserh/HUB-UnB",
        }

    if "/concursos/" in combined or "concurso público" in combined or "concurso publico" in combined or "concurso nacional" in combined:
        return {
            "tipo": "Concurso Público Efetivo",
            "tipo_edital": "Carreira Hospitalar / Concurso Ebserh HUB-UnB",
            "programa": "Concurso Público Nacional Ebserh/HUB-UnB",
        }

    if "/estagios" in combined or "estágio" in combined or "estagio" in combined:
        return {
            "tipo": "Estágio Hospitalar",
            "tipo_edital": "Estágio / Programa de Estágio HUB-UnB",
            "programa": "Programa de Estágio Ebserh/HUB-UnB",
        }

    if (
        "residência tecnológica" in combined
        or "residencia tecnologica" in combined
        or "projeto-residencia-em-tic" in combined
        or "ocean unb" in combined
    ):
        return {
            "tipo": "Residência Tecnológica em Saúde Digital",
            "tipo_edital": "Saúde Digital / Residência Tecnológica Ocean UnB & HUB-UnB",
            "programa": "Residência Tecnológica em Saúde Digital (Ocean UnB / HUB-UnB)",
        }

    return {
        "tipo": "Pesquisa, Inovação e Saúde Digital",
        "tipo_edital": "Saúde Digital e Fomento / Pesquisa HUB-UnB",
        "programa": "Pesquisa e Inovação Tecnológica em Saúde (HUB-UnB)",
    }


def extract_plone_tab_urls(html: str, base_url: str) -> List[str]:
    """Extrai URLs dinâmicas de abas Plone (atributo data-url) em páginas Gov.br."""
    soup = BeautifulSoup(html or "", "html.parser")
    core = soup.find("div", id="content-core") or soup.find("main") or soup
    urls: List[str] = []
    seen = set()
    for el in core.find_all(attrs={"data-url": True}):
        raw = str(el.get("data-url") or "").strip()
        if not raw:
            continue
        full = urljoin(base_url, raw)
        if full not in seen:
            seen.add(full)
            urls.append(full)
    return urls


def extract_docs_from_govbr_html(html: str, page_url: str) -> List[Dict[str, Any]]:
    """Extrai todos os documentos (.pdf, .docx, etc.) contidos no corpo principal de uma página Gov.br."""
    soup = BeautifulSoup(html or "", "html.parser")
    core = (
        soup.find("div", id="content-core")
        or soup.find("article")
        or soup.find("main")
        or soup
    )
    docs: List[Dict[str, Any]] = []
    seen_links = set()

    for a in core.find_all("a", href=True):
        raw_href = str(a["href"]).strip()
        if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:")):
            continue

        if not is_document_url(urljoin(page_url, raw_href)):
            continue

        doc_url = normalize_govbr_doc_url(raw_href, base_url=page_url)
        if doc_url in seen_links:
            continue
        seen_links.add(doc_url)

        raw_title = _clean_text(a.get_text(" ", strip=True))
        # Remove sufixos automáticos de acessibilidade do Plone como ", formato, pdf, 254kb"
        raw_title = re.sub(r",\s*formato,\s*[a-z0-9]+.*$", "", raw_title, flags=re.IGNORECASE).strip()
        if not raw_title:
            filename = urlparse(doc_url).path.rstrip("/").split("/")[-1]
            raw_title = filename or "Documento Oficial HUB-UnB"

        docs.append({
            "titulo": raw_title,
            "link": doc_url,
            "tipo": classify_hub_document(raw_title, doc_url),
        })

    # Também captura URLs diretas de documentos (.pdf, .docx) escritas em texto puro no corpo da página
    core_text = core.get_text(" ", strip=True)
    for m_plain in PLAIN_URL_DOC_RE.finditer(core_text):
        plain_doc_url = normalize_govbr_doc_url(m_plain.group(0).rstrip(".,;)"), base_url=page_url)
        if plain_doc_url in seen_links:
            continue
        seen_links.add(plain_doc_url)
        filename = urlparse(plain_doc_url).path.rstrip("/").split("/")[-1]
        docs.append({
            "titulo": filename or "Documento Oficial HUB-UnB",
            "link": plain_doc_url,
            "tipo": classify_hub_document(filename, plain_doc_url),
        })

    return docs


def _extract_hub_registration_metadata(
    core: BeautifulSoup,
    body_text: str,
    page_url: str,
    default_year: int,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extrai `link_inscricao`, `inicio_inscricao` (ISO) e `fim_inscricao` (ISO) do corpo da página."""
    link_inscricao: Optional[str] = None
    fallback_external_link: Optional[str] = None

    for a in core.find_all("a", href=True):
        raw_href = str(a["href"]).strip()
        if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:")):
            continue
        full_href = urljoin(page_url, raw_href)
        if is_document_url(full_href):
            continue
        lower_href = full_href.lower()
        anchor_text = _clean_text(a.get_text(" ", strip=True)).lower()
        if any(pat in lower_href for pat in REGISTRATION_HOST_PATTERNS) or any(
            kw in anchor_text for kw in ("inscrição", "inscricao", "inscreva", "submissão", "submissao", "formulário de inscrição")
        ):
            link_inscricao = full_href
            break
        if "gov.br/hubrasil" not in lower_href and "gov.br/ebserh" not in lower_href and fallback_external_link is None:
            fallback_external_link = full_href

    if not link_inscricao and "/pesquisa/editais/" in page_url and fallback_external_link:
        link_inscricao = fallback_external_link

    inicio_iso: Optional[str] = None
    fim_iso: Optional[str] = None

    # Procura expressões explícitas de período de inscrições ou submissão
    insc_patterns = (
        r"(?:per[íi]odo\s+de\s+)?inscri[çc][õo]es\s*:?\s*(?:de\s+)?([^.|;\n]{6,80})",
        r"submiss[ãa]o(?:\s+de\s+propostas)?\s*:?\s*(?:de\s+)?([^.|;\n]{6,80})",
        r"(?:recebe\s+propostas|vig[êe]ncia[^.|;\n]{0,40})\s*(?:at[ée])\s*(\d{1,2}\s+de\s+[a-zçáéíóúãõâêîôû]+(?:\s+de\s+20\d{2})?|\d{1,2}/\d{1,2}/20\d{2})",
    )
    for pat in insc_patterns:
        m_insc = re.search(pat, body_text, re.IGNORECASE)
        if not m_insc:
            continue
        snippet = m_insc.group(1).strip()
        if re.search(r"20\d{2}", snippet) is None:
            snippet = f"{snippet} de {default_year}" if "de " in snippet.lower() else f"{snippet}/{default_year}"
        dt_ini, dt_fim = parse_data_interval(snippet, default_year=default_year)
        if dt_ini or dt_fim:
            inicio_iso = dt_ini.date().isoformat() if dt_ini else None
            fim_iso = dt_fim.date().isoformat() if dt_fim else inicio_iso
            break

    return link_inscricao, inicio_iso, fim_iso


def parse_ocean_unb_oportunidades_table(
    html: str,
    page_url: str = HUB_RESIDENCIA_TIC_URL,
    default_year: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Extrai individualmente cada edital da tabela 'Editais e oportunidades' do Ocean UnB no portal HUB."""
    soup = BeautifulSoup(html or "", "html.parser")
    core = soup.find("div", id="content-core") or soup.find("main") or soup
    fallback_yr = default_year or _current_year()
    items: List[Dict[str, Any]] = []

    header_map: Dict[str, int] = {}
    for tr in core.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        col_texts = [_clean_text(c.get_text(" ", strip=True)) for c in cells]
        col_title = col_texts[0]
        if not col_title:
            continue
        if col_title.lower() in ("editais", "edital", "título", "titulo"):
            for idx, hdr in enumerate(col_texts):
                h_low = hdr.lower()
                if "situa" in h_low or "status" in h_low:
                    header_map["situacao"] = idx
                elif "per" in h_low or "inscri" in h_low or "prazo" in h_low or "data" in h_low:
                    header_map["periodo"] = idx
            continue

        if "situacao" in header_map or "periodo" in header_map:
            sit_idx = header_map.get("situacao", -1)
            per_idx = header_map.get("periodo", -1)
            col_situacao = col_texts[sit_idx] if 0 <= sit_idx < len(col_texts) else ""
            col_periodo = col_texts[per_idx] if 0 <= per_idx < len(col_texts) else ""
        else:
            c1 = col_texts[1] if len(col_texts) >= 2 else ""
            c2 = col_texts[2] if len(col_texts) >= 3 else ""
            if re.search(r"\d{1,2}/\d{1,2}", c1) and not re.search(r"\d{1,2}/\d{1,2}", c2):
                col_periodo, col_situacao = c1, c2
            else:
                col_situacao, col_periodo = c1, c2

        a_tag = cells[0].find("a", href=True) or tr.find("a", href=True)
        row_href = urljoin(page_url, str(a_tag["href"]).strip()) if a_tag else ""
        if not row_href:
            slug = re.sub(r"[^a-z0-9]+", "-", col_title.lower()).strip("-")[:60]
            row_href = f"{page_url.rstrip('/')}#{slug}"

        m_yr = (
            EDITAL_YEAR_PATTERN.search(col_title)
            or GENERAL_YEAR_PATTERN.search(col_periodo)
            or GENERAL_YEAR_PATTERN.search(col_title)
            or GENERAL_YEAR_PATTERN.search(row_href)
        )
        ano = int(m_yr.group(1)) if m_yr else fallback_yr

        periodo_norm = col_periodo
        if periodo_norm and re.search(r"20\d{2}", periodo_norm) is None:
            periodo_norm = f"{periodo_norm}/{ano}"
        dt_ini, dt_fim = parse_data_interval(periodo_norm, default_year=ano)
        inicio_iso = dt_ini.date().isoformat() if dt_ini else None
        fim_iso = dt_fim.date().isoformat() if dt_fim else None
        data_pub = _normalize_date_str(
            f"{dt_ini.day:02d}/{dt_ini.month:02d}/{dt_ini.year}" if dt_ini else col_periodo,
            default_year=ano,
        )

        sit_lower = col_situacao.lower()
        if any(w in sit_lower for w in ("encerrad", "fechad", "conclu", "finaliz")):
            status = "fechado"
        elif any(w in sit_lower for w in ("abert", "andamento", "inscri")):
            status = "aberto"
        elif dt_fim and dt_fim.date() < datetime.now(timezone.utc).date():
            status = "fechado"
        else:
            status = "aberto"

        titulo = col_title if "hub" in col_title.lower() or "ocean" in col_title.lower() else f"{col_title} — Ocean UnB / HUB-UnB"
        cat_info = classify_hub_edital(titulo, url=page_url, texto=col_title)
        descricao_parts = [
            f"{titulo}.",
            "Chamada oficial vinculada ao Projeto de Residência Tecnológica em Saúde Digital / TIC 53 (parceria HUB-UnB, PCTec/UnB e Samsung Ocean UnB).",
        ]
        if col_situacao:
            descricao_parts.append(f"Situação no portal HUB-UnB: {col_situacao}.")
        if col_periodo:
            descricao_parts.append(f"Período de inscrições: {col_periodo}.")
        descricao = " ".join(descricao_parts)

        items.append({
            "titulo": titulo,
            "assunto": f"HUB-UnB / Ocean UnB ({cat_info['programa']}) — {titulo}",
            "tipo": cat_info["tipo"],
            "tipo_edital": cat_info["tipo_edital"],
            "programa": cat_info["programa"],
            "descricao": descricao,
            "resumo": descricao,
            "unidade": "HUB-UnB / Ocean UnB",
            "campus": "Darcy Ribeiro",
            "link": row_href,
            "link_inscricao": row_href,
            "data_publicacao": data_pub,
            "inicio_inscricao": inicio_iso,
            "fim_inscricao": fim_iso,
            "status": status,
            "ano": ano,
            "documentos": [],
        })

    return items


def parse_hub_page_as_edital(
    html: str,
    page_url: str,
    override_title: str = "",
    extra_docs: Optional[Sequence[Dict[str, Any]]] = None,
    default_year: Optional[int] = None,
) -> Dict[str, Any]:
    """Converte uma página de edital/seleção do HUB-UnB em dicionário padronizado do projeto."""
    soup = BeautifulSoup(html or "", "html.parser")
    core = (
        soup.find("div", id="content-core")
        or soup.find("article")
        or soup.find("main")
        or soup
    )

    h1 = (
        soup.find("h1", class_="documentFirstHeading")
        or core.find(["h1", "h2"])
        or soup.find("h1")
    )
    extracted_title = _clean_text(h1.get_text(" ", strip=True)) if h1 else ""
    titulo = override_title or extracted_title or "Edital HUB-UnB"

    # Enriquece títulos curtos/genéricos (ex: "2026", "Transferência", "Rede HU+")
    if len(titulo) <= 16 or titulo.isdigit():
        if "/concursos/" in page_url and titulo.isdigit():
            titulo = f"Concurso Público Nacional Ebserh/HUB-UnB — Edição {titulo}"
        elif "cursos/transferencia" in page_url:
            titulo = "Edital/Normas de Transferência — Residência Multiprofissional em Saúde (COREMU/HUB-UnB)"
        elif "cursos-1/transferencia" in page_url:
            titulo = "Edital/Normas de Transferência — Residência Médica (COREME/HUB-UnB)"
        elif "rede-hu" in page_url and "hub" not in titulo.lower():
            titulo = f"Chamada Pública HUB-UnB — {titulo} (CAPES/Ebserh/SECTICS)"
    elif "hub" not in titulo.lower() and "ebserh" not in titulo.lower() and "enare" not in titulo.lower():
        titulo = f"{titulo} — HUB-UnB"

    # Extração de data de publicação/modificação Plone
    raw_date = ""
    doc_date_node = soup.find(class_="documentPublished") or soup.find(class_="documentModified")
    if doc_date_node:
        raw_date = _clean_text(doc_date_node.get_text(" ", strip=True))

    docs = extract_docs_from_govbr_html(html, page_url)
    seen_doc_urls = {d["link"] for d in docs}
    for extra in extra_docs or []:
        if extra.get("link") and extra["link"] not in seen_doc_urls:
            seen_doc_urls.add(extra["link"])
            docs.append(extra)

    # Descrição limpa do corpo da página (preservando informações de bolsas, vigência, público-alvo e prazos)
    paragraphs: List[str] = []
    for p in core.find_all(["p", "li"]):
        txt = _clean_text(p.get_text(" ", strip=True))
        if len(txt) < 25:
            continue
        if any(
            skip in txt.lower()
            for skip in [
                "aguarde. carregando conteúdo da aba",
                "seu navegador não pode executar javascript",
                "formato, pdf",
            ]
        ):
            continue
        if txt not in paragraphs:
            paragraphs.append(txt)
            if len(paragraphs) >= 6:
                break

    body_text = _clean_text(core.get_text(" ", strip=True))
    if not raw_date:
        m_d = DATE_SLASH_PATTERN.search(body_text) or DATE_PT_PATTERN.search(body_text)
        if m_d:
            raw_date = m_d.group(1)

    current_yr = _current_year()
    # Determinação do ano de referência
    ano: Optional[int] = default_year
    if ano is None:
        m_yr = (
            EDITAL_YEAR_PATTERN.search(titulo)
            or GENERAL_YEAR_PATTERN.search(titulo)
            or GENERAL_YEAR_PATTERN.search(page_url)
            or GENERAL_YEAR_PATTERN.search(raw_date)
        )
        if m_yr:
            ano = int(m_yr.group(1))
    if ano is None:
        ano = current_yr

    link_inscricao, inicio_inscricao, fim_inscricao = _extract_hub_registration_metadata(
        core=core,
        body_text=body_text,
        page_url=page_url,
        default_year=ano,
    )

    data_publicacao = _normalize_date_str(raw_date, default_year=ano)
    cat_info = classify_hub_edital(titulo, url=page_url, texto=body_text[:600])

    has_final_doc = any(d.get("tipo") == "resultado_final" for d in docs)
    is_continuous = (
        "transferencia" in page_url
        or "/graduacao/extensao" in page_url
        or "fluxo contínuo" in body_text.lower()
        or "fluxo continuo" in body_text.lower()
        or "fluxo contínuo" in titulo.lower()
    )
    today_iso = datetime.now(timezone.utc).date().isoformat()
    if is_continuous:
        status = "aberto"
    elif has_final_doc or ano < (current_yr - 1):
        status = "fechado"
    elif fim_inscricao and fim_inscricao < today_iso and "/pesquisa/editais/" not in page_url:
        status = "fechado"
    else:
        status = "aberto"

    descricao = (
        " ".join(paragraphs[:5]).strip()
        or f"Edital e documentação oficial do Hospital Universitário de Brasília (HUB-UnB/Ebserh) no âmbito de {cat_info['programa']}: {titulo}."
    )
    resumo = (
        " ".join(paragraphs[:2]).strip()
        or descricao
    )
    assunto = f"HUB-UnB / Ebserh ({cat_info['programa']}) — {titulo}"

    return {
        "titulo": titulo,
        "assunto": assunto,
        "tipo": cat_info["tipo"],
        "tipo_edital": cat_info["tipo_edital"],
        "programa": cat_info["programa"],
        "descricao": descricao,
        "resumo": resumo[:1000],
        "unidade": "HUB-UnB",
        "campus": "Darcy Ribeiro",
        "link": page_url,
        "link_inscricao": link_inscricao or page_url,
        "data_publicacao": data_publicacao,
        "inicio_inscricao": inicio_inscricao,
        "fim_inscricao": fim_inscricao,
        "status": status,
        "ano": ano,
        "documentos": docs,
    }


def extract_subpage_links(
    html: str,
    base_url: str,
    path_must_contain: str = "",
) -> List[Tuple[str, str]]:
    """Extrai pares (título, url) de links internos contidos em #content-core."""
    soup = BeautifulSoup(html or "", "html.parser")
    core = soup.find("div", id="content-core") or soup.find("main") or soup
    results: List[Tuple[str, str]] = []
    seen = set()

    for a in core.find_all("a", href=True):
        raw_href = str(a["href"]).strip()
        if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:")):
            continue
        full = urljoin(base_url, raw_href).rstrip("/")
        if is_document_url(full):
            continue
        if path_must_contain and path_must_contain not in full:
            continue
        if full == base_url.rstrip("/") or full in seen:
            continue
        title = _clean_text(a.get_text(" ", strip=True))
        if not title:
            continue
        seen.add(full)
        results.append((title, full))

    return results


def extract_enare_fgv_publicacoes(
    html: str,
    base_url: str = FGV_ENARE_2026_BASE_URL,
) -> List[Dict[str, Any]]:
    """Extrai publicações e PDFs oficiais do portal ENARE/FGV (payload RSC Next.js ou links HTML)."""
    if not html:
        return []

    results: List[Dict[str, Any]] = []
    seen_links = set()

    chunks: List[str] = []
    for match in re.finditer(r'self\.__next_f\.push\(\[1,("(?:\\.|[^"\\])*")\]\)', html):
        try:
            chunks.append(json.loads(match.group(1)))
        except (ValueError, TypeError):
            continue

    if chunks:
        full_rsc = "".join(chunks)
        marker = '"publicacoes":['
        idx = full_rsc.find(marker)
        if idx != -1:
            try:
                decoder = json.JSONDecoder()
                raw_pubs, _ = decoder.raw_decode(full_rsc[idx + len('"publicacoes":'):])
                if isinstance(raw_pubs, list):
                    for pub in raw_pubs:
                        if not isinstance(pub, dict):
                            continue
                        raw_url = str(pub.get("urlDocumento") or "").strip()
                        if not raw_url:
                            continue
                        doc_url = urljoin(base_url, raw_url)
                        if not is_document_url(doc_url) or doc_url in seen_links:
                            continue
                        seen_links.add(doc_url)

                        doc_title = _clean_text(str(pub.get("titulo") or "")) or "Documento Oficial ENARE"
                        tipo_raw = str(pub.get("tipoDocumento") or "").lower()
                        if tipo_raw == "retificacao":
                            doc_type = "retificacao"
                        elif tipo_raw == "edital" and "retifica" not in doc_title.lower():
                            doc_type = "original"
                        else:
                            doc_type = classify_hub_document(doc_title, doc_url)

                        dests = pub.get("destinatarios")
                        dest_list = [str(d) for d in dests] if isinstance(dests, list) else []
                        results.append({
                            "titulo": doc_title,
                            "link": doc_url,
                            "tipo": doc_type,
                            "data_publicacao": str(pub.get("dataPublicacao") or ""),
                            "tipo_origem": tipo_raw,
                            "destinatarios": dest_list,
                        })
            except (ValueError, TypeError):
                pass

    if not results:
        for doc in extract_docs_from_govbr_html(html, base_url):
            results.append({
                **doc,
                "data_publicacao": "",
                "tipo_origem": "edital",
                "destinatarios": [],
            })

    return results


class HUBScraper(BaseScraper):
    """Implementação do scraper para o Hospital Universitário de Brasília (HUB-UnB / Ebserh)."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        cache_ttl_seconds: float = CACHE_TTL_SECONDS,
    ) -> None:
        self.timeout = timeout
        self.cache_ttl_seconds = cache_ttl_seconds
        self._url_to_docs_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._cache_timestamps: Dict[str, float] = {}

    def _cache_put(self, url: str, docs: List[Dict[str, Any]]) -> None:
        self._url_to_docs_cache[url] = list(docs)
        self._cache_timestamps[url] = time.monotonic()

    def _cache_get(self, url: str) -> Optional[List[Dict[str, Any]]]:
        if url not in self._url_to_docs_cache:
            return None
        ts = self._cache_timestamps.get(url)
        if ts is not None and (time.monotonic() - ts) > self.cache_ttl_seconds:
            self._url_to_docs_cache.pop(url, None)
            self._cache_timestamps.pop(url, None)
            return None
        return self._url_to_docs_cache[url]

    @property
    def orgao_origem(self) -> str:
        """Identificador institucional do órgão."""
        return "HUB"

    def _safe_get(self, client: httpx.Client, url: str) -> Optional[httpx.Response]:
        """Executa GET resiliente com 1 nova tentativa em caso de timeout transitório."""
        for attempt in range(2):
            try:
                resp = client.get(url)
                if resp.status_code == 200:
                    return resp
                return None
            except httpx.TimeoutException as exc:
                if attempt == 0:
                    continue
                logger.warning(f"Timeout ao consultar página do HUB-UnB ({url}): {exc}")
            except httpx.HTTPError as exc:
                logger.warning(f"Falha ao consultar página do HUB-UnB ({url}): {exc}")
                return None
        return None

    def _collect_subfolder_docs(
        self,
        client: httpx.Client,
        parent_html: str,
        parent_url: str,
        allowed_slugs: Sequence[str] = PSS_DOC_SUBFOLDER_SLUGS,
    ) -> List[Dict[str, Any]]:
        """Coleta PDFs dentro de subpastas Plone de um PSS ou Concurso (edital-normativo, resultado, etc.)."""
        soup = BeautifulSoup(parent_html or "", "html.parser")
        core = soup.find("div", id="content-core") or soup
        sub_urls: List[str] = []
        seen = set()

        for a in core.find_all("a", href=True):
            full = urljoin(parent_url, str(a["href"]).strip()).rstrip("/")
            slug = urlparse(full).path.rstrip("/").split("/")[-1].lower()
            if slug in allowed_slugs and full not in seen:
                seen.add(full)
                sub_urls.append(full)

        all_docs: List[Dict[str, Any]] = []
        seen_docs = set()
        for sub_u in sub_urls:
            resp = self._safe_get(client, sub_u)
            if not resp:
                continue
            for doc in extract_docs_from_govbr_html(resp.text, str(resp.url)):
                if doc["link"] not in seen_docs:
                    seen_docs.add(doc["link"])
                    all_docs.append(doc)
        return all_docs

    def _discover_edition_pages(
        self,
        client: httpx.Client,
        index_url: str,
        path_prefix: str,
    ) -> List[Tuple[str, str]]:
        """Descobre subpáginas de edições anuais (resolvendo abas Plone data-url quando presentes)."""
        resp = self._safe_get(client, index_url)
        if not resp:
            return []

        pages: List[Tuple[str, str]] = []
        seen = set()

        for title, link in extract_subpage_links(resp.text, str(resp.url), path_must_contain=path_prefix):
            if link not in seen:
                seen.add(link)
                pages.append((title, link))

        for tab_url in extract_plone_tab_urls(resp.text, str(resp.url)):
            tab_resp = self._safe_get(client, tab_url)
            if not tab_resp:
                continue
            for title, link in extract_subpage_links(tab_resp.text, str(tab_resp.url), path_must_contain=path_prefix):
                if link not in seen:
                    seen.add(link)
                    pages.append((title, link))

        return pages

    def fetch_editais(
        self,
        year: Optional[int] = None,
        max_pss_years: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Coleta todos os editais do HUB-UnB (Residências/ENARE, PIC, PIT, Pesquisa, PSS e Concursos).

        Args:
            year: Filtro opcional por ano de referência (ex: 2026, 2025).
            max_pss_years: Limite opcional de anos de PSS/Concursos a percorrer (útil em testes rápidos ao vivo).

        Returns:
            Lista padronizada de editais do HUB-UnB.
        """
        current_yr = _current_year()
        # Limpa cache em memória a cada ciclo periódico para garantir atualização de documentos
        self._url_to_docs_cache.clear()
        self._cache_timestamps.clear()

        editais: List[Dict[str, Any]] = []
        seen_links = set()

        def _register(item: Optional[Dict[str, Any]]) -> None:
            if not item or not item.get("link"):
                return
            self._cache_put(item["link"], item.get("documentos", []))
            if year is not None and item.get("ano") != year:
                return
            if item["link"] not in seen_links:
                seen_links.add(item["link"])
                editais.append(item)

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                candidate_targets: List[Tuple[str, str, Optional[int], bool]] = []
                # Tupla: (override_title, url, default_year, inspect_pss_subfolders)

                # 1. PIC e PIT (Iniciação Científica e Tecnológica no HUB-UnB)
                for title, link in self._discover_edition_pages(client, HUB_PIC_INDEX_URL, "/pic-ebserh/"):
                    if link.rstrip("/").endswith("/pic-ebserh/pic-ebserh"):
                        continue
                    pic_prefix = (
                        "Programa de Iniciação Científica — "
                        if "hub" in title.lower()
                        else "Programa de Iniciação Científica HUB-UnB — "
                    )
                    candidate_targets.append((f"{pic_prefix}{title}", link, None, False))

                for title, link in self._discover_edition_pages(
                    client,
                    HUB_PIT_INDEX_URL,
                    "/programa-de-iniciacao-tecnologica-pit-ebserh-hub-unb/",
                ):
                    pit_prefix = (
                        "Programa de Iniciação Tecnológica — "
                        if "hub" in title.lower()
                        else "Programa de Iniciação Tecnológica HUB-UnB — "
                    )
                    candidate_targets.append((f"{pit_prefix}{title}", link, None, False))

                # 2. Residência Médica (COREME) e Multiprofissional (COREMU) — ENARE (FGV + Gov.br) + Transferências
                fgv_normative_docs: List[Dict[str, Any]] = []
                fgv_candidate_years = [year] if year is not None else [current_yr, current_yr - 1]
                for enare_yr in fgv_candidate_years:
                    fgv_pub_url = f"https://enare{enare_yr}.conhecimento.fgv.br/publicacoes/"
                    fgv_resp = self._safe_get(client, fgv_pub_url)
                    if not fgv_resp:
                        continue
                    fgv_pubs = extract_enare_fgv_publicacoes(fgv_resp.text, base_url=str(fgv_resp.url))
                    med_docs = [
                        {"titulo": p["titulo"], "link": p["link"], "tipo": p["tipo"]}
                        for p in fgv_pubs
                        if any(d in p.get("destinatarios", []) for d in ("medica-acesso-direto", "medica-pre-requisito"))
                    ]
                    multi_docs = [
                        {"titulo": p["titulo"], "link": p["link"], "tipo": p["tipo"]}
                        for p in fgv_pubs
                        if "multi-uniprofissional" in p.get("destinatarios", [])
                    ]
                    fgv_normative_docs = [
                        {"titulo": p["titulo"], "link": p["link"], "tipo": p["tipo"]}
                        for p in fgv_pubs
                        if p.get("tipo_origem") in ("edital", "retificacao")
                    ]
                    latest_med_dt = next(
                        (p["data_publicacao"] for p in fgv_pubs if p.get("data_publicacao")),
                        f"{enare_yr}-06-03",
                    )
                    med_final = any(d["tipo"] == "resultado_final" for d in med_docs)
                    multi_final = any(d["tipo"] == "resultado_final" for d in multi_docs)
                    if med_docs:
                        _register({
                            "titulo": f"Residência Médica (COREME / ENARE {enare_yr}) — Seleção Unificada HUB-UnB",
                            "assunto": f"HUB-UnB / Ebserh (Residência Médica HUB-UnB — COREME / ENARE {enare_yr})",
                            "tipo": "Residência Médica (COREME)",
                            "tipo_edital": "Saúde / Residência Médica COREME",
                            "programa": "Residência Médica HUB-UnB (COREME / ENARE)",
                            "descricao": (
                                f"Processo seletivo unificado do Exame Nacional de Residência (ENARE {enare_yr} / FGV / HU Brasil) "
                                "para ingresso nos programas de Residência Médica (Acesso Direto e Pré-Requisito — COREME) "
                                "do Hospital Universitário de Brasília (HUB-UnB)."
                            ),
                            "resumo": (
                                f"Processo seletivo unificado do Exame Nacional de Residência (ENARE {enare_yr} / FGV / HU Brasil) "
                                "para ingresso nos programas de Residência Médica (Acesso Direto e Pré-Requisito — COREME) "
                                "do Hospital Universitário de Brasília (HUB-UnB)."
                            ),
                            "unidade": "HUB-UnB",
                            "campus": "Darcy Ribeiro",
                            "link": f"{fgv_pub_url}#residencia-medica",
                            "link_inscricao": fgv_pub_url,
                            "data_publicacao": _normalize_date_str(latest_med_dt, default_year=enare_yr),
                            "status": "fechado" if (med_final or enare_yr < current_yr) else "aberto",
                            "ano": enare_yr,
                            "documentos": med_docs,
                        })
                    if multi_docs:
                        _register({
                            "titulo": (
                                f"Residência Multiprofissional e em Área Profissional da Saúde "
                                f"(COREMU / ENARE {enare_yr}) — Seleção Unificada HUB-UnB"
                            ),
                            "assunto": f"HUB-UnB / Ebserh (Residência Multiprofissional HUB-UnB — COREMU / ENARE {enare_yr})",
                            "tipo": "Residência Multiprofissional em Saúde (COREMU)",
                            "tipo_edital": "Saúde / Residência Multiprofissional COREMU",
                            "programa": "Residência Multiprofissional HUB-UnB (COREMU / ENARE)",
                            "descricao": (
                                f"Processo seletivo unificado do Exame Nacional de Residência (ENARE {enare_yr} / FGV / HU Brasil) "
                                "para ingresso nos programas de Residência Multiprofissional e Uniprofissional em Saúde "
                                "(COREMU) do Hospital Universitário de Brasília (HUB-UnB)."
                            ),
                            "resumo": (
                                f"Processo seletivo unificado do Exame Nacional de Residência (ENARE {enare_yr} / FGV / HU Brasil) "
                                "para ingresso nos programas de Residência Multiprofissional e Uniprofissional em Saúde "
                                "(COREMU) do Hospital Universitário de Brasília (HUB-UnB)."
                            ),
                            "unidade": "HUB-UnB",
                            "campus": "Darcy Ribeiro",
                            "link": f"{fgv_pub_url}#residencia-multiprofissional",
                            "link_inscricao": fgv_pub_url,
                            "data_publicacao": _normalize_date_str(latest_med_dt, default_year=enare_yr),
                            "status": "fechado" if (multi_final or enare_yr < current_yr) else "aberto",
                            "ano": enare_yr,
                            "documentos": multi_docs,
                        })
                    if med_docs or multi_docs:
                        break

                enare_resp = self._safe_get(client, HUB_ENARE_URL)
                if enare_resp:
                    enare_item = parse_hub_page_as_edital(
                        enare_resp.text,
                        str(enare_resp.url),
                        override_title="Exame Nacional de Residência (ENARE / HUB-UnB — COREME e COREMU)",
                        extra_docs=fgv_normative_docs,
                        default_year=current_yr,
                    )
                    _register(enare_item)

                enare_ant_resp = self._safe_get(client, HUB_ENARE_ANTERIORES_URL)
                if enare_ant_resp:
                    for ed_title, ed_url in extract_subpage_links(
                        enare_ant_resp.text,
                        str(enare_ant_resp.url),
                        path_must_contain="/edicoes-anteriores/",
                    ):
                        m_yr = GENERAL_YEAR_PATTERN.search(ed_title)
                        ed_yr = int(m_yr.group(1)) if m_yr else None
                        if year is not None and ed_yr is not None and ed_yr != year:
                            continue
                        candidate_targets.append(
                            (
                                f"Exame Nacional de Residência ENARE ({ed_title}) — Vagas HUB-UnB",
                                ed_url,
                                ed_yr,
                                max_pss_years is None,
                            )
                        )

                candidate_targets.append(
                    (
                        "Edital/Normas de Transferência — Residência Multiprofissional em Saúde (COREMU/HUB-UnB)",
                        HUB_COREMU_TRANSFERENCIA_URL,
                        current_yr,
                        False,
                    )
                )
                candidate_targets.append(
                    (
                        "Edital/Normas de Transferência — Residência Médica (COREME/HUB-UnB)",
                        HUB_COREME_TRANSFERENCIA_URL,
                        current_yr,
                        False,
                    )
                )
                candidate_targets.append(
                    (
                        "Fluxo Contínuo de Submissão — Atividades e Projetos de Extensão Universitária no HUB-UnB",
                        HUB_EXTENSAO_URL,
                        current_yr,
                        False,
                    )
                )

                # 3. Pesquisa, Inovação e Saúde Digital no HUB-UnB:
                #    Coleta integral de todas as subpáginas de `pesquisa/editais`
                #    (Concurso de Inovação em Saúde Digital, Rede HU+, CNPq, Mulheres na Ciência,
                #    FAP/DF, FINEP, CAPES, Editais CDT-UnB, PROADI-SUS, Financiamento Internacional e NIH)
                pesq_resp = self._safe_get(client, HUB_PESQUISA_EDITAIS_URL)
                if pesq_resp:
                    for p_title, p_url in extract_subpage_links(
                        pesq_resp.text,
                        str(pesq_resp.url),
                        path_must_contain="/pesquisa/editais/",
                    ):
                        title_label = p_title if "hub" in p_title.lower() else f"{p_title} — Editais e Fomento HUB-UnB"
                        candidate_targets.append((title_label, p_url, None, False))

                # 3b. Jornada Científica do HUB-UnB (edição mais recente / edições com normas e submissão)
                jornada_pages = self._discover_edition_pages(
                    client,
                    HUB_JORNADA_CIENTIFICA_URL,
                    "/jornanda-cientifica/",
                )
                for j_title, j_url in jornada_pages:
                    if j_url.rstrip("/").endswith("jornada-cientifica-do-hub-1"):
                        continue
                    # Prioriza as edições mais recentes da Jornada Científica (evita sobrecarregar dezenas de anos antigos)
                    if max_pss_years is not None and j_url != jornada_pages[-1][1]:
                        continue
                    if j_url in [p[1] for p in jornada_pages[-2:]]:
                        candidate_targets.append((f"{j_title} — HUB-UnB", j_url, None, False))

                # 3c. Ocean UnB (Projeto Residência em TIC 53) — Aba "Editais e oportunidades" + Residência OceanBrasil
                ocean_res_docs: List[Dict[str, Any]] = []
                ocean_res_resp = self._safe_get(client, OCEAN_RESIDENCIA_URL)
                if ocean_res_resp:
                    ocean_res_docs = extract_ocean_residencia_unb_docs(
                        ocean_res_resp.text,
                        base_url=str(ocean_res_resp.url),
                    )

                tic_resp = self._safe_get(client, HUB_RESIDENCIA_TIC_URL)
                if tic_resp:
                    tic_page_docs = extract_docs_from_govbr_html(tic_resp.text, str(tic_resp.url))
                    table_items = parse_ocean_unb_oportunidades_table(
                        tic_resp.text,
                        page_url=str(tic_resp.url),
                        default_year=current_yr,
                    )
                    if table_items:
                        for row_item in table_items:
                            row_docs: List[Dict[str, Any]] = list(tic_page_docs)
                            seen_row_docs = {d["link"] for d in row_docs}
                            # Busca PDFs oficiais na página de destino (ex.: pctec.unb.br/edital-...)
                            if row_item["link"] and not row_item["link"].startswith(HUB_RESIDENCIA_TIC_URL):
                                ext_resp = self._safe_get(client, row_item["link"])
                                if ext_resp:
                                    for d in extract_docs_from_govbr_html(ext_resp.text, str(ext_resp.url)):
                                        if d["link"] not in seen_row_docs:
                                            seen_row_docs.add(d["link"])
                                            row_docs.append(d)
                            # Anexa PDFs UnB/DF hospedados em residencia.oceanbrasil.com ao edital de Residência Ocean UnB
                            if "ocean" in row_item["titulo"].lower() or "saúde digital" in row_item["titulo"].lower():
                                for od in ocean_res_docs:
                                    if od["link"] not in seen_row_docs:
                                        seen_row_docs.add(od["link"])
                                        row_docs.append(od)
                            row_item["documentos"] = row_docs
                            if any(d.get("tipo") == "resultado_final" for d in row_docs):
                                row_item["status"] = "fechado"
                            _register(row_item)
                    else:
                        tic_item = parse_hub_page_as_edital(
                            tic_resp.text,
                            str(tic_resp.url),
                            override_title="Editais e Oportunidades — Residência Tecnológica em Saúde Digital (HUB-UnB / Ocean UnB)",
                            extra_docs=[*tic_page_docs, *ocean_res_docs],
                            default_year=current_yr,
                        )
                        _register(tic_item)

                # 4. Processos Seletivos Simplificados (PSS) filtrados exclusivamente para HUB-UnB / Nacional / Sede
                dynamic_pss_years = _build_pss_years(current_yr)
                pss_years_to_check = (
                    (year,)
                    if year is not None and year in dynamic_pss_years
                    else dynamic_pss_years[:max_pss_years] if max_pss_years is not None else dynamic_pss_years
                )
                for pss_yr in pss_years_to_check:
                    pss_list_url = f"{HUB_PSS_BASE_URL}/{pss_yr}"
                    pss_resp = self._safe_get(client, pss_list_url)
                    if not pss_resp:
                        continue
                    for pss_title, pss_url in extract_subpage_links(
                        pss_resp.text,
                        str(pss_resp.url),
                        path_must_contain=f"/processo-seletivo-simplificado-pss/{pss_yr}/",
                    ):
                        if is_hub_relevant_pss(pss_title, pss_url):
                            candidate_targets.append((pss_title, pss_url, pss_yr, True))

                # 5. Concursos Públicos Nacionais Ebserh (vagas efetivas para o HUB-UnB, excluindo outros HUs isolados)
                dynamic_conc_years = _build_concursos_years(current_yr)
                conc_years_to_check = (
                    (year,)
                    if year is not None and year in dynamic_conc_years
                    else dynamic_conc_years[:max_pss_years] if max_pss_years is not None else dynamic_conc_years
                )
                for conc_yr in conc_years_to_check:
                    conc_url = f"{HUB_CONCURSOS_ANUAIS_BASE_URL}/{conc_yr}"
                    conc_resp = self._safe_get(client, conc_url)
                    if not conc_resp:
                        continue
                    sub_links = extract_subpage_links(
                        conc_resp.text,
                        str(conc_resp.url),
                        path_must_contain=f"/concursos/{conc_yr}/",
                    )
                    has_direct_normative_folder = any(
                        urlparse(su).path.rstrip("/").split("/")[-1].lower() in PSS_LISTING_SUBFOLDER_SLUGS
                        for _, su in sub_links
                    )
                    if has_direct_normative_folder or extract_docs_from_govbr_html(conc_resp.text, str(conc_resp.url)):
                        candidate_targets.append(
                            (
                                f"Concurso Público Nacional Ebserh/HUB-UnB — Edição {conc_yr}",
                                conc_url,
                                conc_yr,
                                True,
                            )
                        )
                    else:
                        for c_title, c_sub_url in sub_links:
                            if is_hub_relevant_pss(c_title, c_sub_url):
                                candidate_targets.append(
                                    (
                                        f"{c_title} — Vagas HUB-UnB",
                                        c_sub_url,
                                        conc_yr,
                                        True,
                                    )
                                )

                # 6. Programa de Estágio Ebserh/HUB-UnB (abas data-url)
                if max_pss_years is None:
                    est_resp = self._safe_get(client, HUB_ESTAGIOS_URL)
                    if est_resp:
                        for tab_u in extract_plone_tab_urls(est_resp.text, str(est_resp.url)):
                            if "quadro-de-estagiarios" in tab_u:
                                continue
                            m_yr = GENERAL_YEAR_PATTERN.search(tab_u)
                            est_yr = int(m_yr.group(1)) if m_yr else None
                            if year is not None and est_yr is not None and est_yr != year:
                                continue
                            slug_label = tab_u.rstrip("/").split("/")[-1].replace("-", " ").title()
                            candidate_targets.append(
                                (f"Programa de Estágio Ebserh/HUB-UnB — {slug_label}", tab_u, est_yr, False)
                            )

                # Executa a coleta das páginas-alvo com paralelismo controlado (2 workers para respeitar o WAF do Gov.br)
                def _fetch_target(target: Tuple[str, str, Optional[int], bool]) -> Optional[Dict[str, Any]]:
                    ov_title, target_url, def_yr, check_subfolders = target
                    r = self._safe_get(client, target_url)
                    if not r:
                        # Se o item já foi confirmado na listagem oficial de PSS mas a subpágina sofreu timeout transitório
                        if "/processo-seletivo-simplificado-pss/" in target_url and ov_title:
                            return parse_hub_page_as_edital(
                                "",
                                target_url,
                                override_title=ov_title,
                                default_year=def_yr,
                            )
                        return None
                    extra_docs: List[Dict[str, Any]] = []
                    if check_subfolders:
                        extra_docs.extend(
                            self._collect_subfolder_docs(
                                client,
                                r.text,
                                str(r.url),
                                allowed_slugs=PSS_LISTING_SUBFOLDER_SLUGS,
                            )
                        )
                    # Resolve também abas data-url caso a página individual possua abas internas
                    for inner_tab in extract_plone_tab_urls(r.text, str(r.url)):
                        tab_r = self._safe_get(client, inner_tab)
                        if tab_r:
                            extra_docs.extend(extract_docs_from_govbr_html(tab_r.text, str(tab_r.url)))
                    return parse_hub_page_as_edital(
                        r.text,
                        str(r.url),
                        override_title=ov_title,
                        extra_docs=extra_docs,
                        default_year=def_yr,
                    )

                with ThreadPoolExecutor(max_workers=2) as pool:
                    fetched_items = list(pool.map(_fetch_target, candidate_targets))

                for item in fetched_items:
                    _register(item)

        except Exception as exc:
            logger.error(f"Erro geral no scraper do HUB-UnB: {exc}")
            return editais

        return editais

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai todos os documentos oficiais (.pdf, .docx) vinculados a um edital do HUB-UnB."""
        if not edital_url:
            return []

        cached = self._cache_get(edital_url)
        if cached is not None:
            return cached

        if is_document_url(edital_url):
            clean_url = normalize_govbr_doc_url(edital_url)
            return [{
                "titulo": "Documento Oficial HUB-UnB",
                "link": clean_url,
                "tipo": classify_hub_document(clean_url, clean_url),
            }]

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                verify=False,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                base_target_url = edital_url.split("#", 1)[0]
                fragment = edital_url.split("#", 1)[1].lower() if "#" in edital_url else ""
                resp = self._safe_get(client, base_target_url)
                if not resp:
                    return []
                if "conhecimento.fgv.br" in base_target_url:
                    fgv_pubs = extract_enare_fgv_publicacoes(resp.text, base_url=str(resp.url))
                    if fragment == "residencia-medica":
                        docs = [
                            {"titulo": p["titulo"], "link": p["link"], "tipo": p["tipo"]}
                            for p in fgv_pubs
                            if any(d in p.get("destinatarios", []) for d in ("medica-acesso-direto", "medica-pre-requisito"))
                        ]
                    elif fragment == "residencia-multiprofissional":
                        docs = [
                            {"titulo": p["titulo"], "link": p["link"], "tipo": p["tipo"]}
                            for p in fgv_pubs
                            if "multi-uniprofissional" in p.get("destinatarios", [])
                        ]
                    else:
                        docs = [{"titulo": p["titulo"], "link": p["link"], "tipo": p["tipo"]} for p in fgv_pubs]
                    self._cache_put(edital_url, docs)
                    return docs

                docs = extract_docs_from_govbr_html(resp.text, str(resp.url))
                seen = {d["link"] for d in docs}
                for sub_doc in self._collect_subfolder_docs(client, resp.text, str(resp.url)):
                    if sub_doc["link"] not in seen:
                        seen.add(sub_doc["link"])
                        docs.append(sub_doc)
                for tab_url in extract_plone_tab_urls(resp.text, str(resp.url)):
                    tab_r = self._safe_get(client, tab_url)
                    if tab_r:
                        for tab_doc in extract_docs_from_govbr_html(tab_r.text, str(tab_r.url)):
                            if tab_doc["link"] not in seen:
                                seen.add(tab_doc["link"])
                                docs.append(tab_doc)
                self._cache_put(edital_url, docs)
                return docs
        except Exception as exc:
            logger.warning(f"Erro ao extrair documentos do HUB-UnB em {edital_url}: {exc}")
            return []


hub_scraper = HUBScraper()

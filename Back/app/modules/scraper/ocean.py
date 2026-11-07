"""Scraper para o Samsung Ocean Brasil — Unidade UnB / Brasília (Ocean UnB).

Coleta e categoriza todas as atividades mensais (cursos, oficinas, palestras,
jornadas, trilhas tecnológicas e eventos presenciais no PCTec/UnB ou online
ministrados pela equipe da UnB) e os editais de Residência Tecnológica em Saúde
Digital referentes à Universidade de Brasília (UnB), filtrando exclusivamente
a unidade de Brasília (UnB) e descartando atividades exclusivas da USP (São Paulo)
e da UEA (Manaus).

Fontes oficiais:
- API REST de Produção do Portal Samsung Ocean Brasil:
  - Agenda mensal por unidade: https://api.oceanbrasil.com/prod/schedule
  - Atividades ativas/próximas: https://api.oceanbrasil.com/prod/home/events
  - Detalhes e materiais de curso: https://api.oceanbrasil.com/prod/course/{id}
- Portal da Residência Tecnológica em Saúde Digital (Ocean UnB / HUB-UnB):
  - https://residencia.oceanbrasil.com/

Projetado para execução periódica contínua (janelas mensais dinâmicas baseadas
no relógio UTC atual e cache em memória com TTL curto sem vazamento de estado).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import html as html_lib
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

logger = logging.getLogger(__name__)

OCEAN_API_BASE_URL = "https://api.oceanbrasil.com/prod"
OCEAN_WEB_BASE_URL = "https://www.oceanbrasil.com"
OCEAN_RESIDENCIA_URL = "https://residencia.oceanbrasil.com/"
UNB_CAMPUS_QUERY = "Brasília"

DEFAULT_TIMEOUT = 20.0
CACHE_TTL_SECONDS = 300.0
RECENT_ENRICH_WINDOW_DAYS = 45

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Fique-de-Olho/1.0"
)

ACTIVITY_ID_FROM_URL_RE = re.compile(r"/atividades/(\d+)(?:[-/?#]|$)")
ISO_DATE_PREFIX_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")


def _utc_now() -> datetime:
    """Retorna o instante UTC atual (facilitando testes determinísticos e execução periódica)."""
    return datetime.now(timezone.utc)


def _strip_accents(value: str) -> str:
    """Remove acentos e normaliza para minúsculas."""
    normalized = unicodedata.normalize("NFD", value or "")
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").lower()


def _clean_text(raw: str) -> str:
    """Normaliza Unicode NFC, entidades HTML e espaços múltiplos."""
    if not raw:
        return ""
    unescaped = unicodedata.normalize("NFC", html_lib.unescape(str(raw)))
    return re.sub(r"\s+", " ", unescaped).strip()


def _clean_html_fragment(raw_html: Optional[str]) -> str:
    """Converte fragmentos HTML de descrição/ementa da API do Ocean em texto limpo."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(str(raw_html), "html.parser")
    return _clean_text(soup.get_text(" ", strip=True))


def slugify_ocean_title(title: str) -> str:
    """Gera slug compatível com as rotas `/atividades/{id}-{slug}` do portal OceanBrasil."""
    ascii_lower = _strip_accents(_clean_text(title))
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_lower).strip("-")
    return slug or "atividade-ocean-unb"


def build_ocean_activity_url(group_id: int, title: str) -> str:
    """Constrói a URL pública canônica de uma atividade no portal OceanBrasil."""
    return f"{OCEAN_WEB_BASE_URL}/atividades/{group_id}-{slugify_ocean_title(title)}"


def is_unb_ocean_campus(campus_value: Any) -> bool:
    """Verifica se o campus da atividade refere-se à unidade da UnB (Brasília / PCTec-UnB).

    Exclui explicitamente atividades exclusivas de São Paulo (USP), Campinas (UNICAMP)
    e Manaus (UEA).
    """
    if isinstance(campus_value, dict):
        raw = f"{campus_value.get('name', '')} {campus_value.get('address', '')}"
    else:
        raw = str(campus_value or "")
    norm = _strip_accents(raw)
    if not norm:
        return False
    return any(token in norm for token in ("brasilia", "unb", "pctec", "distrito federal"))


def _parse_iso_datetime(raw: Optional[str]) -> Optional[datetime]:
    """Converte timestamps ISO-8601 da API OceanBrasil em `datetime` UTC."""
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        m = ISO_DATE_PREFIX_RE.match(cleaned)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
            except ValueError:
                return None
        return None


def _format_ddmmyyyy(dt: Optional[datetime], fallback_year: int) -> str:
    """Formata `datetime` como `DD/MM/YYYY`."""
    if dt is None:
        return f"01/01/{fallback_year}"
    return f"{dt.day:02d}/{dt.month:02d}/{dt.year}"


def classify_ocean_activity(
    title: str,
    track_name: str = "",
    modality: str = "",
) -> Dict[str, str]:
    """Classifica uma atividade ou edital do Ocean UnB nas categorias do projeto."""
    combined = _strip_accents(f"{title} {track_name} {modality}")

    if "residencia" in combined:
        return {
            "tipo": "Residência Tecnológica em Saúde Digital",
            "tipo_edital": "Residência Tecnológica / Bolsa Ocean UnB",
            "programa": "Programa de Residência Tecnológica em Saúde Digital (Ocean UnB / HUB-UnB)",
        }

    if any(
        kw in combined
        for kw in ("ocean lab", "ocean launch", "demoday", "hackathon", "startup", "empreendedorismo", "inovacao")
    ):
        return {
            "tipo": "Inovação e Empreendedorismo Tecnológico",
            "tipo_edital": "Inovação / Capacitação Ocean UnB",
            "programa": f"Samsung Ocean UnB — {track_name or 'Inovação e Empreendedorismo'}",
        }

    if any(kw in combined for kw in ("digital health", "saude digital", "saude", "wearable", "hospital")):
        return {
            "tipo": "Extensão",
            "tipo_edital": "Extensão / Saúde Digital Ocean UnB",
            "programa": f"Samsung Ocean UnB — {track_name or 'Saúde Digital'}",
        }

    clean_track = _clean_text(track_name) or "Capacitação Tecnológica"
    return {
        "tipo": "Extensão",
        "tipo_edital": f"Extensão / Capacitação Ocean UnB ({clean_track})",
        "programa": f"Samsung Ocean UnB — Trilha {clean_track}",
    }


def build_monthly_schedule_dates(
    year: Optional[int] = None,
    reference_now: Optional[datetime] = None,
) -> List[str]:
    """Gera a lista de datas `YYYY-MM-01` para consulta mensal na API `/schedule`.

    - Se `year` for informado, consulta os 12 meses daquele ano.
    - Se `year` for `None` (sincronização periódica automática), consulta todos os
      12 meses do ano corrente, além de dezembro do ano anterior (em janeiro) e
      janeiro/fevereiro do ano seguinte (em novembro/dezembro) para cobrir viradas de ano.
    """
    now = reference_now or _utc_now()
    if year is not None:
        return [f"{year}-{month:02d}-01" for month in range(1, 13)]

    y = now.year
    dates: List[str] = []
    if now.month == 1:
        dates.append(f"{y - 1}-12-01")
    for month in range(1, 13):
        dates.append(f"{y}-{month:02d}-01")
    if now.month >= 11:
        dates.append(f"{y + 1}-01-01")
        dates.append(f"{y + 1}-02-01")
    return dates


def format_ocean_activity_as_edital(
    group_id: int,
    schedule_sessions: Sequence[Dict[str, Any]],
    home_summary: Optional[Dict[str, Any]] = None,
    course_detail: Optional[Dict[str, Any]] = None,
    reference_now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Consolida dados de `/schedule`, `/home/events` e `/course/{id}` no formato de edital."""
    now = reference_now or _utc_now()
    home = home_summary or {}
    detail = course_detail or {}

    # Verifica vínculo com UnB / Brasília quando há informação explícita de campus
    campus_candidates = [
        detail.get("campus"),
        home.get("campusName"),
        *(s.get("campusName") for s in schedule_sessions if s.get("campusName")),
    ]
    non_empty_campuses = [c for c in campus_candidates if c]
    if non_empty_campuses and not any(is_unb_ocean_campus(c) for c in non_empty_campuses):
        return None

    raw_title = (
        detail.get("title")
        or home.get("eventGroupTitle")
        or next((s.get("eventGroupTitle") for s in schedule_sessions if s.get("eventGroupTitle")), "")
        or next((s.get("title") for s in schedule_sessions if s.get("title")), "")
    )
    clean_title = _clean_text(raw_title)
    if not clean_title:
        return None

    track_name = _clean_text(
        detail.get("trackName")
        or home.get("trackTitle")
        or next((s.get("trackTitle") for s in schedule_sessions if s.get("trackTitle")), "")
        or "Tecnologia e Inovação"
    )
    modality = _clean_text(
        detail.get("modality")
        or home.get("modality")
        or next((s.get("modality") for s in schedule_sessions if s.get("modality")), "")
        or "Online"
    )

    # Coleta todas as datas das sessões da atividade
    session_dts: List[datetime] = []
    for s in schedule_sessions:
        for key in ("startDate", "endDate"):
            dt = _parse_iso_datetime(s.get(key))
            if dt:
                session_dts.append(dt)
    for ev in detail.get("events") or home.get("events") or []:
        if isinstance(ev, dict):
            dt = _parse_iso_datetime(ev.get("startDate") or ev.get("startTime"))
            if dt:
                session_dts.append(dt)

    first_session = min(session_dts) if session_dts else None
    last_session = max(session_dts) if session_dts else first_session

    enrollment_start_dt = _parse_iso_datetime(
        detail.get("enrollmentStart") or home.get("enrollmentStart")
    )
    ano = (
        first_session.year
        if first_session is not None
        else enrollment_start_dt.year if enrollment_start_dt is not None else now.year
    )

    pub_dt = enrollment_start_dt or first_session
    data_publicacao = _format_ddmmyyyy(pub_dt, fallback_year=ano)
    inicio_inscricao = (enrollment_start_dt or first_session).date().isoformat() if (enrollment_start_dt or first_session) else None
    fim_inscricao = last_session.date().isoformat() if last_session else inicio_inscricao

    enrollment_status = str(
        detail.get("enrollmentStatus") or home.get("enrollmentStatus") or ""
    ).strip().lower()

    if enrollment_status == "open":
        if last_session and last_session.date() < now.date():
            status = "fechado"
        else:
            status = "aberto"
    elif enrollment_status in ("closed", "full"):
        status = "fechado"
    else:
        if last_session and last_session.date() >= now.date():
            status = "aberto"
        else:
            status = "fechado"

    # Instrutores / palestrantes
    speakers_list: List[str] = []
    for sp in detail.get("speakers") or []:
        if isinstance(sp, dict) and sp.get("name"):
            sp_name = _clean_text(sp["name"])
            if sp_name and sp_name not in speakers_list:
                speakers_list.append(sp_name)
    if not speakers_list:
        for sp_name_raw in home.get("speakersNames") or []:
            sp_name = _clean_text(str(sp_name_raw))
            if sp_name and sp_name not in speakers_list:
                speakers_list.append(sp_name)

    workload_min = detail.get("certificateWorkload")
    if not workload_min:
        ev_list = detail.get("events") or home.get("events") or []
        if isinstance(ev_list, list):
            workload_min = sum(
                int(ev.get("workload") or 0)
                for ev in ev_list
                if isinstance(ev, dict) and str(ev.get("workload") or "").isdigit()
            ) or None

    desc_parts: List[str] = []
    detail_desc = _clean_html_fragment(detail.get("description"))
    if detail_desc:
        desc_parts.append(detail_desc)
    else:
        desc_parts.append(
            f"Atividade gratuita com certificado promovida pelo Samsung Ocean UnB (Parque Científico e Tecnológico da UnB — PCTec/UnB) na trilha de {track_name}."
        )

    meta_bits: List[str] = [f"Trilha: {track_name}", f"Modalidade: {modality} (Unidade Brasília / UnB)"]
    if first_session:
        if last_session and last_session.date() != first_session.date():
            meta_bits.append(
                f"Realização: {_format_ddmmyyyy(first_session, ano)} a {_format_ddmmyyyy(last_session, ano)}"
            )
        else:
            meta_bits.append(f"Realização: {_format_ddmmyyyy(first_session, ano)}")
    if workload_min and isinstance(workload_min, int) and workload_min > 0:
        horas = workload_min / 60.0
        carga_fmt = f"{int(horas)}h" if horas.is_integer() else f"{horas:.1f}h"
        meta_bits.append(f"Carga horária certificada: {carga_fmt}")
    if speakers_list:
        meta_bits.append(f"Instrutores(as): {', '.join(speakers_list)}")

    target_aud = _clean_html_fragment(detail.get("targetAudience"))
    if target_aud:
        meta_bits.append(f"Público-alvo: {target_aud}")

    prereq = _clean_html_fragment(detail.get("preRequisites"))
    if prereq:
        meta_bits.append(f"Pré-requisitos: {prereq}")

    curriculum = _clean_html_fragment(detail.get("curriculum"))
    if curriculum:
        meta_bits.append(f"Conteúdo programático: {curriculum}")

    descricao = f"{' '.join(desc_parts)} | {' | '.join(meta_bits)}"
    resumo = f"{desc_parts[0]} ({' · '.join(meta_bits[:4])})"

    # Documentos anexos (ex.: Material de Preparação em PDF hospedado no S3 do Ocean)
    docs: List[Dict[str, Any]] = []
    prep = detail.get("preparationMaterial")
    if isinstance(prep, dict) and prep.get("fileUrl"):
        file_url = str(prep["fileUrl"]).strip()
        if file_url:
            docs.append({
                "titulo": f"Material de Preparação — {clean_title}",
                "link": file_url,
                "tipo": "original",
            })

    activity_url = build_ocean_activity_url(group_id, clean_title)
    cat_info = classify_ocean_activity(clean_title, track_name=track_name, modality=modality)

    titulo_formatado = clean_title
    if "ocean" not in clean_title.lower() and "unb" not in clean_title.lower():
        titulo_formatado = f"{clean_title} — Samsung Ocean UnB ({track_name} · {modality})"

    return {
        "titulo": titulo_formatado,
        "assunto": f"Samsung Ocean UnB — {track_name} ({modality})",
        "tipo": cat_info["tipo"],
        "tipo_edital": cat_info["tipo_edital"],
        "programa": cat_info["programa"],
        "modalidade": modality,
        "trilha": track_name,
        "descricao": descricao,
        "resumo": resumo[:1000],
        "unidade": "Ocean UnB (PCTec/UnB)",
        "campus": "Darcy Ribeiro",
        "link": activity_url,
        "link_inscricao": activity_url,
        "data_publicacao": data_publicacao,
        "inicio_inscricao": inicio_inscricao,
        "fim_inscricao": fim_inscricao,
        "status": status,
        "ano": ano,
        "documentos": docs,
    }


def extract_ocean_residencia_unb_docs(
    html: str,
    base_url: str = OCEAN_RESIDENCIA_URL,
) -> List[Dict[str, Any]]:
    """Extrai exclusivamente os documentos PDF da praça Brasília/UnB em `residencia.oceanbrasil.com`."""
    soup = BeautifulSoup(html or "", "html.parser")
    docs: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    for a in soup.find_all("a", href=True):
        raw_href = str(a["href"]).strip()
        if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:")):
            continue
        full_url = urljoin(base_url, raw_href)
        path_lower = urlparse(full_url).path.lower()
        if not path_lower.endswith((".pdf", ".doc", ".docx")):
            continue

        label = _clean_text(a.get_text(" ", strip=True))
        combined_norm = _strip_accents(f"{label} {path_lower}")

        # Exclui documentos exclusivos da praça São Paulo / USP
        if any(sp_tok in combined_norm for sp_tok in ("usp", "edital sp", "_sp_", "-sp-")):
            continue

        # Mantém documentos da UnB / DF / Brasília (ou documentos nacionais sem praça restrita)
        is_unb_doc = any(tok in combined_norm for tok in ("unb", "df", "brasilia", "hub"))
        if not is_unb_doc:
            continue

        if full_url in seen:
            continue
        seen.add(full_url)

        doc_title = label or "Documento Oficial — Residência Tecnológica Ocean UnB"
        if "df" not in doc_title.lower() and "unb" not in doc_title.lower():
            doc_title = f"{doc_title} (Ocean UnB / DF)"

        low_doc = _strip_accents(f"{doc_title} {path_lower}")
        if "resultado" in low_doc and "final" in low_doc:
            doc_type = "resultado_final"
        elif any(k in low_doc for k in ("preliminar", "provisorio", "selecionados", "2a_fase", "entrevista")):
            doc_type = "resultado_provisorio"
        elif any(k in low_doc for k in ("retificacao", "errata", "prorrogacao")):
            doc_type = "retificacao"
        else:
            doc_type = classify_document(doc_title, full_url)

        docs.append({
            "titulo": doc_title,
            "link": full_url,
            "tipo": doc_type,
        })

    return docs


def parse_ocean_residencia_unb_edital(
    html: str,
    base_url: str = OCEAN_RESIDENCIA_URL,
    reference_now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Extrai o edital da praça Brasília (Ocean UnB / HUB-UnB) em `residencia.oceanbrasil.com`."""
    if not html:
        return None
    now = reference_now or _utc_now()
    docs = extract_ocean_residencia_unb_docs(html, base_url=base_url)
    soup = BeautifulSoup(html, "html.parser")
    full_text = _clean_text(soup.get_text(" ", strip=True))
    if not docs and "ocean unb" not in full_text.lower() and "brasília" not in full_text.lower():
        return None

    h1 = soup.find(["h1", "h2"])
    heading = _clean_text(h1.get_text(" ", strip=True)) if h1 else "Programa de Residência Tecnológica em Saúde Digital"
    if "unb" not in heading.lower():
        titulo = f"{heading} — Praça Brasília (Ocean UnB / HUB-UnB)"
    else:
        titulo = heading

    # Determina ano a partir dos links dos documentos UnB ou do texto
    ano: Optional[int] = None
    for d in docs:
        m_y = YEAR_PATTERN.search(d["link"]) or YEAR_PATTERN.search(d["titulo"])
        if m_y:
            ano = int(m_y.group(1))
            break
    if ano is None:
        m_text_y = YEAR_PATTERN.search(full_text)
        ano = int(m_text_y.group(1)) if m_text_y else now.year

    # Procura bloco de datas específico de Brasília — Ocean UnB
    bsb_idx = full_text.lower().find("ocean unb")
    bsb_slice = full_text[bsb_idx:] if bsb_idx != -1 else full_text

    data_pub = f"01/09/{ano}"
    m_pub = re.search(r"(\d{2}/\d{2}/20\d{2})\s*[–\-]\s*Publica[çc][ãa]o do edital", bsb_slice, re.I)
    if m_pub:
        data_pub = m_pub.group(1)

    inicio_insc: Optional[str] = None
    fim_insc: Optional[str] = None
    m_insc = re.search(
        r"(\d{1,2})(?:/(\d{1,2}))?\s*(?:a|até)\s*(\d{1,2})/(\d{1,2})/(20\d{2})\s*[–\-]\s*Per[íi]odo de inscri",
        bsb_slice,
        re.I,
    )
    if m_insc:
        d1, m1_opt, d2, m2, y2 = m_insc.groups()
        m1 = m1_opt or m2
        try:
            inicio_insc = date(int(y2), int(m1), int(d1)).isoformat()
            fim_insc = date(int(y2), int(m2), int(d2)).isoformat()
        except ValueError:
            pass

    has_final = any(d["tipo"] == "resultado_final" for d in docs)
    if has_final:
        status = "fechado"
    elif fim_insc and fim_insc < now.date().isoformat():
        status = "fechado"
    else:
        status = "aberto"

    descricao = (
        f"{titulo}. Capacitação tecnológica e empreendedora presencial com foco em Saúde Digital "
        "realizada no Ocean UnB (PCTec/UnB) em parceria com o Hospital Universitário de Brasília (HUB-UnB/Ebserh), "
        "com duração de 6 meses e oferta de 30 bolsas de estudo de R$ 1.000,00/mês."
    )

    return {
        "titulo": titulo,
        "assunto": "Samsung Ocean UnB / HUB-UnB — Residência Tecnológica em Saúde Digital",
        "tipo": "Residência Tecnológica em Saúde Digital",
        "tipo_edital": "Residência Tecnológica / Bolsa Ocean UnB",
        "programa": "Programa de Residência Tecnológica em Saúde Digital (Ocean UnB / HUB-UnB)",
        "descricao": descricao,
        "resumo": descricao,
        "unidade": "Ocean UnB (PCTec/UnB)",
        "campus": "Darcy Ribeiro",
        "link": f"{base_url.rstrip('/')}/#ocean-unb",
        "link_inscricao": base_url,
        "data_publicacao": data_pub,
        "inicio_inscricao": inicio_insc,
        "fim_inscricao": fim_insc,
        "status": status,
        "ano": ano,
        "documentos": docs,
    }


class OceanBrasilScraper(BaseScraper):
    """Scraper oficial das atividades mensais e editais do Samsung Ocean UnB (`OCEAN`)."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        cache_ttl_seconds: float = CACHE_TTL_SECONDS,
    ) -> None:
        self.timeout = timeout
        self.cache_ttl_seconds = cache_ttl_seconds
        self._docs_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

    @property
    def orgao_origem(self) -> str:
        """Identificador institucional do portal no registro de scrapers."""
        return "OCEAN"

    def _get_cached_docs(self, url: str) -> Optional[List[Dict[str, Any]]]:
        entry = self._docs_cache.get(url)
        if not entry:
            return None
        ts, docs = entry
        if (time.monotonic() - ts) > self.cache_ttl_seconds:
            self._docs_cache.pop(url, None)
            return None
        return docs

    def _set_cached_docs(self, url: str, docs: List[Dict[str, Any]]) -> None:
        self._docs_cache[url] = (time.monotonic(), list(docs))

    def _safe_get_json(
        self,
        client: httpx.Client,
        url: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        for attempt in range(2):
            try:
                resp = client.get(url, params=params)
                if resp.status_code == 200:
                    return resp.json()
                return None
            except httpx.TimeoutException as exc:
                if attempt == 0:
                    continue
                logger.warning(f"Timeout na API OceanBrasil ({url}): {exc}")
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning(f"Erro ao consultar API OceanBrasil ({url}): {exc}")
                return None
        return None

    def fetch_editais(
        self,
        year: Optional[int] = None,
        enrich_all_courses: bool = False,
    ) -> List[Dict[str, Any]]:
        """Coleta todas as atividades mensais e editais da unidade UnB (Brasília) na OceanBrasil.

        Args:
            year: Filtro opcional de ano (ex: 2026). Quando `None`, coleta dinamicamente
                a agenda mensal completa do ano vigente e meses adjacentes de virada de ano.
            enrich_all_courses: Se `True`, consulta `/course/{id}` para 100% dos grupos do ano,
                inclusive cursos históricos encerrados há muitos meses. Por padrão (`False`),
                enriquece cursos ativos, futuros e recentes (últimos 45 dias), garantindo
                execução periódica rápida e gentil com a API.
        """
        now = _utc_now()
        # Limpa cache a cada ciclo de sincronização periódica para evitar dados obsoletos
        self._docs_cache.clear()

        editais: List[Dict[str, Any]] = []
        seen_links: Set[str] = set()

        def _register(item: Optional[Dict[str, Any]]) -> None:
            if not item or not item.get("link"):
                return
            self._set_cached_docs(item["link"], item.get("documentos", []))
            if year is not None and item.get("ano") != year:
                return
            if item["link"] not in seen_links:
                seen_links.add(item["link"])
                editais.append(item)

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/html, */*"},
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                # 1. Coleta `/home/events` para mapear atividades abertas/próximas de Brasília (UnB)
                home_by_id: Dict[int, Dict[str, Any]] = {}
                home_payload = self._safe_get_json(client, f"{OCEAN_API_BASE_URL}/home/events")
                if isinstance(home_payload, dict):
                    for grp in home_payload.get("nextEventGroups") or []:
                        if not isinstance(grp, dict):
                            continue
                        if not is_unb_ocean_campus(grp.get("campusName")):
                            continue
                        gid = grp.get("id")
                        if isinstance(gid, int):
                            home_by_id[gid] = grp

                # 2. Coleta agenda mensal (`/schedule`) para todos os meses aplicáveis na unidade Brasília (UnB)
                schedule_dates = build_monthly_schedule_dates(year=year, reference_now=now)

                def _fetch_month(dt_str: str) -> List[Dict[str, Any]]:
                    payload = self._safe_get_json(
                        client,
                        f"{OCEAN_API_BASE_URL}/schedule",
                        params={
                            "date": dt_str,
                            "timeRange": "MONTHLY",
                            "campus": UNB_CAMPUS_QUERY,
                        },
                    )
                    events_raw: Optional[List[Any]] = None
                    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
                        events_raw = payload["events"]
                    elif isinstance(payload, list):
                        events_raw = payload
                    if events_raw is not None:
                        return [
                            ev
                            for ev in events_raw
                            if isinstance(ev, dict) and is_unb_ocean_campus(ev.get("campusName") or UNB_CAMPUS_QUERY)
                        ]
                    return []

                sessions_by_group: Dict[int, List[Dict[str, Any]]] = {}
                seen_session_ids: Dict[int, Set[Any]] = {}

                with ThreadPoolExecutor(max_workers=6) as pool:
                    monthly_batches = list(pool.map(_fetch_month, schedule_dates))

                for batch in monthly_batches:
                    for ev in batch:
                        gid = ev.get("eventGroupId") or ev.get("id")
                        if not isinstance(gid, int):
                            continue
                        sid = ev.get("id") or ev.get("startDate")
                        seen_sids = seen_session_ids.setdefault(gid, set())
                        if sid in seen_sids:
                            continue
                        seen_sids.add(sid)
                        sessions_by_group.setdefault(gid, []).append(ev)

                all_group_ids = sorted(set(home_by_id.keys()) | set(sessions_by_group.keys()), reverse=True)

                # 3. Seleciona grupos para enriquecimento detalhado via `/course/{id}`
                cutoff_dt = now - timedelta(days=RECENT_ENRICH_WINDOW_DAYS)
                ids_to_enrich: List[int] = []
                for gid in all_group_ids:
                    if enrich_all_courses or gid in home_by_id:
                        ids_to_enrich.append(gid)
                        continue
                    grp_sessions = sessions_by_group.get(gid, [])
                    latest_dt = max(
                        (
                            dt
                            for s in grp_sessions
                            for dt in (_parse_iso_datetime(s.get("endDate") or s.get("startDate")),)
                            if dt is not None
                        ),
                        default=None,
                    )
                    if latest_dt is not None and latest_dt >= cutoff_dt:
                        ids_to_enrich.append(gid)

                details_by_id: Dict[int, Dict[str, Any]] = {}
                if ids_to_enrich:
                    def _fetch_course(gid: int) -> Tuple[int, Optional[Dict[str, Any]]]:
                        data = self._safe_get_json(client, f"{OCEAN_API_BASE_URL}/course/{gid}")
                        return gid, data if isinstance(data, dict) else None

                    with ThreadPoolExecutor(max_workers=8) as pool:
                        for gid, detail_data in pool.map(_fetch_course, ids_to_enrich):
                            if detail_data:
                                details_by_id[gid] = detail_data

                for gid in all_group_ids:
                    edital_item = format_ocean_activity_as_edital(
                        group_id=gid,
                        schedule_sessions=sessions_by_group.get(gid, []),
                        home_summary=home_by_id.get(gid),
                        course_detail=details_by_id.get(gid),
                        reference_now=now,
                    )
                    _register(edital_item)

                # 4. Coleta também o portal oficial da Residência Tecnológica em Saúde Digital (Ocean UnB)
                try:
                    res_resp = client.get(OCEAN_RESIDENCIA_URL)
                    if res_resp.status_code == 200:
                        res_item = parse_ocean_residencia_unb_edital(
                            res_resp.text,
                            base_url=str(res_resp.url),
                            reference_now=now,
                        )
                        _register(res_item)
                except httpx.HTTPError as exc:
                    logger.warning(f"Falha ao consultar portal Residência Ocean UnB ({OCEAN_RESIDENCIA_URL}): {exc}")

        except Exception as exc:
            logger.error(f"Erro geral no scraper OceanBrasil (UnB): {exc}")
            return editais

        return editais

    def fetch_documentos(self, edital_url: str) -> List[Dict[str, Any]]:
        """Extrai documentos vinculados a uma atividade ou edital do Ocean UnB."""
        if not edital_url:
            return []

        cached = self._get_cached_docs(edital_url)
        if cached is not None:
            return cached

        if urlparse(edital_url).path.lower().endswith((".pdf", ".doc", ".docx")):
            return [{
                "titulo": "Documento Oficial Ocean UnB",
                "link": edital_url,
                "tipo": classify_document(edital_url, edital_url),
            }]

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/html, */*"},
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                if "residencia.oceanbrasil.com" in edital_url.lower():
                    base_u = edital_url.split("#", 1)[0] or OCEAN_RESIDENCIA_URL
                    resp = client.get(base_u)
                    if resp.status_code == 200:
                        docs = extract_ocean_residencia_unb_docs(resp.text, base_url=str(resp.url))
                        self._set_cached_docs(edital_url, docs)
                        return docs
                    return []

                m_id = ACTIVITY_ID_FROM_URL_RE.search(edital_url)
                if m_id:
                    gid = int(m_id.group(1))
                    detail = self._safe_get_json(client, f"{OCEAN_API_BASE_URL}/course/{gid}")
                    docs = []
                    if isinstance(detail, dict):
                        prep = detail.get("preparationMaterial")
                        if isinstance(prep, dict) and prep.get("fileUrl"):
                            title = _clean_text(detail.get("title") or f"Atividade {gid}")
                            docs.append({
                                "titulo": f"Material de Preparação — {title}",
                                "link": str(prep["fileUrl"]).strip(),
                                "tipo": "original",
                            })
                    self._set_cached_docs(edital_url, docs)
                    return docs
        except Exception as exc:
            logger.warning(f"Erro ao extrair documentos Ocean UnB ({edital_url}): {exc}")

        return []


ocean_scraper = OceanBrasilScraper()

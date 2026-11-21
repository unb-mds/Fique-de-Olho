import hashlib
import json
import logging
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import (
    Edital,
    EditalDocumento,
    SessionLocal,
    StatusEdital,
    TipoDocumento,
)
from app.modules.scraper import deg
from app.modules.scraper.parser import detect_orgao_emissor, is_vague_title, parse_edital_metadados
from app.modules.scraper.summarizer import (
    enrich_edital_with_llm,
    enrich_metadata_with_llm,
    enrich_title_and_summary,
    is_generic_summary,
)
from app.modules.scraper.pdf import (
    PDFCorruptedError,
    PDFDownloadError,
    PDFExtractionError,
    extract_pdf,
    is_google_drive_url,
)
from app.modules.notificacoes.service import (
    gerar_notificacoes_prazo as _gerar_notificacoes_prazo,
    notificar_edital_atualizado,
)

logger = logging.getLogger(__name__)

PDF_ENRICHMENT_TIMEOUT = 10.0
MAX_TEXTO_EXTRAIDO_CHARS = 100000

MESES_PT = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

MAPA_TIPOS_DOCUMENTO = {
    "original": TipoDocumento.ORIGINAL,
    "resultado_provisorio": TipoDocumento.RESULTADO_PROVISORIO,
    "resultado_final": TipoDocumento.RESULTADO_FINAL,
    "retificacao": TipoDocumento.RETIFICACAO,
    "homologacao": TipoDocumento.RESULTADO_FINAL,
}


def parse_data_publicacao(date_str: str, default_year: Optional[int] = None) -> datetime:
    """Converte strings de datas brasileiras ou ISO para objetos datetime com timezone UTC."""
    eff_year = default_year if default_year is not None else datetime.now(timezone.utc).year
    if not date_str or not isinstance(date_str, str):
        return datetime(eff_year, 1, 1, tzinfo=timezone.utc)

    cleaned = date_str.strip().lower()

    # Formato ISO: 2026-09-22 (ou 2026-09-22T...)
    iso_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})(?![0-9])", cleaned)
    if iso_match:
        try:
            return datetime(
                int(iso_match.group(1)),
                int(iso_match.group(2)),
                int(iso_match.group(3)),
                tzinfo=timezone.utc,
            )
        except ValueError:
            pass

    # Formato: 23 de setembro de 2026
    extenso_match = re.search(r"(\d{1,2})\s+de\s+([a-zçáéíóúãõâêîôû]+)\s+de\s+(\d{4})", cleaned)
    if extenso_match:
        day = int(extenso_match.group(1))
        mes_nome = extenso_match.group(2)
        year = int(extenso_match.group(3))
        month = MESES_PT.get(mes_nome, 1)
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            pass

    # Formato: 15/03/2026
    barra_match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", cleaned)
    if barra_match:
        day = int(barra_match.group(1))
        month = int(barra_match.group(2))
        year = int(barra_match.group(3))
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            pass

    return datetime(eff_year, 1, 1, tzinfo=timezone.utc)


def map_tipo_documento(tipo_str: str, titulo_str: Optional[str] = None) -> TipoDocumento:
    """Mapeia string do scraper para o enum TipoDocumento do banco, considerando também o título."""
    normalizado = tipo_str.lower().strip() if tipo_str else "original"
    mapped = MAPA_TIPOS_DOCUMENTO.get(normalizado)
    if mapped is not None and mapped != TipoDocumento.ORIGINAL:
        return mapped

    if titulo_str:
        tit_low = titulo_str.lower()
        if any(k in tit_low for k in ("resultado final", "resultado_final", "homologacao", "homologação")):
            return TipoDocumento.RESULTADO_FINAL
        if any(k in tit_low for k in ("resultado provisorio", "resultado provisório", "resultado preliminar")):
            return TipoDocumento.RESULTADO_PROVISORIO
        if any(k in tit_low for k in ("retificacao", "retificação")):
            return TipoDocumento.RETIFICACAO

    return mapped or TipoDocumento.ORIGINAL


def _parse_optional_date(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            pass
        low = raw.lower()
        m_ext = re.search(r"(\d{1,2})\s+de\s+([a-zçáéíóúãõâêîôû]+)\s+de\s+(\d{4})", low)
        if m_ext:
            try:
                return date(int(m_ext.group(3)), MESES_PT.get(m_ext.group(2), 1), int(m_ext.group(1)))
            except ValueError:
                return None
        m_slash = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", low)
        if m_slash:
            try:
                return date(int(m_slash.group(3)), int(m_slash.group(2)), int(m_slash.group(1)))
            except ValueError:
                return None
    return None


def _coerce_vagas(value: Any) -> Optional[int]:
    """Converte número ou string (ex.: '2100', '1 vaga', '2 + CR') para inteiro positivo seguro."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 < value < 1000000 else None
    if isinstance(value, float):
        iv = int(value)
        return iv if 0 < iv < 1000000 else None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            val = int(raw)
            return val if 0 < val < 1000000 else None
        m = re.search(
            r"\b(\d{1,6})\s*(?:vagas?|bolsas?|\+\s*cr\b|cadastro)",
            raw,
            re.I,
        )
        if m:
            val = int(m.group(1))
            return val if 0 < val < 1000000 else None
        nums = re.findall(r"\b(\d{1,6})\b", raw)
        if len(nums) == 1:
            val = int(nums[0])
            return val if 0 < val < 1000000 else None
    return None


def _coerce_valor_bolsa(value: Any) -> Optional[Decimal]:
    """Converte número, Decimal ou string monetária ('R$ 1.500,00', 700.0) para Decimal(10, 2)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        if value <= 0 or value >= Decimal("100000000"):
            return None
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if isinstance(value, (int, float)):
        if value <= 0 or value >= 100000000:
            return None
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except InvalidOperation:
            return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        cleaned = re.sub(r"[rR]\$\s*", "", raw).strip()
        m_br = re.search(r"(\d{1,3}(?:\.\d{3})+,\d{1,2}|\d+,\d{1,2})", cleaned)
        if m_br:
            num_str = m_br.group(1).replace(".", "").replace(",", ".")
        else:
            m_num = re.search(r"\b(\d+(?:\.\d{1,2})?)\b", cleaned)
            if not m_num:
                return None
            num_str = m_num.group(1)
        try:
            dec = Decimal(num_str).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return dec if Decimal("0") < dec < Decimal("100000000") else None
        except InvalidOperation:
            return None
    return None


def _sanitize_periodo_inscricao(
    inicio: Optional[date],
    fim: Optional[date],
    context: str = "",
) -> tuple[Optional[date], Optional[date]]:
    """Garante a constraint inicio_inscricao <= fim_inscricao, descartando início inconsistente."""
    if inicio is not None and fim is not None and inicio > fim:
        logger.warning(
            f"Período de inscrição inconsistente ({inicio} > {fim}) em '{context}'; "
            "descartando inicio_inscricao para respeitar editais_periodo_inscricao_ck."
        )
        return None, fim
    return inicio, fim


def _sanitize_texto_extraido(text: Optional[str]) -> Optional[str]:
    """Remove NUL bytes e limita tamanho para persistência segura no PostgreSQL."""
    if not text:
        return None
    cleaned = text.replace("\x00", "").strip()
    if not cleaned:
        return None
    return cleaned[:MAX_TEXTO_EXTRAIDO_CHARS]


def _is_likely_pdf_url(url: Optional[str]) -> bool:
    """Verifica se a URL aponta para um documento PDF (ou endpoint de download de arquivo)."""
    if not url or not isinstance(url, str):
        return False
    low = url.strip().lower()
    if not low.startswith(("http://", "https://")):
        return False
    if is_google_drive_url(url):
        return True
    base_path = low.split("?", 1)[0].split("#", 1)[0]
    if base_path.endswith(".pdf"):
        return True
    if any(token in low for token in (".pdf?", "download=", "/download/", "id_arquivo=")):
        return True
    return False


def _select_candidate_pdf_url(
    edital_data: Dict[str, Any],
    effective_docs: List[Dict[str, Any]],
    url_pagina: str,
) -> Optional[str]:
    """Determina a URL candidata oficial do PDF do edital (Prioridade 2)."""
    raw_url_pdf = str(edital_data.get("url_pdf") or "").strip()
    if raw_url_pdf and _is_likely_pdf_url(raw_url_pdf):
        return raw_url_pdf

    # Procura primeiro documento original com extensão .pdf
    for doc in effective_docs:
        doc_url = str(doc.get("link") or doc.get("url_pdf") or "").strip()
        raw_tipo = doc.get("tipo") or doc.get("tipo_documento") or "original"
        tipo = map_tipo_documento(raw_tipo, doc.get("titulo"))
        if tipo == TipoDocumento.ORIGINAL and _is_likely_pdf_url(doc_url):
            return doc_url

    # Fallback: primeiro documento com extensão .pdf na lista de anexos
    for doc in effective_docs:
        doc_url = str(doc.get("link") or doc.get("url_pdf") or "").strip()
        if _is_likely_pdf_url(doc_url):
            return doc_url

    # Se a própria url_pagina for um link direto .pdf
    if _is_likely_pdf_url(url_pagina):
        return url_pagina

    return None


def _select_retificacao_pdf_urls(
    effective_docs: List[Dict[str, Any]],
    primary_pdf_url: Optional[str] = None,
) -> List[str]:
    """Retorna URLs de PDFs classificados como retificação (em ordem de aparição)."""
    retificacoes: List[str] = []
    for doc in effective_docs:
        doc_url = str(doc.get("link") or doc.get("url_pdf") or "").strip()
        if not doc_url or doc_url == primary_pdf_url or not _is_likely_pdf_url(doc_url):
            continue
        raw_tipo = doc.get("tipo") or doc.get("tipo_documento") or "original"
        tipo = map_tipo_documento(raw_tipo, doc.get("titulo"))
        if tipo == TipoDocumento.RETIFICACAO and doc_url not in retificacoes:
            retificacoes.append(doc_url)
    return retificacoes


def _enrich_edital_metadata(
    edital_data: Dict[str, Any],
    effective_docs: List[Dict[str, Any]],
    existing_edital: Optional[Edital] = None,
    hash_conteudo: Optional[str] = None,
    default_orgao: Optional[str] = None,
    enable_pdf_enrichment: bool = True,
) -> Dict[str, Any]:
    """Enriquece os metadados do edital combinando dados estruturados do scraper (P1) e fallback PDF (P2)."""
    url_pagina = str(edital_data.get("link") or edital_data.get("url_pagina") or "").strip()
    titulo = str(edital_data.get("titulo") or "").strip()

    # 1. Prioridade 1 — Dados Estruturados do Scraper
    inicio_insc = _parse_optional_date(edital_data.get("inicio_inscricao"))
    fim_insc = _parse_optional_date(edital_data.get("fim_inscricao"))
    inicio_insc, fim_insc = _sanitize_periodo_inscricao(inicio_insc, fim_insc, context=url_pagina or titulo)

    raw_orgao = (
        edital_data.get("orgao_emissor")
        or edital_data.get("orgao_origem")
        or default_orgao
    )
    orgao_emissor = str(raw_orgao).strip()[:50] if raw_orgao and str(raw_orgao).strip() else None

    raw_assunto = edital_data.get("assunto")
    assunto = str(raw_assunto).strip() if raw_assunto and str(raw_assunto).strip() else None

    raw_campus = edital_data.get("campus")
    campus = str(raw_campus).strip()[:255] if raw_campus and str(raw_campus).strip() else None

    vagas = _coerce_vagas(edital_data.get("vagas"))
    valor_bolsa = _coerce_valor_bolsa(
        edital_data.get("valor_bolsa")
        if edital_data.get("valor_bolsa") is not None
        else edital_data.get("valor")
    )
    texto_extraido = _sanitize_texto_extraido(edital_data.get("texto_extraido"))
    resumo = (
        edital_data.get("resumo")
        or edital_data.get("descricao")
        or assunto
    )

    candidate_pdf_url = _select_candidate_pdf_url(edital_data, effective_docs, url_pagina)

    # Preserva texto_extraido e metadados já existentes no banco em caso de reprocessamento idempotente
    is_redundant_reprocess = False
    if existing_edital is not None:
        same_hash = bool(hash_conteudo and existing_edital.hash_conteudo == hash_conteudo)
        same_pdf = (
            not candidate_pdf_url
            or existing_edital.url_pdf == candidate_pdf_url
            or any(d.url_pdf == candidate_pdf_url for d in existing_edital.documentos)
        )
        if same_hash and same_pdf and existing_edital.texto_extraido:
            is_redundant_reprocess = True
            if not texto_extraido:
                texto_extraido = existing_edital.texto_extraido
            if inicio_insc is None and "inicio_inscricao" not in edital_data:
                inicio_insc = existing_edital.inicio_inscricao
            if fim_insc is None and "fim_inscricao" not in edital_data:
                fim_insc = existing_edital.fim_inscricao
            if vagas is None and "vagas" not in edital_data:
                vagas = existing_edital.vagas
            if valor_bolsa is None and "valor_bolsa" not in edital_data and "valor" not in edital_data:
                valor_bolsa = existing_edital.valor_bolsa
            if not campus:
                campus = existing_edital.campus
            if not orgao_emissor:
                orgao_emissor = existing_edital.orgao_emissor
            if not assunto:
                assunto = existing_edital.assunto
            inicio_insc, fim_insc = _sanitize_periodo_inscricao(inicio_insc, fim_insc, context=url_pagina or titulo)

            # Reaproveita texto_extraido local (sem baixar PDF) para preencher datas legadas ausentes
            if (inicio_insc is None or fim_insc is None) and texto_extraido:
                ano_ref_local = edital_data.get("ano") if isinstance(edital_data.get("ano"), int) else None
                data_pub_local = _parse_optional_date(edital_data.get("data_publicacao") or existing_edital.data_publicacao)
                data_pub_dt_local = (
                    datetime(data_pub_local.year, data_pub_local.month, data_pub_local.day, tzinfo=timezone.utc)
                    if data_pub_local
                    else None
                )
                parsed_local = parse_edital_metadados(
                    texto_extraido,
                    ano_referencia=ano_ref_local,
                    data_publicacao=data_pub_dt_local,
                )
                local_ini = _parse_optional_date(parsed_local.inicio_inscricao)
                local_fim = _parse_optional_date(parsed_local.fim_inscricao)
                local_ini, local_fim = _sanitize_periodo_inscricao(local_ini, local_fim, context=url_pagina or titulo)
                if inicio_insc is None and local_ini is not None and (fim_insc is None or local_ini <= fim_insc):
                    inicio_insc = local_ini
                if fim_insc is None and local_fim is not None and (inicio_insc is None or inicio_insc <= local_fim):
                    fim_insc = local_fim

    missing_essential = (
        any(x is None for x in (inicio_insc, fim_insc, vagas, valor_bolsa, campus))
        or not texto_extraido
    )

    pdf_attempted = False
    pdf_failed = False
    pdf_succeeded = False

    ano_ref = edital_data.get("ano") if isinstance(edital_data.get("ano"), int) else None
    data_pub_raw = edital_data.get("data_publicacao")
    data_pub_dt = None
    if data_pub_raw:
        parsed_pub = _parse_optional_date(data_pub_raw)
        if parsed_pub:
            data_pub_dt = datetime(parsed_pub.year, parsed_pub.month, parsed_pub.day, tzinfo=timezone.utc)

    # 2. Prioridade 2 — Fallback/Enriquecimento via extract_pdf + parse_edital_metadados
    if (
        enable_pdf_enrichment
        and candidate_pdf_url
        and missing_essential
        and not is_redundant_reprocess
    ):
        pdf_attempted = True
        try:
            extraction = extract_pdf(candidate_pdf_url, timeout=PDF_ENRICHMENT_TIMEOUT)
            extracted_txt = _sanitize_texto_extraido(getattr(extraction, "full_text", None))
            if extracted_txt and not texto_extraido:
                texto_extraido = extracted_txt

            parsed = parse_edital_metadados(extraction, ano_referencia=ano_ref, data_publicacao=data_pub_dt)
            pdf_succeeded = True

            # Preenche apenas campos ausentes (scraper > parser do PDF)
            if not orgao_emissor and parsed.orgao_emissor:
                orgao_emissor = parsed.orgao_emissor[:50]
            if not campus and parsed.campus:
                campus = parsed.campus[:255]
            if vagas is None and parsed.vagas is not None:
                vagas = _coerce_vagas(parsed.vagas)
            if valor_bolsa is None and parsed.valor_bolsa is not None:
                valor_bolsa = _coerce_valor_bolsa(parsed.valor_bolsa)

            pdf_ini = _parse_optional_date(parsed.inicio_inscricao)
            pdf_fim = _parse_optional_date(parsed.fim_inscricao)
            pdf_ini, pdf_fim = _sanitize_periodo_inscricao(pdf_ini, pdf_fim, context=candidate_pdf_url)

            if inicio_insc is None and pdf_ini is not None:
                if fim_insc is None or pdf_ini <= fim_insc:
                    inicio_insc = pdf_ini
                else:
                    logger.warning(
                        f"Data inicio_inscricao do PDF ({pdf_ini}) > fim_inscricao ({fim_insc}) "
                        f"em {candidate_pdf_url}; mantendo apenas fim_inscricao."
                    )

            if fim_insc is None and pdf_fim is not None:
                if inicio_insc is None or inicio_insc <= pdf_fim:
                    fim_insc = pdf_fim
                else:
                    logger.warning(
                        f"Data fim_inscricao do PDF ({pdf_fim}) < inicio_inscricao ({inicio_insc}) "
                        f"em {candidate_pdf_url}; ignorando fim_inscricao inconsistente."
                    )

            inicio_insc, fim_insc = _sanitize_periodo_inscricao(inicio_insc, fim_insc, context=url_pagina or titulo)

        except (PDFExtractionError, PDFDownloadError, PDFCorruptedError, Exception) as exc:
            pdf_failed = True
            logger.warning(f"Falha ao extrair/enriquecer PDF '{candidate_pdf_url}' para '{url_pagina}': {exc}")

    # 2.1 Retificações de prazo (prorrogação ou definição de novas datas em PDFs de retificação)
    if enable_pdf_enrichment and not is_redundant_reprocess:
        for ret_url in _select_retificacao_pdf_urls(effective_docs, candidate_pdf_url):
            try:
                ret_extraction = extract_pdf(ret_url, timeout=PDF_ENRICHMENT_TIMEOUT)
                ret_parsed = parse_edital_metadados(
                    ret_extraction,
                    ano_referencia=ano_ref,
                    data_publicacao=data_pub_dt,
                )
                ret_ini = _parse_optional_date(ret_parsed.inicio_inscricao)
                ret_fim = _parse_optional_date(ret_parsed.fim_inscricao)
                ret_ini, ret_fim = _sanitize_periodo_inscricao(ret_ini, ret_fim, context=ret_url)
                if ret_fim is not None and (fim_insc is None or ret_fim > fim_insc):
                    fim_insc = ret_fim
                if inicio_insc is None and ret_ini is not None and (fim_insc is None or ret_ini <= fim_insc):
                    inicio_insc = ret_ini
            except Exception as ret_exc:
                logger.warning(f"Falha ao ler retificação '{ret_url}' para '{url_pagina}': {ret_exc}")

    # 2.2 / 3. Segunda passada unificada (Camada 1 + Camada 2 Gemini em no máximo 1 chamada)
    existing_title_summary_ok = bool(
        existing_edital is not None
        and hash_conteudo
        and existing_edital.hash_conteudo == hash_conteudo
        and not is_vague_title(existing_edital.titulo)
        and not is_generic_summary(existing_edital.resumo, existing_edital.titulo)
    )
    faltam_metadados_llm = bool(
        enable_pdf_enrichment
        and texto_extraido
        and (
            (not is_redundant_reprocess and (inicio_insc is None or fim_insc is None or valor_bolsa is None or vagas is None))
            or (is_redundant_reprocess and fim_insc is None)
        )
    )

    if existing_title_summary_ok and not faltam_metadados_llm:
        titulo_final = existing_edital.titulo
        resumo_final = existing_edital.resumo
    else:
        incoming_resumo = edital_data.get("resumo") or edital_data.get("descricao")
        incoming_resumo = str(incoming_resumo).strip() if incoming_resumo else None
        resumo_base: Optional[str] = incoming_resumo
        if is_generic_summary(incoming_resumo, titulo):
            resumo_base = None
            if existing_edital is not None and not is_generic_summary(
                existing_edital.resumo, existing_edital.titulo
            ):
                resumo_base = existing_edital.resumo

        texto_base = texto_extraido or (existing_edital.texto_extraido if existing_edital is not None else None)
        assunto_base = assunto or (existing_edital.assunto if existing_edital is not None else None)
        orgao_base = orgao_emissor or (existing_edital.orgao_emissor if existing_edital is not None else None)
        url_pdf_base = candidate_pdf_url or (existing_edital.url_pdf if existing_edital is not None else None)

        llm_unificado = enrich_edital_with_llm(
            titulo=existing_edital.titulo if existing_title_summary_ok else titulo,
            texto_extraido=texto_base,
            assunto=assunto_base,
            orgao_emissor=orgao_base,
            url_pdf=url_pdf_base,
            resumo_atual=(
                existing_edital.resumo
                if existing_title_summary_ok
                else (resumo_base or incoming_resumo)
            ),
            pedir_metadados=faltam_metadados_llm,
        )

        if faltam_metadados_llm:
            if inicio_insc is None and llm_unificado.get("inicio_inscricao"):
                inicio_insc = _parse_optional_date(llm_unificado["inicio_inscricao"])
            if fim_insc is None and llm_unificado.get("fim_inscricao"):
                fim_insc = _parse_optional_date(llm_unificado["fim_inscricao"])
            if valor_bolsa is None and llm_unificado.get("valor_bolsa") is not None:
                valor_bolsa = _coerce_valor_bolsa(llm_unificado["valor_bolsa"])
            if vagas is None and llm_unificado.get("vagas") is not None:
                vagas = _coerce_vagas(llm_unificado["vagas"])
            if not orgao_emissor and llm_unificado.get("orgao_emissor"):
                orgao_emissor = str(llm_unificado["orgao_emissor"]).strip()[:50]
            inicio_insc, fim_insc = _sanitize_periodo_inscricao(inicio_insc, fim_insc, context=url_pagina or titulo)

        titulo_final = (
            existing_edital.titulo
            if existing_title_summary_ok
            else (llm_unificado.get("titulo") or titulo or "Edital sem título")
        )
        resumo_final = (
            existing_edital.resumo
            if existing_title_summary_ok
            else llm_unificado.get("resumo")
        )
        if not resumo_final:
            fallback = edital_data.get("resumo_fallback")
            resumo_final = str(fallback).strip() if fallback else None

    # Se ainda não identificou órgão emissor no PDF nem veio estruturado, tenta detectar pelo título/resumo
    if not orgao_emissor:
        detected = detect_orgao_emissor(f"{titulo_final} {resumo_final or ''}")
        if detected:
            orgao_emissor = detected[:50]

    # 4. Ciclo de status_processamento
    has_complete_metadata = bool(
        (inicio_insc is not None or fim_insc is not None)
        and (vagas is not None or valor_bolsa is not None or campus is not None)
    )
    if pdf_failed:
        status_processamento = "erro"
    elif pdf_succeeded or is_redundant_reprocess or has_complete_metadata or bool(texto_extraido):
        status_processamento = "processado"
    else:
        status_processamento = "parcialmente_processado"

    return {
        "titulo": titulo_final,
        "orgao_emissor": orgao_emissor,
        "assunto": assunto,
        "campus": campus,
        "vagas": vagas,
        "valor_bolsa": valor_bolsa,
        "inicio_inscricao": inicio_insc,
        "fim_inscricao": fim_insc,
        "texto_extraido": texto_extraido,
        "resumo": resumo_final,
        "status_processamento": status_processamento,
        "candidate_pdf_url": candidate_pdf_url,
        "pdf_attempted": pdf_attempted,
        "pdf_failed": pdf_failed,
    }


def _merge_documentos_list(
    embedded_docs: Any,
    explicit_docs: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Combina documentos embutidos no dicionário do edital com documentos passados explicitamente."""
    merged: List[Dict[str, Any]] = []
    seen_urls = set()

    sources: List[Dict[str, Any]] = []
    if explicit_docs:
        sources.extend(d for d in explicit_docs if isinstance(d, dict))
    if isinstance(embedded_docs, list):
        sources.extend(d for d in embedded_docs if isinstance(d, dict))

    for doc in sources:
        doc_url = str(doc.get("link") or doc.get("url_pdf") or "").strip()
        if not doc_url or doc_url in seen_urls:
            continue
        seen_urls.add(doc_url)
        merged.append(doc)
    return merged


def _resolve_unique_url_pdf(
    db: Session,
    candidate_pdf: Optional[str],
    url_pagina: str,
) -> Optional[str]:
    """Evita violação da restrição UNIQUE em Edital.url_pdf caso dois editais compartilhem o mesmo PDF.

    Garante que Edital.url_pdf contenha apenas URLs diretas de PDF válidas (nunca a página HTML).
    """
    primary = (candidate_pdf or "").strip() or None
    if not primary or not _is_likely_pdf_url(primary):
        return None

    collision = (
        db.query(Edital.id)
        .filter(Edital.url_pdf == primary, Edital.url_pagina != url_pagina)
        .first()
    )
    if collision is None:
        return primary

    if url_pagina and url_pagina != primary and _is_likely_pdf_url(url_pagina):
        page_collision = (
            db.query(Edital.id)
            .filter(Edital.url_pdf == url_pagina, Edital.url_pagina != url_pagina)
            .first()
        )
        if page_collision is None:
            return url_pagina

    return None


def _resumo_para_hash(edital_data: Dict[str, Any]) -> Any:
    """Componente de resumo do hash, estável com o formato anterior do payload do service.

    O service passou a enviar a frase genérica em ``resumo_fallback`` (em vez de ``resumo``);
    usá-la no hash quando não há resumo real evita falsas "atualizações relevantes".
    """
    resumo = edital_data.get("resumo", "")
    if not resumo and edital_data.get("resumo_fallback"):
        return edital_data["resumo_fallback"]
    return resumo


def _hash_edital(edital_data: Dict[str, Any], documentos_data: List[Dict[str, Any]]) -> str:
    """Calcula um hash estável dos dados observáveis do edital."""
    payload = {
        "titulo": edital_data.get("titulo", ""),
        "resumo": _resumo_para_hash(edital_data),
        "data_publicacao": str(edital_data.get("data_publicacao", "")),
        "inicio_inscricao": str(edital_data.get("inicio_inscricao", "")),
        "fim_inscricao": str(edital_data.get("fim_inscricao", "")),
        "documentos": sorted(
            (
                doc.get("link") or doc.get("url_pdf", ""),
                doc.get("tipo") or doc.get("tipo_documento") or "",
            )
            for doc in documentos_data
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _resolve_edital_status(
    edital_data: Dict[str, Any],
    tem_resultado_final: bool,
    fim_inscricao: Optional[date],
) -> StatusEdital:
    """Determina o status atualizado do edital de forma compatível com execuções periódicas."""
    if tem_resultado_final:
        return StatusEdital.ENCERRADO

    raw_status = str(edital_data.get("status") or "").strip().lower()
    if raw_status in ("fechado", "encerrado"):
        return StatusEdital.ENCERRADO

    if fim_inscricao is not None and fim_inscricao < datetime.now(timezone.utc).date():
        return StatusEdital.ENCERRADO

    return StatusEdital.ABERTO


def upsert_edital(
    db: Session,
    edital_data: Dict[str, Any],
    documentos_data: Optional[List[Dict[str, Any]]] = None,
    enable_pdf_enrichment: bool = True,
) -> Edital:
    """
    Insere ou atualiza um edital e seus documentos associados (UPSERT).
    Garante idempotência e atualização periódica evitando duplicações por url_pagina e url_pdf,
    enriquecendo metadados via scraper + PDF fallback e recalculando status automaticamente.
    """
    effective_docs = _merge_documentos_list(edital_data.get("documentos"), documentos_data)
    url_pagina = edital_data.get("link") or edital_data.get("url_pagina", "")
    titulo = edital_data.get("titulo", "Edital sem título")
    data_str = edital_data.get("data_publicacao", "")
    default_yr = edital_data.get("ano") if isinstance(edital_data.get("ano"), int) else None
    data_pub = parse_data_publicacao(str(data_str), default_year=default_yr)
    hash_conteudo = edital_data.get("hash_conteudo") or _hash_edital(edital_data, effective_docs)

    # Busca edital existente pela URL única antes do enriquecimento para permitir skip idempotente
    edital = db.query(Edital).filter(Edital.url_pagina == url_pagina).first()

    # Etapa de enriquecimento híbrido (estruturado + PDF fallback)
    enriched = _enrich_edital_metadata(
        edital_data=edital_data,
        effective_docs=effective_docs,
        existing_edital=edital,
        hash_conteudo=hash_conteudo,
        enable_pdf_enrichment=enable_pdf_enrichment,
    )

    inicio_insc = enriched["inicio_inscricao"]
    fim_insc = enriched["fim_inscricao"]
    titulo = enriched["titulo"] or titulo
    orgao_emissor = enriched["orgao_emissor"]
    assunto = enriched["assunto"]
    campus = enriched["campus"]
    vagas = enriched["vagas"]
    valor_bolsa = enriched["valor_bolsa"]
    texto_extraido = enriched["texto_extraido"]
    resumo = enriched["resumo"]
    status_processamento = enriched["status_processamento"]
    candidate_pdf_url = enriched["candidate_pdf_url"]

    # Determina se há resultado final nos documentos informados ou já persistidos
    tem_resultado_final = any(
        map_tipo_documento(
            doc.get("tipo") or doc.get("tipo_documento") or "",
            doc.get("titulo"),
        )
        == TipoDocumento.RESULTADO_FINAL
        for doc in effective_docs
    )
    if edital and any(d.tipo_documento == TipoDocumento.RESULTADO_FINAL for d in edital.documentos):
        tem_resultado_final = True

    # Recalcula status DEPOIS do enriquecimento via PDF
    novo_status = _resolve_edital_status(edital_data, tem_resultado_final, fim_insc)
    tipo = edital_data.get("tipo") or edital_data.get("tipo_edital")

    if edital:
        hash_anterior = edital.hash_conteudo
        # Atualiza dados existentes mantendo frescor em execuções periódicas
        edital.titulo = titulo
        edital.data_publicacao = data_pub
        if candidate_pdf_url:
            if (
                not edital.url_pdf
                or not _is_likely_pdf_url(edital.url_pdf)
                or (
                    edital_data.get("url_pdf")
                    and _is_likely_pdf_url(str(edital_data.get("url_pdf")))
                )
            ):
                safe_pdf = _resolve_unique_url_pdf(db, candidate_pdf_url, url_pagina)
                if safe_pdf:
                    edital.url_pdf = safe_pdf
        elif edital.url_pdf and not _is_likely_pdf_url(edital.url_pdf):
            edital.url_pdf = None
        if resumo:
            edital.resumo = resumo
        if tipo:
            edital.tipo = tipo
        if campus:
            edital.campus = campus
        if orgao_emissor:
            edital.orgao_emissor = orgao_emissor
        if assunto:
            edital.assunto = assunto
        if vagas is not None:
            edital.vagas = vagas
        if valor_bolsa is not None:
            edital.valor_bolsa = valor_bolsa
        if texto_extraido:
            edital.texto_extraido = texto_extraido
        if inicio_insc is not None or "inicio_inscricao" in edital_data:
            edital.inicio_inscricao = inicio_insc
        if fim_insc is not None or "fim_inscricao" in edital_data:
            edital.fim_inscricao = fim_insc
        # Garante invariante de período de inscrição no banco
        edital.inicio_inscricao, edital.fim_inscricao = _sanitize_periodo_inscricao(
            edital.inicio_inscricao, edital.fim_inscricao, context=url_pagina
        )
        edital.status_processamento = status_processamento
        edital.hash_conteudo = hash_conteudo
        edital.status = novo_status
        edital.atualizado_em = datetime.now(timezone.utc)
        if hash_anterior != hash_conteudo:
            notificar_edital_atualizado(db, edital, hash_conteudo)
    else:
        # Cria novo edital protegendo unicidade de url_pdf (apenas URLs de PDF válidas)
        safe_url_pdf = _resolve_unique_url_pdf(
            db,
            candidate_pdf_url,
            url_pagina,
        )
        edital = Edital(
            titulo=titulo,
            url_pagina=url_pagina,
            url_pdf=safe_url_pdf,
            data_publicacao=data_pub,
            status=novo_status,
            campus=campus,
            tipo=tipo,
            resumo=resumo,
            orgao_emissor=orgao_emissor,
            assunto=assunto,
            vagas=vagas,
            valor_bolsa=valor_bolsa,
            inicio_inscricao=inicio_insc,
            fim_inscricao=fim_insc,
            texto_extraido=texto_extraido,
            status_processamento=status_processamento,
            hash_conteudo=hash_conteudo,
        )
        db.add(edital)
        db.flush()

    # Processa documentos vinculados de forma incremental
    docs_existentes = {doc.url_pdf: doc for doc in edital.documentos}

    for doc_data in effective_docs:
        doc_url = doc_data.get("link") or doc_data.get("url_pdf", "")
        if not doc_url:
            continue

        raw_doc_tipo = doc_data.get("tipo") or doc_data.get("tipo_documento") or "original"
        tipo_enum = map_tipo_documento(raw_doc_tipo, doc_data.get("titulo"))

        if doc_url in docs_existentes:
            # Atualiza tipo se necessário
            docs_existentes[doc_url].tipo_documento = tipo_enum
        else:
            # Adiciona novo documento vinculado
            novo_doc = EditalDocumento(
                edital_id=edital.id,
                url_pdf=doc_url,
                tipo_documento=tipo_enum,
            )
            db.add(novo_doc)
            docs_existentes[doc_url] = novo_doc

    # Se qualquer documento cadastrado for resultado_final, garante status encerrado
    if any(d.tipo_documento == TipoDocumento.RESULTADO_FINAL for d in edital.documentos):
        edital.status = StatusEdital.ENCERRADO

    db.commit()
    db.refresh(edital)
    return edital


def gerar_notificacoes_prazo(
    db: Session,
    data_referencia: Optional[date] = None,
) -> int:
    """Compatibilidade pública para o serviço de notificações de prazo."""
    return _gerar_notificacoes_prazo(db, data_referencia)


def run_pipeline(
    db: Session,
    year: Optional[int] = None,
    fetch_docs: bool = True,
    enable_pdf_enrichment: bool = True,
    scraper: Optional[Any] = None,
    orgao: Optional[str] = None,
    max_items: Optional[int] = None,
) -> List[Edital]:
    """Executa a coleta de um scraper (instância de BaseScraper, sigla de órgão ou DEG por padrão) e persiste no banco."""
    from app.modules.scraper import get_scraper

    if scraper is not None:
        if isinstance(scraper, str):
            target_scraper = get_scraper(scraper)
            if target_scraper is None:
                raise ValueError(f"Portal '{scraper}' não registrado em SCRAPERS_REGISTRY.")
            sigla = getattr(target_scraper, "orgao_origem", scraper.upper().strip())
        else:
            target_scraper = scraper
            sigla = getattr(target_scraper, "orgao_origem", None) or (
                orgao.upper().strip() if orgao else "DEG"
            )
    elif orgao is not None:
        target_scraper = get_scraper(orgao)
        if target_scraper is None:
            raise ValueError(f"Portal '{orgao}' não registrado em SCRAPERS_REGISTRY.")
        sigla = getattr(target_scraper, "orgao_origem", orgao.upper().strip())
    else:
        target_scraper = deg
        sigla = "DEG"

    editais_coletados = target_scraper.fetch_editais(year=year)
    if max_items is not None:
        editais_coletados = editais_coletados[:max_items]
    logger.info(f"Coletados {len(editais_coletados)} editais do portal {sigla}.")

    editais_persistidos: List[Edital] = []
    for item in editais_coletados:
        if not item.get("link") or not item.get("titulo"):
            continue
        embedded_docs = item.get("documentos")
        docs: List[Dict[str, Any]] = []
        if fetch_docs and not embedded_docs and item.get("link"):
            try:
                docs = target_scraper.fetch_documentos(item["link"])
            except Exception as exc:
                logger.warning(f"[{sigla}] Erro ao buscar documentos para {item['link']}: {exc}")

        payload = {
            **item,
            "orgao_emissor": item.get("orgao_emissor") or item.get("orgao_origem") or sigla,
        }
        try:
            edital_salvo = upsert_edital(
                db=db,
                edital_data=payload,
                documentos_data=docs,
                enable_pdf_enrichment=enable_pdf_enrichment,
            )
            editais_persistidos.append(edital_salvo)
        except Exception as item_exc:
            db.rollback()
            logger.warning(f"[{sigla}] Falha ao persistir edital {item.get('link')}: {item_exc}")

    return editais_persistidos


def run_periodic_pipeline(
    db: Session,
    orgaos: Optional[List[str]] = None,
    year: Optional[int] = None,
    fetch_docs: bool = True,
    max_items_per_orgao: Optional[int] = None,
    enable_pdf_enrichment: Optional[bool] = None,
) -> Dict[str, List[Edital]]:
    """Executa periodicamente a coleta idempotente de múltiplos (ou todos os) portais registrados.

    Isola falhas por portal para que a indisponibilidade temporária de um site externo
    nunca interrompa a sincronização periódica dos demais órgãos, e dispara alertas de prazo ao final.
    """
    from app.modules.scraper import SCRAPERS_REGISTRY

    target_orgaos = (
        [sigla.upper().strip() for sigla in orgaos]
        if orgaos
        else list(SCRAPERS_REGISTRY.keys())
    )
    eff_pdf_enrichment = fetch_docs if enable_pdf_enrichment is None else enable_pdf_enrichment
    resultados: Dict[str, List[Edital]] = {}

    for sigla in target_orgaos:
        scraper = SCRAPERS_REGISTRY.get(sigla)
        if scraper is None:
            logger.warning(f"Portal '{sigla}' não encontrado em SCRAPERS_REGISTRY; ignorando.")
            continue

        persistidos_orgao: List[Edital] = []
        try:
            coletados = scraper.fetch_editais(year=year)
            if max_items_per_orgao is not None:
                coletados = coletados[:max_items_per_orgao]

            for item in coletados:
                if not item.get("link") or not item.get("titulo"):
                    continue
                embedded_docs = item.get("documentos")
                docs: List[Dict[str, Any]] = []
                if fetch_docs and not embedded_docs:
                    try:
                        docs = scraper.fetch_documentos(item["link"])
                    except Exception as doc_exc:
                        logger.warning(f"[{sigla}] Erro ao extrair documentos de {item['link']}: {doc_exc}")
                payload = {
                    **item,
                    "orgao_emissor": item.get("orgao_emissor") or item.get("orgao_origem") or sigla,
                }
                try:
                    salvo = upsert_edital(
                        db=db,
                        edital_data=payload,
                        documentos_data=docs,
                        enable_pdf_enrichment=eff_pdf_enrichment,
                    )
                    persistidos_orgao.append(salvo)
                except Exception as item_exc:
                    db.rollback()
                    logger.warning(f"[{sigla}] Falha ao persistir edital {item.get('link')}: {item_exc}")

            resultados[sigla] = persistidos_orgao
            logger.info(f"[{sigla}] Ciclo periódico concluído: {len(persistidos_orgao)} editais sincronizados.")
        except Exception as exc:
            db.rollback()
            logger.error(f"[{sigla}] Falha geral durante execução periódica: {exc}")
            resultados[sigla] = persistidos_orgao

    try:
        gerar_notificacoes_prazo(db)
    except Exception as notif_exc:
        logger.warning(f"Falha ao gerar notificações periódicas de prazo: {notif_exc}")

    return resultados


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    if "--all" in args:
        args_clean = [a for a in args if a != "--all"]
        ano_arg = int(args_clean[0]) if args_clean and args_clean[0].isdigit() else None
        print(f"Iniciando pipeline periódico completo para todos os portais (ano: {ano_arg or 'atual'})...")
        with SessionLocal() as session:
            por_orgao = run_periodic_pipeline(db=session, year=ano_arg)
            total = sum(len(v) for v in por_orgao.values())
            print(f"Sucesso! {total} editais sincronizados em {len(por_orgao)} portais.")
    else:
        ano_arg = int(args[0]) if args and args[0].isdigit() else None
        print(f"Iniciando pipeline do scraper DEG para o ano: {ano_arg or 'atual'}...")
        with SessionLocal() as session:
            salvos = run_pipeline(db=session, year=ano_arg)
            print(f"Sucesso! {len(salvos)} editais sincronizados com o banco de dados.")

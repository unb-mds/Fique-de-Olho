import hashlib
import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.database import (
    Edital,
    EditalDocumento,
    SessionLocal,
    StatusEdital,
    TipoDocumento,
)
from app.modules.scraper import deg
from app.modules.notificacoes.service import (
    gerar_notificacoes_prazo as _gerar_notificacoes_prazo,
    notificar_edital_atualizado,
)

logger = logging.getLogger(__name__)

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


def map_tipo_documento(tipo_str: str) -> TipoDocumento:
    """Mapeia string do scraper para o enum TipoDocumento do banco."""
    normalizado = tipo_str.lower().strip() if tipo_str else "original"
    return MAPA_TIPOS_DOCUMENTO.get(normalizado, TipoDocumento.ORIGINAL)


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
    """Evita violação da restrição UNIQUE em Edital.url_pdf caso dois editais compartilhem o mesmo PDF."""
    primary = (candidate_pdf or "").strip() or None
    if not primary:
        return None

    collision = (
        db.query(Edital.id)
        .filter(Edital.url_pdf == primary, Edital.url_pagina != url_pagina)
        .first()
    )
    if collision is None:
        return primary

    if url_pagina and url_pagina != primary:
        page_collision = (
            db.query(Edital.id)
            .filter(Edital.url_pdf == url_pagina, Edital.url_pagina != url_pagina)
            .first()
        )
        if page_collision is None:
            return url_pagina

    return None


def _hash_edital(edital_data: Dict[str, Any], documentos_data: List[Dict[str, Any]]) -> str:
    """Calcula um hash estável dos dados observáveis do edital."""
    payload = {
        "titulo": edital_data.get("titulo", ""),
        "resumo": edital_data.get("resumo", ""),
        "data_publicacao": str(edital_data.get("data_publicacao", "")),
        "inicio_inscricao": str(edital_data.get("inicio_inscricao", "")),
        "fim_inscricao": str(edital_data.get("fim_inscricao", "")),
        "documentos": sorted(
            (doc.get("link") or doc.get("url_pdf", ""), doc.get("tipo", ""))
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
) -> Edital:
    """
    Insere ou atualiza um edital e seus documentos associados (UPSERT).
    Garante idempotência e atualização periódica evitando duplicações por url_pagina e url_pdf.
    """
    effective_docs = _merge_documentos_list(edital_data.get("documentos"), documentos_data)
    url_pagina = edital_data.get("link") or edital_data.get("url_pagina", "")
    titulo = edital_data.get("titulo", "Edital sem título")
    data_str = edital_data.get("data_publicacao", "")
    default_yr = edital_data.get("ano") if isinstance(edital_data.get("ano"), int) else None
    data_pub = parse_data_publicacao(str(data_str), default_year=default_yr)
    hash_conteudo = edital_data.get("hash_conteudo") or _hash_edital(edital_data, effective_docs)

    # Determina se há resultado final nos documentos informados
    tem_resultado_final = any(
        map_tipo_documento(doc.get("tipo", "")) == TipoDocumento.RESULTADO_FINAL
        for doc in effective_docs
    )

    inicio_insc = _parse_optional_date(edital_data.get("inicio_inscricao"))
    fim_insc = _parse_optional_date(edital_data.get("fim_inscricao"))
    novo_status = _resolve_edital_status(edital_data, tem_resultado_final, fim_insc)

    # Busca edital existente pela URL única
    edital = db.query(Edital).filter(Edital.url_pagina == url_pagina).first()

    resumo = edital_data.get("resumo") or edital_data.get("descricao") or edital_data.get("assunto")
    tipo = edital_data.get("tipo") or edital_data.get("tipo_edital")
    campus = edital_data.get("campus")

    if edital:
        hash_anterior = edital.hash_conteudo
        # Atualiza dados existentes mantendo frescor em execuções periódicas
        edital.titulo = titulo
        edital.data_publicacao = data_pub
        if resumo:
            edital.resumo = resumo
        if tipo:
            edital.tipo = tipo
        if campus:
            edital.campus = campus
        if inicio_insc is not None or "inicio_inscricao" in edital_data:
            edital.inicio_inscricao = inicio_insc
        if fim_insc is not None or "fim_inscricao" in edital_data:
            edital.fim_inscricao = fim_insc
        edital.hash_conteudo = hash_conteudo
        edital.status = novo_status
        edital.atualizado_em = datetime.now(timezone.utc)
        if hash_anterior != hash_conteudo:
            notificar_edital_atualizado(db, edital, hash_conteudo)
    else:
        # Cria novo edital protegendo unicidade de url_pdf
        safe_url_pdf = _resolve_unique_url_pdf(
            db,
            edital_data.get("url_pdf") or url_pagina,
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
            inicio_inscricao=inicio_insc,
            fim_inscricao=fim_insc,
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

        tipo_enum = map_tipo_documento(doc_data.get("tipo", "original"))

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
) -> List[Edital]:
    """
    Executa a coleta do scraper do DEG e persiste os resultados no banco de dados.
    """
    editais_coletados = deg.fetch_editais(year=year)
    logger.info(f"Coletados {len(editais_coletados)} editais do portal DEG.")

    editais_persistidos: List[Edital] = []
    for item in editais_coletados:
        docs = []
        if fetch_docs and item.get("link"):
            try:
                docs = deg.fetch_documentos(item["link"])
            except Exception as exc:
                logger.warning(f"Erro ao buscar documentos para {item['link']}: {exc}")

        edital_salvo = upsert_edital(db=db, edital_data=item, documentos_data=docs)
        editais_persistidos.append(edital_salvo)

    return editais_persistidos


def run_periodic_pipeline(
    db: Session,
    orgaos: Optional[List[str]] = None,
    year: Optional[int] = None,
    fetch_docs: bool = True,
    max_items_per_orgao: Optional[int] = None,
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
                try:
                    salvo = upsert_edital(db=db, edital_data=item, documentos_data=docs)
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

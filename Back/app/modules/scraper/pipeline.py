import logging
import re
import hashlib
import json
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


def parse_data_publicacao(date_str: str, default_year: int = 2026) -> datetime:
    """Converte strings de datas brasileiras para objetos datetime com timezone."""
    if not date_str or not isinstance(date_str, str):
        return datetime(default_year, 1, 1, tzinfo=timezone.utc)

    cleaned = date_str.strip().lower()

    # Formato: 23 de setembro de 2026
    extenso_match = re.search(r"(\d{1,2})\s+de\s+([a-zçáéíóúãõâêîôû]+)\s+de\s+(\d{4})", cleaned)
    if extenso_match:
        day = int(extenso_match.group(1))
        mes_nome = extenso_match.group(2)
        year = int(extenso_match.group(3))
        month = MESES_PT.get(mes_nome, 1)
        return datetime(year, month, day, tzinfo=timezone.utc)

    # Formato: 15/03/2026
    barra_match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", cleaned)
    if barra_match:
        day = int(barra_match.group(1))
        month = int(barra_match.group(2))
        year = int(barra_match.group(3))
        return datetime(year, month, day, tzinfo=timezone.utc)

    return datetime(default_year, 1, 1, tzinfo=timezone.utc)


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
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            pass
        parsed = parse_data_publicacao(value)
        return parsed.date()
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


def upsert_edital(
    db: Session,
    edital_data: Dict[str, Any],
    documentos_data: Optional[List[Dict[str, Any]]] = None,
) -> Edital:
    """
    Insere ou atualiza um edital e seus documentos associados (UPSERT).
    Garante idempotência evitando duplicações por url_pagina e url_pdf.
    """
    documentos_data = documentos_data or []
    url_pagina = edital_data.get("link") or edital_data.get("url_pagina", "")
    titulo = edital_data.get("titulo", "Edital sem título")
    data_str = edital_data.get("data_publicacao", "")
    data_pub = parse_data_publicacao(str(data_str))
    hash_conteudo = edital_data.get("hash_conteudo") or _hash_edital(edital_data, documentos_data)

    # Determina se há resultado final nos documentos informados
    tem_resultado_final = any(
        map_tipo_documento(doc.get("tipo", "")) == TipoDocumento.RESULTADO_FINAL
        for doc in documentos_data
    )

    # Busca edital existente pela URL única
    edital = db.query(Edital).filter(Edital.url_pagina == url_pagina).first()

    resumo = edital_data.get("resumo") or edital_data.get("descricao") or edital_data.get("assunto")
    tipo = edital_data.get("tipo") or edital_data.get("tipo_edital")

    if edital:
        hash_anterior = edital.hash_conteudo
        # Atualiza dados existentes
        edital.titulo = titulo
        edital.data_publicacao = data_pub
        if resumo and not edital.resumo:
            edital.resumo = resumo
        if tipo and not edital.tipo:
            edital.tipo = tipo
        edital.inicio_inscricao = _parse_optional_date(edital_data.get("inicio_inscricao"))
        edital.fim_inscricao = _parse_optional_date(edital_data.get("fim_inscricao"))
        edital.hash_conteudo = hash_conteudo
        if tem_resultado_final:
            edital.status = StatusEdital.ENCERRADO
        if hash_anterior != hash_conteudo:
            notificar_edital_atualizado(db, edital, hash_conteudo)
    else:
        # Cria novo edital
        status = StatusEdital.ENCERRADO if tem_resultado_final else StatusEdital.ABERTO
        edital = Edital(
            titulo=titulo,
            url_pagina=url_pagina,
            url_pdf=edital_data.get("url_pdf") or url_pagina,
            data_publicacao=data_pub,
            status=status,
            campus=edital_data.get("campus"),
            tipo=tipo,
            resumo=resumo,
            inicio_inscricao=_parse_optional_date(edital_data.get("inicio_inscricao")),
            fim_inscricao=_parse_optional_date(edital_data.get("fim_inscricao")),
            hash_conteudo=hash_conteudo,
        )
        db.add(edital)
        db.flush()

    # Processa documentos vinculados de forma incremental
    docs_existentes = {doc.url_pdf: doc for doc in edital.documentos}

    for doc_data in documentos_data:
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
    Executa a coleta do scraper do DEG e persiste os resultados no PostgreSQL.
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


if __name__ == "__main__":
    import sys

    ano_arg = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    print(f"Iniciando pipeline do scraper para o ano: {ano_arg or 'atual'}...")
    with SessionLocal() as session:
        salvos = run_pipeline(db=session, year=ano_arg)
        print(f"Sucesso! {len(salvos)} editais sincronizados com o banco de dados.")

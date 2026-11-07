"""Camada de serviço para persistência e sincronização periódica de dados raspados dos portais da UnB."""

import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.editais.models import Coleta, Edital
from app.modules.scraper.deg import fetch_editais
from app.modules.scraper.pipeline import gerar_notificacoes_prazo, upsert_edital

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

DATE_ISO_REGEX = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?![0-9])")
DATE_PT_REGEX = re.compile(r"(\d{1,2})\s+de\s+([A-Za-zÀ-ÿ]+)\s+de\s+(\d{4})", re.IGNORECASE)
DATE_SLASH_REGEX = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def parse_date_pt(texto_data: Optional[str]) -> Optional[date]:
    """Converte strings de data ISO ou em português para objetos date do Python."""
    if not texto_data:
        return None

    match_iso = DATE_ISO_REGEX.search(texto_data)
    if match_iso:
        try:
            return date(int(match_iso.group(1)), int(match_iso.group(2)), int(match_iso.group(3)))
        except ValueError:
            return None

    match_extenso = DATE_PT_REGEX.search(texto_data)
    if match_extenso:
        dia = int(match_extenso.group(1))
        mes_str = match_extenso.group(2).lower()
        ano = int(match_extenso.group(3))
        mes = MESES_PT.get(mes_str)
        if mes:
            try:
                return date(ano, mes, dia)
            except ValueError:
                return None

    match_slash = DATE_SLASH_REGEX.search(texto_data)
    if match_slash:
        dia = int(match_slash.group(1))
        mes = int(match_slash.group(2))
        ano = int(match_slash.group(3))
        try:
            return date(ano, mes, dia)
        except ValueError:
            return None

    return None


def inferir_categoria(titulo: str) -> str:
    """Infere o tipo do edital a partir de palavras-chave no título."""
    tit_lower = titulo.lower()
    if "monitoria" in tit_lower:
        return "Monitoria"
    if "pibic" in tit_lower or "pibiti" in tit_lower or "iniciação científica" in tit_lower or "iniciação tecnológica" in tit_lower:
        return "PIBIC"
    if "residência" in tit_lower or "residencia" in tit_lower or "enare" in tit_lower:
        return "Residência"
    if "extensão" in tit_lower or "extensao" in tit_lower or "inovação" in tit_lower or "inovacao" in tit_lower or "ocean" in tit_lower:
        return "Extensões"
    if "bolsa" in tit_lower or "auxílio" in tit_lower or "auxilio" in tit_lower or "permanência" in tit_lower:
        return "Bolsas / Auxílios"
    if "estágio" in tit_lower or "estagio" in tit_lower:
        return "Estágio"
    if "pesquisa" in tit_lower:
        return "Pesquisa"
    if "vestibular" in tit_lower or "transferência" in tit_lower or "transferencia" in tit_lower:
        return "Vestibular"
    return "Extensões"


def sync_deg_editais(db: Session, max_items: int = 30) -> Dict[str, Any]:
    """Executa a coleta no portal do DEG e persiste novos editais no banco de dados."""
    coleta = Coleta(fonte="DEG", status="executando")
    db.add(coleta)
    db.commit()
    db.refresh(coleta)

    novos_count = 0
    try:
        itens_raspados = fetch_editais()
        itens_para_processar = itens_raspados[:max_items]

        for item in itens_para_processar:
            titulo = item.get("titulo", "").strip()
            link = item.get("link", "").strip()
            if not titulo or not link:
                continue

            edital_existente = (
                db.query(Edital)
                .filter((Edital.url_pdf == link) | (Edital.url_pagina == link))
                .first()
            )
            upsert_edital(
                db,
                {
                    **item,
                    "resumo": f"Edital publicado pelo DEG em {item.get('data_publicacao', 'data não informada')}.",
                    "campus": "Darcy Ribeiro",
                    "tipo": inferir_categoria(titulo),
                },
            )
            if not edital_existente:
                novos_count += 1

        db.commit()

        coleta.status = "concluida"
        coleta.editais_encontrados = len(itens_raspados)
        coleta.finalizada_em = func.now()
        db.commit()

        return {
            "status": "success",
            "coleta_id": coleta.id,
            "editais_encontrados": len(itens_raspados),
            "novos_editais": novos_count,
            "mensagem": f"Sincronização concluída com sucesso. {novos_count} novos editais persistidos.",
        }

    except Exception as e:
        db.rollback()
        coleta.status = "falhou"
        coleta.mensagem_erro = str(e)
        coleta.finalizada_em = func.now()
        db.commit()
        raise e


def sync_portal_editais(
    db: Session,
    orgao: str,
    max_items: Optional[int] = 100,
    year: Optional[int] = None,
    fetch_docs: bool = False,
) -> Dict[str, Any]:
    """Executa a coleta idempotente e periódica de um portal específico registrado em SCRAPERS_REGISTRY."""
    from app.modules.scraper import get_scraper

    sigla = orgao.upper().strip()
    scraper = get_scraper(sigla)
    if scraper is None:
        raise ValueError(f"Portal '{sigla}' não registrado em SCRAPERS_REGISTRY.")

    coleta = Coleta(fonte=sigla, status="executando")
    db.add(coleta)
    db.commit()
    db.refresh(coleta)

    novos_count = 0
    atualizados_count = 0
    try:
        itens_raspados = scraper.fetch_editais(year=year)
        itens_para_processar = itens_raspados[:max_items] if max_items is not None else itens_raspados

        for item in itens_para_processar:
            titulo = str(item.get("titulo") or "").strip()
            link = str(item.get("link") or "").strip()
            if not titulo or not link:
                continue

            edital_existente = db.query(Edital).filter(Edital.url_pagina == link).first()
            hash_anterior = edital_existente.hash_conteudo if edital_existente else None

            docs: List[Dict[str, Any]] = []
            if fetch_docs and not item.get("documentos"):
                try:
                    docs = scraper.fetch_documentos(link)
                except Exception as doc_exc:
                    logger.warning(f"[{sigla}] Erro ao buscar documentos de {link}: {doc_exc}")

            payload = {
                **item,
                "resumo": (
                    item.get("resumo")
                    or item.get("descricao")
                    or item.get("assunto")
                    or f"Edital publicado pelo portal {sigla} em {item.get('data_publicacao') or 'data não informada'}."
                ),
                "campus": item.get("campus") or "Darcy Ribeiro",
                "tipo": item.get("tipo") or item.get("tipo_edital") or inferir_categoria(titulo),
            }
            edital_salvo = upsert_edital(db, payload, documentos_data=docs)
            if edital_existente is None:
                novos_count += 1
            elif hash_anterior != edital_salvo.hash_conteudo:
                atualizados_count += 1

        coleta.status = "concluida"
        coleta.editais_encontrados = len(itens_raspados)
        coleta.finalizada_em = func.now()
        db.commit()

        return {
            "status": "success",
            "fonte": sigla,
            "coleta_id": coleta.id,
            "editais_encontrados": len(itens_raspados),
            "novos_editais": novos_count,
            "editais_atualizados": atualizados_count,
            "mensagem": (
                f"[{sigla}] Sincronização periódica concluída: "
                f"{novos_count} novos e {atualizados_count} atualizados."
            ),
        }
    except Exception as exc:
        db.rollback()
        coleta.status = "falhou"
        coleta.mensagem_erro = str(exc)
        coleta.finalizada_em = func.now()
        db.commit()
        raise exc


def sync_all_portais(
    db: Session,
    orgaos: Optional[List[str]] = None,
    max_items_per_orgao: Optional[int] = 100,
    year: Optional[int] = None,
    fetch_docs: bool = False,
) -> Dict[str, Any]:
    """Sincroniza periodicamente todos os portais da UnB (ou subconjunto informado), isolando erros por órgão."""
    from app.modules.scraper import SCRAPERS_REGISTRY

    target_orgaos = (
        [s.upper().strip() for s in orgaos]
        if orgaos
        else list(SCRAPERS_REGISTRY.keys())
    )
    relatorios: Dict[str, Any] = {}
    total_encontrados = 0
    total_novos = 0
    total_atualizados = 0

    for sigla in target_orgaos:
        try:
            res = sync_portal_editais(
                db=db,
                orgao=sigla,
                max_items=max_items_per_orgao,
                year=year,
                fetch_docs=fetch_docs,
            )
            relatorios[sigla] = res
            total_encontrados += int(res.get("editais_encontrados", 0))
            total_novos += int(res.get("novos_editais", 0))
            total_atualizados += int(res.get("editais_atualizados", 0))
        except Exception as exc:
            logger.error(f"Erro ao sincronizar portal {sigla} no ciclo periódico: {exc}")
            relatorios[sigla] = {
                "status": "error",
                "fonte": sigla,
                "erro": str(exc),
            }

    try:
        gerar_notificacoes_prazo(db)
    except Exception as notif_exc:
        logger.warning(f"Erro ao gerar notificações de prazo após sync_all_portais: {notif_exc}")

    return {
        "status": "success",
        "portais_processados": len(target_orgaos),
        "editais_encontrados": total_encontrados,
        "novos_editais": total_novos,
        "editais_atualizados": total_atualizados,
        "portais": relatorios,
    }

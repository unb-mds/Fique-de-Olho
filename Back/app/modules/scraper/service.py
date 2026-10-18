"""Camada de serviço para persistência e sincronização de dados raspados do DEG."""

import re
from datetime import date, datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.modules.editais.models import Edital, Campus, TipoEdital, Coleta
from app.modules.scraper.deg import fetch_editais

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

DATE_PT_REGEX = re.compile(r"(\d{1,2})\s+de\s+([A-Za-zÀ-ÿ]+)\s+de\s+(\d{4})", re.IGNORECASE)
DATE_SLASH_REGEX = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def parse_date_pt(texto_data: Optional[str]) -> Optional[date]:
    """Converte strings de data em português para objetos date do Python."""
    if not texto_data:
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
    if "pibic" in tit_lower or "pibiti" in tit_lower or "iniciação científica" in tit_lower:
        return "PIBIC"
    if "extensão" in tit_lower or "extensao" in tit_lower or "inovação" in tit_lower or "inovacao" in tit_lower:
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

        # Cache de catálogos
        campi_cache: Dict[str, Campus] = {c.nome: c for c in db.query(Campus).all()}
        tipos_cache: Dict[str, TipoEdital] = {t.nome: t for t in db.query(TipoEdital).all()}

        default_campus = campi_cache.get("Darcy Ribeiro") or db.query(Campus).first()

        for item in itens_para_processar:
            titulo = item.get("titulo", "").strip()
            link = item.get("link", "").strip()
            if not titulo or not link:
                continue

            pub_date = parse_date_pt(item.get("data_publicacao"))
            cat_nome = inferir_categoria(titulo)
            tipo_obj = tipos_cache.get(cat_nome)
            if not tipo_obj:
                tipo_obj = TipoEdital(nome=cat_nome)
                db.add(tipo_obj)
                db.flush()
                tipos_cache[cat_nome] = tipo_obj

            edital_existente = db.query(Edital).filter(Edital.url_pdf == link).first()
            if not edital_existente:
                novo_edital = Edital(
                    identificador_origem=link,
                    titulo=titulo,
                    resumo=f"Edital publicado pelo DEG em {item.get('data_publicacao', 'data não informada')}.",
                    url_pdf=link,
                    data_publicacao=pub_date,
                    status_processamento="processado",
                )
                if default_campus:
                    novo_edital.campi.append(default_campus)
                novo_edital.tipos.append(tipo_obj)
                db.add(novo_edital)
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

